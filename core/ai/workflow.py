"""Versioned, stage-by-stage review; legacy decisions remain read-only."""
from __future__ import annotations

import copy
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
from uuid import uuid4

from core.ai.service import approved_master, proofread, safe_blocks
from core.master import Master

ROLES = ('proofreading', 'technical_review', 'final_review')


def read_json(path, default):
    return json.loads(path.read_text(encoding='utf-8')) if path.is_file() else default


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.' + uuid4().hex + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(path)


def now():
    return datetime.now().isoformat(timespec='seconds')


def change(item, status, reason, actor='user'):
    item.setdefault('history', []).append({'at': now(), 'from': item['status'], 'to': status,
                                          'reason': reason, 'actor': actor})
    item['status'] = status
    item['status_reason'] = reason


def apply_stages(baseline, items, roles=ROLES):
    master = copy.deepcopy(baseline)
    for role in roles:
        stage = [i for i in items if i.get('role', 'proofreading') == role and i['status'] == 'approved']
        by_id = {b.id: b for b in master.blocks}
        seen = set()
        for item in stage:
            block = by_id.get(item['block_id'])
            if not block or block.text != item['source_text'] or block.id in seen:
                raise ValueError('승인한 제안의 기준 문장이 변경됐습니다. 해당 단계를 다시 검토해 주세요.')
            seen.add(block.id)
        master = approved_master(master, stage)
        after = {b.id: b.text for b in master.blocks}
        if any(after[i['block_id']] != i['suggested_text'] for i in stage):
            raise ValueError('원본 보호 규칙에 맞지 않는 승인 제안이 있습니다.')
    return master


class ReviewWorkflow:
    def __init__(self, root: Path, original: Master, work: Path):
        self.root, self.original, self.work = root, original, work
        self.folder = work / 'review-v2'

    @property
    def active(self):
        return (self.folder / 'workflow.json').is_file()

    def legacy(self):
        return read_json(self.folder / 'legacy-decisions.json' if self.active else self.work / 'suggestions.json', [])

    def items(self):
        return read_json(self.folder / 'suggestions.json', [])

    def baseline(self):
        if self.active:
            return Master.load(self.folder / 'baseline.json')
        legacy = self.legacy()
        result = approved_master(self.original, legacy)
        texts = {b.id: b.text for b in result.blocks}
        if any(texts.get(i['block_id']) != i['suggested_text'] for i in legacy if i['status'] == 'approved'):
            raise ValueError('기존 승인 기록 중 원고와 맞지 않는 항목이 있습니다. 원고와 이전 검토 기록을 확인해 주세요.')
        return result

    def start(self):
        if self.active:
            return
        baseline = self.baseline()
        self.folder.mkdir(parents=True, exist_ok=True)
        baseline.save(self.folder / 'baseline.json')
        write_json(self.folder / 'legacy-decisions.json', self.legacy())
        write_json(self.folder / 'suggestions.json', [])
        write_json(self.folder / 'workflow.json', {'version': 2, 'created': now(),
                   'source_hash': self.original.source_hash,
                   'baseline_approved_count': sum(i['status'] == 'approved' for i in self.legacy())})

    def input_master(self, role):
        if role not in ROLES:
            raise ValueError('검토 단계를 확인해 주세요.')
        return apply_stages(self.baseline(), self.items(), ROLES[:ROLES.index(role)])

    def output_master(self):
        return apply_stages(self.baseline(), self.items())

    @staticmethod
    def key(block, role, model, reasoning):
        return '|'.join((role, model, reasoning, block.id, sha256(block.text.encode('utf-8')).hexdigest()))

    def plan(self, role, model, reasoning, limit=None, repeat=False):
        master = self.input_master(role)
        eligible = safe_blocks(master, None)
        runs = read_json(self.folder / 'runs.json', [])
        completed = {key for run in runs for key in run.get('completed_keys', [])
                     if key not in run.get('invalidated_keys', [])}
        pending = [b for b in eligible if repeat or self.key(b, role, model, reasoning) not in completed]
        selected = pending[:limit]
        return {'master': master, 'blocks': selected, 'eligible': len(eligible),
                'already_reviewed': len(eligible) - len(pending), 'target_count': len(selected),
                'remaining': len(pending) - len(selected)}

    def run(self, model, reasoning, limit=None, progress=None, role='proofreading', repeat=False, cancelled=None):
        self.start()
        plan = self.plan(role, model, reasoning, limit, repeat)
        run_id = uuid4().hex
        run_folder = self.folder / 'runs' / run_id
        run_folder.mkdir(parents=True)
        plan['master'].save(run_folder / 'input-master.json')
        selected = Master(self.original.title, self.original.source_name, self.original.source_hash, plan['blocks'])
        items, calls = proofread(self.root, selected, model, reasoning, None, progress, role, cancelled=cancelled)
        existing = self.items()
        # Identical rejected/held proposals keep their decisions when rerunning.
        known = {(s['role'], s['block_id'], s['source_text'], s['suggested_text'], s.get('model'))
                 for s in existing if s['status'] != 'outdated'}
        added = 0
        for item in items:
            signature = (role, item['block_id'], item['source_text'], item['suggested_text'], model)
            if signature not in known:
                item.update(id='r' + uuid4().hex[:16], role=role, run_id=run_id, created=now())
                existing.append(item)
                known.add(signature)
                added += 1
        write_json(self.folder / 'suggestions.json', existing)
        by_id = {b.id: b for b in plan['blocks']}
        succeeded = [c for c in calls if c.get('success')]
        failures = [c for c in calls if not c.get('success')]
        run = {'id': run_id, 'role': role, 'model': model, 'reasoning': reasoning, 'created': now(),
               'target_count': plan['target_count'], 'success_count': len(succeeded),
               'failure_count': len(failures), 'unprocessed_count': plan['target_count'] - len(calls),
               'completed_keys': [self.key(by_id[c['block_id']], role, model, reasoning) for c in succeeded],
               'calls': calls, 'new_count': added, 'cancelled': bool(cancelled and cancelled())}
        runs = read_json(self.folder / 'runs.json', [])
        write_json(self.folder / 'runs.json', runs + [run])
        write_json(run_folder / 'result.json', run)
        return {**run, 'suggestion_count': len(existing), 'remaining': plan['remaining']}

    def decide(self, ids, status):
        if status not in ('approved', 'rejected', 'hold'):
            raise ValueError('검토 상태를 확인해 주세요.')
        items = self.items()
        selected = [i for i in items if i['id'] in ids]
        if len(selected) != len(set(ids)):
            raise ValueError('선택한 제안을 찾을 수 없습니다. 목록을 다시 불러와 주세요.')
        pairs = [(i['role'], i['block_id']) for i in selected]
        if status == 'approved' and len(set(pairs)) != len(pairs):
            raise ValueError('같은 단계의 같은 문단에 대한 제안을 동시에 승인할 수 없습니다. 적용할 제안 하나를 선택해 주세요.')
        for item in selected:
            if item['status'] == 'outdated':
                raise ValueError('기준 문장이 바뀐 제안입니다. 해당 단계에서 AI 검토를 다시 실행해 주세요.')
            if status == 'approved':
                base = apply_stages(self.baseline(), items, ROLES[:ROLES.index(item['role'])])
                block = next((b for b in base.blocks if b.id == item['block_id']), None)
                if block is None or block.text != item['source_text']:
                    raise ValueError('기준 문장이 바뀌었습니다. 해당 단계를 다시 검토해 주세요.')
                for other in items:
                    if other['id'] != item['id'] and other['role'] == item['role'] and other['block_id'] == item['block_id'] and other['status'] == 'approved':
                        change(other, 'superseded', '다른 제안 승인으로 대체됨: ' + item['id'], 'automatic')
            change(item, status, '사용자가 선택한 검토 상태')
        # A changed earlier stage invalidates only dependent, now-mismatched text.
        base = self.baseline()
        invalidated = set()
        for role in ROLES:
            by_id = {b.id: b for b in base.blocks}
            for item in items:
                if item['role'] == role and item['status'] in ('approved', 'pending', 'hold'):
                    block = by_id.get(item['block_id'])
                    if block is None or block.text != item['source_text']:
                        change(item, 'outdated', '앞 단계 승인 내용이 바뀌었습니다. 이 단계에서 다시 검토하세요.', 'automatic')
                        invalidated.add((role, item['block_id']))
            base = apply_stages(base, items, (role,))
        # Validate before saving so a rejected transaction leaves decisions intact.
        apply_stages(self.baseline(), items)
        if invalidated:
            runs = read_json(self.folder / 'runs.json', [])
            for run in runs:
                keys = set(run.get('invalidated_keys', []))
                keys.update(key for key in run.get('completed_keys', []) if (key.split('|')[0], key.split('|')[3]) in invalidated)
                run['invalidated_keys'] = sorted(keys)
            write_json(self.folder / 'runs.json', runs)
        write_json(self.folder / 'suggestions.json', items)
        return items
