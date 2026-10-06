"""Source-grounded learning additions, stored separately from manual decisions."""
import copy
from dataclasses import asdict
import re

from core.ai.publication_request import request
from core.ai.workflow import write_json
from core.cancellation import check_cancelled
from core.manuscript.structure import validate, fingerprint
from core.manuscript.learning_scope import has_learning_content
from core.master import Block
from core.qa.editorial import EXERCISE, PLACEHOLDER

ISOLATED_PLACEHOLDER = re.compile(r'^\s*[（(]?\s*추후\s*제공\s*[）)]?\s*[.!]?\s*$')


def units(master, nodes, skipped=None):
    nodes = validate(master, nodes)
    indices = {b.id: i for i, b in enumerate(master.blocks)}
    result = []
    for node in nodes:
        if node['level'] not in (1, 2) or EXERCISE.search(node['title']):
            continue
        blocks = master.blocks[indices[node['start_block_id']]:indices[node['end_block_id']] + 1]
        if not has_learning_content(blocks, nodes):
            if skipped is not None:
                skipped.append({'unit_id': node['id'], 'title': node['title'],
                                'reason': '학습 본문 없이 제목·빈 문단·그림·미완성 표식만 있는 구간'})
            continue
        # A heading followed only by a placeholder is not a completed exercise.
        pattern = r'장말\s*연습문제|연습\s*문제' if node['level'] == 1 else r'절\s*확인\s*활동|확인\s*문제|스스로\s*점검|퀴즈'
        exercise_start = next((i for i, b in enumerate(blocks) if re.search(pattern, b.text)
                               and b.kind not in {'code-block','code-output'} and len(b.text) < 80), None)
        exercise_body = blocks[exercise_start + 1:] if exercise_start is not None else []
        next_heading = next((i for i, b in enumerate(exercise_body) if b.kind == 'heading'
                             or re.match(r'^(?:Chapter\s*\d|\d+\.\d+\s)', b.text, re.I)), len(exercise_body))
        exercise_body = exercise_body[:next_heading]
        has_exercise = any(b.text.strip() and not ISOLATED_PLACEHOLDER.fullmatch(b.text)
                           and not PLACEHOLDER.search(b.text) and b.kind not in {'heading', 'figure-caption'}
                           for b in exercise_body)
        has_placeholder = any(ISOLATED_PLACEHOLDER.fullmatch(b.text) for b in exercise_body)
        if has_exercise and not has_placeholder:
            continue
        chapter_exercise = next((i for i, b in enumerate(blocks) if re.search(r'연습\s*문제', b.text)
                                 and len(b.text) < 80 and b.kind not in {'code-block','code-output'}), None)
        anchor = blocks[chapter_exercise - 1].id if node['level'] == 2 and chapter_exercise and chapter_exercise > 0 else node['end_block_id']
        result.append({**node, 'blocks': blocks, 'anchor': anchor, 'type': 'chapter' if node['level'] == 1 else 'section',
                       'placeholders': [b.id for b in exercise_body if ISOLATED_PLACEHOLDER.fullmatch(b.text)] if node['level'] == 1 else []})
    return result


def validate_questions(data, sources, unit_type):
    if not isinstance(data, dict) or not isinstance(data.get('questions'), list):
        raise ValueError('학습 보완 응답 형식 오류')
    count = len(data['questions'])
    if not (2 <= count <= 3 if unit_type == 'section' else 5 <= count <= 9):
        raise ValueError(f'절 확인 문제는 2~3개, 장말 문제는 5~9개가 필요합니다. 반환된 문제: {count}개.'
                         + (' 원고 근거가 부족하여 문제를 생성하지 못했습니다.' if count == 0 else ''))
    seen = set()
    for q in data['questions']:
        if not isinstance(q, dict):
            raise ValueError('학습 문제 형식 오류')
        for key in ('question','answer','explanation'):
            value = q.get(key)
            if not isinstance(value, str) or not value.strip() or len(value) > 2000 or PLACEHOLDER.search(value):
                raise ValueError('학습 문제·정답·해설이 없거나 미완성입니다.')
        if q['question'].strip() in seen:
            raise ValueError('학습 문제가 중복되었습니다.')
        seen.add(q['question'].strip())
        evidence = q.get('evidence')
        if not isinstance(evidence, list) or not evidence:
            raise ValueError('학습 문제의 원고 근거가 없습니다.')
        for item in evidence:
            if (not isinstance(item, dict) or item.get('block_id') not in sources
                or not isinstance(item.get('quote'), str) or len(item['quote'].strip()) < 8
                or item['quote'] not in sources[item['block_id']]):
                raise ValueError('학습 문제의 근거 위치·인용이 원고와 다릅니다.')


def generate(job, master, nodes, models, progress=None, cancelled=None):
    skipped = []
    planned = units(master, nodes, skipped)
    locked = {i['block_id'] for i in job.workflow().items() + job.workflow().legacy()
              if i.get('status') in ('approved','rejected','hold')}
    additions, replacements, completed = [], [], []
    for number, unit in enumerate(planned, 1):
        check_cancelled(cancelled)
        if progress:
            progress({'phase': f'학습 문제 보완·검수 {number}/{len(planned)} · {unit["title"]}', 'percent': 71})
        # Code is read-only evidence, never sent to a rewrite endpoint or executed.
        rows = [{'id': b.id, 'kind': b.kind, 'text': b.text, 'rows': b.rows} for b in unit['blocks']
                if b.text.strip() or b.rows]
        sources = {b.id: b.text + ('\n' + '\n'.join('\n'.join(r) for r in b.rows) if b.rows else '') for b in unit['blocks']}
        import json
        if len(json.dumps(rows, ensure_ascii=False)) > 60000:
            raise ValueError('학습 보완 범위가 60,000자를 초과합니다. 장을 나누어 제작하세요: ' + unit['title'])
        count = '2~3개 짧은 확인 문제 또는 실습 체크 항목' if unit['type'] == 'section' else '5~9개 장말 연습문제'
        def validator(data):
            try:
                validate_questions(data, sources, unit['type'])
            except ValueError as exc:
                raise ValueError(unit['title'] + ' · ' + str(exc)) from exc
        data = request(job, 'learning-generate-v1', models['technical_review'],
            '제공된 원고에서 배운 내용만 사용하여 ' + count + '을 작성하세요. '
            '개념 설명·적용·오류 찾기를 적절히 섞되 원고에 없는 코드 실행 결과나 기술 사실을 추측하지 마세요. '
            '기존 문제를 중복하지 말고 코드 자체를 새로 쓰거나 고치지 마세요. 각 문제의 정답과 짧은 해설을 별도로 작성하세요. '
            '질문·정답·해설을 직접 뒷받침하는 원고 문단 ID와 정확한 인용을 포함하세요. 근거가 없으면 questions=[]로 반환하세요. '
            '{"questions":[{"question":"문제","answer":"예시 정답","explanation":"해설","evidence":[{"block_id":"id","quote":"정확한 원고 인용"}]}]}',
            {'id': unit['id'], 'title': unit['title'], 'type': unit['type'], 'sources': rows}, validator, cancelled)
        def review_validator(value):
            if (not isinstance(value, dict) or type(value.get('accepted')) is not bool
                or not isinstance(value.get('reason'), str) or not value['reason'].strip()):
                raise ValueError('학습 문제 독립 검수 응답 형식 오류')
        verdict = request(job, 'learning-review-v1', models['final_review'],
            '학습 문제를 독립 검수하세요. 모든 질문·정답·해설이 해당 원고에서 학습한 내용과 인용 근거로 실제 뒷받침되는지, '
            '정답의 정확성·모호성·중복·오탈자·난이도를 검사하세요. 인용이 존재한다는 이유만으로 통과시키지 마세요. '
            '새 코드나 검증되지 않은 실행 결과가 있으면 거부하세요. 하나라도 문제가 있으면 accepted=false. '
            '{"accepted":true,"reason":"검수 근거"}',
            {'id': unit['id'], 'sources': rows, 'questions': data['questions']}, review_validator, cancelled)
        if not verdict['accepted']:
            raise ValueError('학습 문제 검수 미통과: ' + unit['title'] + ' · ' + verdict['reason'])
        title = '장말 연습문제' if unit['type'] == 'chapter' else '절 확인 활동'
        questions = '\n\n'.join(f'{i}. {q["question"]}' for i, q in enumerate(data['questions'], 1))
        answers = '\n\n'.join(f'{i}. {q["answer"]}\n해설: {q["explanation"]}' for i, q in enumerate(data['questions'], 1))
        text = title + '\n\n' + questions + '\n\n예시 정답과 해설\n\n' + answers
        replace_ids = unit['placeholders']
        if len(replace_ids) > 1:
            raise ValueError('장말 미완성 표식이 여러 곳입니다. 위치를 먼저 확인하세요: ' + unit['title'])
        if replace_ids:
            block = next(b for b in master.blocks if b.id == replace_ids[0])
            if block.id in locked or block.assets or block.links or block.rows or block.kind in {'code-block','code-output','table','math-expression'}:
                raise ValueError('보호된 미완성 문제는 자동 교체할 수 없습니다: ' + block.id)
            replacements.append({'block_id': block.id, 'source_text': block.text, 'text': text})
        else:
            additions.append({'after': unit['anchor'], 'block': asdict(Block(
                id='learning-' + unit['id'], kind='exercise', text=text, inlines=[{'kind':'text','text':text}]))})
        completed.append({'unit_id': unit['id'], 'title': unit['title'], 'type': unit['type'], **data, 'review': verdict})
    report = {'policy': 'learning-v1', 'baseline_hash': fingerprint(master), 'additions': additions,
              'replacements': replacements, 'units': completed, 'skipped_units': skipped,
              'question_count': sum(len(u['questions']) for u in completed)}
    write_json(job.work / 'learning-last.json', report)
    return report


def apply(master, report):
    if report.get('baseline_hash') != fingerprint(master):
        raise ValueError('학습 보완 중 기준 원고가 변경됐습니다.')
    result = copy.deepcopy(master)
    by_id = {b.id: b for b in result.blocks}
    replaced = set()
    for item in report['replacements']:
        b = by_id[item['block_id']]
        if (b.id in replaced or b.text != item['source_text'] or not ISOLATED_PLACEHOLDER.fullmatch(b.text)
            or b.assets or b.links or b.rows or b.kind in {'code-block','code-output','table','math-expression'}):
            raise ValueError('학습 보완의 미완성 표식 교체 검사 실패')
        b.text = item['text']; b.inlines = [{'kind':'text','text':b.text}]
        replaced.add(b.id)
    after = {}
    for item in report['additions']:
        b = Block(**item['block'])
        if item['after'] not in by_id or b.id in by_id or b.kind != 'exercise' or b.assets or b.links or b.rows:
            raise ValueError('학습 보완 위치 또는 보호 검사 실패')
        by_id[b.id] = b
        after.setdefault(item['after'], []).append(b)
    # Section activities precede chapter exercises when they share the final anchor.
    for values in after.values():
        values.sort(key=lambda b: b.text.startswith('장말'))
    result.blocks = [item for b in result.blocks for item in [b, *after.get(b.id, [])]]
    if result.outline:
        result.outline = validate(result, result.outline)
    return result
