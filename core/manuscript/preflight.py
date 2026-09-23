"""Local publication gate. Structural checks are not a semantic accuracy score."""
import re
from core.manuscript.structure import propose_rules, validate, SPECIAL

PROTECTED = {'code-block', 'code-output', 'table', 'figure', 'math-expression',
             'figure-caption', 'numbered-list', 'procedure-step', 'bullet-list'}


def heading_level(block):
    text = block.text.strip()
    if block.kind in PROTECTED or block.assets or not text or SPECIAL.match(text):
        return None
    if re.match(r'^(?:chapter\s*\d+|제?\s*\d+\s*장)(?:\b|\s|[.:])', text, re.I):
        return 1
    if re.match(r'^\d+\.\d+\.\d+\.\d+[.\s]', text):
        return 4
    if re.match(r'^\d+\.\d+\.\d+[.\s]', text):
        return 3
    if re.match(r'^\d+\.\d+[.\s]', text):
        return 2
    if block.outline_level in (1, 2, 3, 4):
        return block.outline_level
    match = re.match(r'^(?:heading|제목)\s*([1234])$', block.style, re.I)
    return int(match[1]) if match else None


def inspect_structure(master, nodes=None, generated=False):
    issues = []
    def issue(code, block, message):
        issues.append({'code': code, 'block_id': block, 'message': message})
    if not master.blocks:
        issue('empty', '', '분석할 본문이 없습니다.')
        return {'passed': False, 'nodes': [], 'issues': issues}
    try:
        nodes = validate(master, nodes if nodes is not None else propose_rules(master))
    except ValueError as exc:
        issue('invalid_hierarchy', master.blocks[0].id, str(exc))
        return {'passed': False, 'nodes': [], 'issues': issues}
    candidates = [(b, heading_level(b)) for b in master.blocks if heading_level(b)]
    real = [n for n in nodes if n['use_source_title']]
    if not generated and not real:
        issue('no_headings', master.blocks[0].id, '장·절 제목의 번호 또는 Word 제목 단서가 없습니다. AI 구조 재구성을 허용하거나 제목을 추가하세요.')
    # A single invented parent does not constitute reconstructed structure.
    if generated and len(nodes) < 2:
        issue('insufficient_ai_structure', master.blocks[0].id, 'AI가 충분한 구획을 찾지 못했습니다. 임시 장 제목 하나만으로 자동 제작하지 않습니다.')
    by_anchor = {(n['start_block_id'], n['level']) for n in nodes}
    for b, level in candidates:
        if not generated and (b.id, level) not in by_anchor:
            issue('omitted_heading', b.id, '제목 후보가 목차에서 누락되거나 수준이 충돌합니다: ' + b.text[:80])
        if len(b.text) > 180 or '\n' in b.text or re.search(r'(?:합니다|입니다|한다|된다|있다|없다)[.!?]$', b.text.strip()):
            issue('prose_heading', b.id, '일반 문장이 제목으로 지정된 것으로 보입니다: ' + b.text[:80])
    # Numbering evidence must agree with its enclosing chapter/section.
    chapter, section, last_number = None, None, {}
    previous_chapter = None
    for b, level in candidates:
        t=b.text.strip()
        cm=re.match(r'^(?:chapter\s*|제?\s*)(\d+)\s*(?:장)?', t, re.I) if level == 1 else None
        sm=re.match(r'^(\d+)\.(\d+)(?:\.(\d+))?[.\s]', t) if level > 1 else None
        if level == 1:
            chapter=int(cm[1]) if cm else None
            if chapter is not None and previous_chapter is not None and chapter <= previous_chapter:
                issue('chapter_order', b.id, '장 번호가 중복되거나 역순입니다: ' + t[:80])
            if chapter is not None: previous_chapter=chapter
            section=None; last_number={}
        if sm:
            num=tuple(int(v) for v in sm.groups() if v is not None)
            if chapter is not None and num[0] != chapter:
                issue('number_conflict', b.id, '절 번호가 상위 장 번호와 맞지 않습니다: ' + t[:80])
            if level == 3 and section is not None and num[:2] != section:
                issue('number_conflict', b.id, '소단원 번호가 상위 절 번호와 맞지 않습니다: ' + t[:80])
            key=(level,num[:-1])
            if key in last_number and num[-1] <= last_number[key]:
                issue('number_order', b.id, '같은 범위에서 제목 번호가 중복되거나 역순입니다: ' + t[:80])
            last_number[key]=num[-1]
            if level == 2: section=num[:2]
    indices={b.id:i for i,b in enumerate(master.blocks)}
    for n in nodes:
        descendants=[x for x in nodes if x['parent_id']==n['id']]
        if descendants: continue
        a,z=indices[n['start_block_id']],indices[n['end_block_id']]
        body=[b for b in master.blocks[a:z+1] if b.kind=='paragraph' and b.text.strip()]
        if len(body)>40:
            issue('long_unsegmented_range', n['start_block_id'], f"{n['title'][:60]}: 일반 본문 {len(body)}문단이 한 구간에 모여 있습니다. 절 구분을 보완하세요.")
    for n in nodes:
        b=master.blocks[indices[n['start_block_id']]]
        if generated and n['use_source_title'] and (heading_level(b) is None or b.kind in PROTECTED):
            issue('ai_promoted_prose', b.id, 'AI가 제목 단서 없는 본문을 제목으로 변경하려 했습니다. 새 제목으로 구분해야 합니다.')
    return {'passed': not issues, 'nodes': nodes, 'issues': issues}
