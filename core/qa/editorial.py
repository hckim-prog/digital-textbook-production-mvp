"""Content readiness is separate from source/output fidelity. Never edits text."""
from html import escape
import re

from core.ai.publication_request import request
from core.qa.checks import save_report
from core.manuscript.learning_scope import has_learning_content

PLACEHOLDER = re.compile(r'\[(?:FIGURE\b[^\]]*|이미지\s*확인\s*필요[^\]]*)\]|[（(]\s*추후\s*제공\s*[）)]|^\s*추후\s*제공\s*[.!]?\s*$|^\s*(?:TODO|TBD)\s*(?::.*)?$', re.I)
EXERCISE = re.compile(r'연습\s*문제|확인\s*문제|스스로\s*점검|자가\s*진단|퀴즈')
TECHNICAL = re.compile(r'Visual\s*Studio|단축키|signed|unsigned|overflow|underflow|완전한\s*상위\s*집합|항상.*(?:크기|바이트|순환)', re.I)


def text_units(master):
    """Include captions and prose cells; code/output/math are read-protected."""
    for b in master.blocks:
        if b.kind in {'code-block', 'code-output', 'math-expression'}:
            continue
        if b.kind == 'table':
            for ri, row in enumerate(b.rows):
                for ci, value in enumerate(row):
                    kind = b.cell_kinds[ri][ci] if ri < len(b.cell_kinds) and ci < len(b.cell_kinds[ri]) else 'paragraph'
                    if kind not in {'code-block', 'code-output', 'math-expression'} and value.strip():
                        yield {'id': f'{b.id}-r{ri}c{ci}', 'text': value, 'kind': kind}
        elif b.text.strip():
            yield {'id': b.id, 'text': b.text, 'kind': b.kind}


def inspect(master):
    issues, seen = [], {}
    def add(unit, code, message, severity='warning', quote=None):
        issues.append({'block_id': unit['id'], 'code': code, 'severity': severity,
                       'quote': quote or unit['text'][:160], 'message': message})
    units = list(text_units(master))
    for unit in units:
        text = unit['text']
        marker = PLACEHOLDER.search(text)
        if marker:
            add(unit, 'placeholder', '제작용 미완성 표식이 남았습니다.', 'error', marker.group())
        if TECHNICAL.search(text):
            add(unit, 'technical_source', '버전·플랫폼·언어 규칙을 공식 문서로 확인해야 합니다. 자동 사실 검증은 미실행입니다.')
        if re.search(r'[가-힣][A-Za-z]{2,}', text):
            add(unit, 'mixed_spacing', '한영 접합 후보입니다. 고유명사·UI 이름인지 확인하세요.')
        if unit['kind'] == 'paragraph' and len(text.strip()) >= 24:
            if text.strip() in seen:
                add(unit, 'duplicate', '동일 문단이 반복됩니다: ' + seen[text.strip()])
            seen[text.strip()] = unit['id']
        if re.search(r'\d+\s*(?:쪽|페이지)', text):
            add(unit, 'page_reference', '재조판된 PDF의 실제 페이지와 참조를 대조하세요.')
    formal = [u for u in units if re.search(r'(?:입니다|합니다|됩니다)[.!?]?$', u['text'])]
    plain = [u for u in units if re.search(r'(?:이다|한다|된다)[.!?]?$', u['text'])]
    if formal and plain:
        add(plain[0], 'mixed_style', '이다/입니다 문체가 함께 있습니다. 인용·문제 문체는 별도 확인하세요.')
    for b in master.blocks:
        if b.assets:
            issues.append({'block_id': b.id, 'code': 'image_semantics', 'severity': 'warning', 'quote': '',
                           'message': '이미지 파일 보존과 별도로 화면의 버튼·메뉴·실행 결과와 본문 일치를 사람이 확인해야 합니다.'})
        if b.kind == 'figure-caption' and not b.text.strip():
            issues.append({'block_id': b.id, 'code': 'empty_caption', 'severity': 'error', 'quote': '', 'message': '그림 캡션이 비어 있습니다.'})
    indices = {b.id: i for i, b in enumerate(master.blocks)}
    for n in master.outline:
        if n['level'] not in (1, 2) or EXERCISE.search(n['title']):
            continue
        blocks = master.blocks[indices[n['start_block_id']]:indices[n['end_block_id']] + 1]
        if not has_learning_content(blocks, master.outline):
            continue
        pattern = r'장말\s*연습문제|연습\s*문제' if n['level'] == 1 else r'절\s*확인\s*활동|확인\s*문제|스스로\s*점검|퀴즈'
        if not any(re.search(pattern, b.text) for b in blocks if b.kind not in {'code-block','code-output'}):
            issues.append({'block_id': n['start_block_id'], 'code':'missing_learning', 'severity':'warning', 'quote':n['title'],
                           'message': '장말 연습문제 보완 필요' if n['level'] == 1 else '절 확인 활동 보완 필요'})
    return issues


def audit(job, master, selection, cancelled=None, progress=None):
    units = list(text_units(master))
    batches, batch, size = [], [], 0
    for unit in units:
        length = len(unit['text'])
        if length > 12000:
            raise ValueError('텍스트 QA 단위가 12,000자를 초과합니다: ' + unit['id'])
        if size + length > 16000 and batch:
            batches.append(batch); batch, size = [], 0
        batch.append(unit); size += length
    if batch:
        batches.append(batch)
    issues = []
    for i, batch in enumerate(batches):
        if progress:
            progress({'phase': f'독립 텍스트 QA {i+1}/{len(batches)}', 'percent': 73})
        by_id = {u['id']: u['text'] for u in batch}
        def validate(data):
            if not isinstance(data, dict) or not isinstance(data.get('issues'), list):
                raise ValueError('텍스트 QA 응답 형식 오류')
            for item in data['issues']:
                if (not isinstance(item, dict) or item.get('block_id') not in by_id
                    or item.get('category') not in {'typo','english','spacing','incomplete','style','duplicate','placeholder','technical','reference'}
                    or not isinstance(item.get('quote'), str) or not item['quote'].strip()
                    or item['quote'] not in by_id[item['block_id']]
                    or not isinstance(item.get('message'), str) or not item['message'].strip()
                    or type(item.get('definite')) is not bool):
                    raise ValueError('텍스트 QA의 위치·근거·판정 형식 오류')
        data = request(job, 'editorial-audit-v1', selection,
            '최종 출력 후보를 읽기 전용으로 문장 단위 검사하세요. 수정되지 않은 문단도 검사합니다. '
            '오탈자, 영문 철자, 한영 접합/조사 구분, 띄어쓰기, 미완성 문장, 문체 혼용, 중복, 제작 표식, 내부 참조를 확인하세요. '
            '제목·목록·캡션·문제의 정상적인 짧은 문구는 미완성으로 오인하지 마세요. 기술적 의심은 technical로 분리하고 공식 근거를 확인했다고 주장하지 마세요. '
            '현재 자료에서 확실한 오류만 definite=true. 문제 없으면 빈 issues. '
            '{"issues":[{"block_id":"원문 id","category":"typo","quote":"오류가 있는 정확한 원문 구절","message":"문제와 필요한 조치","definite":true}]}',
            {'id': f'batch-{i}', 'units': batch}, validate, cancelled)
        for item in data['issues']:
            issues.append({**item, 'code': 'ai_' + item['category'],
                           'severity': 'error' if item['definite'] and item['category'] != 'technical' else 'warning'})
    return issues


def report(master, ai_issues=None, automatic_report=None):
    issues = inspect(master) + (ai_issues or [])
    for item in (automatic_report or {}).get('retained', []):
        issues.append({'block_id': item['block_id'], 'code': 'retained_edit', 'severity': 'warning',
                       'quote': item.get('source_text', ''), 'message': item['reason']})
    errors = sum(i['severity'] == 'error' for i in issues)
    return {'passed': errors == 0, 'status': 'FAIL' if errors else 'REVIEW_REQUIRED' if issues or ai_issues is None else 'AUTOMATED_CHECKS_PASSED',
            'ai_audited': ai_issues is not None, 'issues': issues, 'error_count': errors,
            'note': '자동 검사 결과이며 상품화 승인이나 전체 사실 정확성 보증이 아닙니다. 공식 문서 대조·이미지 내용 대조·사람의 최종 승인은 별도입니다.'}


def save(report, folder):
    save_report(report, folder / 'editorial-qa.json')
    rows = ''.join('<tr>' + ''.join('<td>' + escape(str(i.get(k, ''))) + '</td>' for k in
                   ('severity','block_id','quote','message')) + '</tr>' for i in report['issues'])
    path = folder / 'editorial-qa.html'
    path.write_text('<!doctype html><meta charset="utf-8"><title>텍스트·출판 완결성 검사</title>'
                    '<style>body{font-family:Malgun Gothic;margin:2rem}td,th{border:1px solid #ccc;padding:.6rem;white-space:pre-wrap}table{border-collapse:collapse}</style>'
                    '<h1>텍스트·출판 완결성 검사: ' + report['status'] + '</h1><p>' + escape(report['note'])
                    + '</p><p>독립 AI 텍스트 검사: ' + ('실행' if report['ai_audited'] else '미실행')
                    + '</p><table><tr><th>수준</th><th>위치</th><th>원문 근거</th><th>확인 사항</th></tr>' + rows + '</table>', encoding='utf-8')
    return path
