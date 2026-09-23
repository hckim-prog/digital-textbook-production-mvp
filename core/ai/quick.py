"""Conservative output-only corrections; never rewrite review decisions."""
import re
from collections import Counter
from core.ai.service import approved_master, editable

# Deliberately small, auditable allowlist. No general whitespace normalization.
RULES = (("몇일", "며칠"), ("금새", "금세"), ("어의없다", "어이없다"),
         ("할수 있다", "할 수 있다"), ("할수 없다", "할 수 없다"))


def allowed(source, target):
    if source == target:
        return False
    changed = source
    for before, after in RULES:
        changed = re.sub(r"(?<![\w])" + re.escape(before) + r"(?![\w])", after, changed)
    return changed == target


def quick_master(master, items):
    counts = Counter(i['block_id'] for i in items if i.get('status') == 'pending'
                     and i.get('role') == 'proofreading')
    locked = {i['block_id'] for i in items if i.get('status') in ('approved', 'hold', 'rejected')}
    blocks = {b.id: b for b in master.blocks}
    applied, retained = [], []
    for item in items:
        if item.get('status') != 'pending':
            continue
        block = blocks.get(item['block_id'])
        reason = '표현·기술 변경 또는 자동 적용 기준 밖'
        ok = (item.get('role') == 'proofreading' and item.get('level') == 'A'
              and counts[item['block_id']] == 1 and item['block_id'] not in locked
              and block is not None and editable(block) and not block.assets and not block.links
              and block.text == item.get('source_text')
              and allowed(block.text, item.get('suggested_text', '')))
        if ok:
            applied.append({**item, 'status': 'approved', 'application': 'quick-output-only'})
        else:
            retained.append({'id': item['id'], 'block_id': item['block_id'], 'reason': reason})
    result = approved_master(master, applied)
    texts = {b.id: b.text for b in result.blocks}
    if any(texts[i['block_id']] != i['suggested_text'] for i in applied):
        raise ValueError('빠른 교정의 원본 보호 검사에 실패했습니다.')
    return result, {'policy': 'limited-corrections-v1', 'applied': applied, 'retained': retained,
                    'applied_count': len(applied), 'retained_count': len(retained)}
