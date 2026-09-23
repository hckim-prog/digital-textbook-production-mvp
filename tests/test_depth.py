import copy
import json
import shutil
from pathlib import Path
from dataclasses import asdict

import pytest
from docx import Document
from lxml import html

from app.controllers.production import Production
from app.controllers.publishing import publish
from core.manuscript import depth
from core.manuscript.structure import propose_rules


def job_for(tmp_path):
    source = tmp_path / '교재.docx'
    doc = Document()
    for text in ['Chapter 1 시작', '1.1 여러 학습 주제', '컴파일 오류의 개념과 수정 방법을 설명합니다.',
                 '실행 중 발생하는 오류와 점검 방법을 설명합니다.', '별도 연습 예제로 확인합니다.',
                 '1.2 짧은 정리', '정리 문장입니다.']:
        doc.add_paragraph(text)
    doc.save(source)
    job = Production(tmp_path / 'project', source)
    job.analyze()
    return job


@pytest.mark.parametrize('maximum', [3, 4])
def test_auto_depth_direct_exports_cache_and_no_approval(tmp_path, monkeypatch, maximum):
    job = job_for(tmp_path)
    master = job.master()
    before = asdict(master)
    nodes = propose_rules(master)
    job.structure().save(nodes, approved=False)
    saved = (job.work / 'structure.json').read_bytes()
    calls = []
    def response(root, model, reasoning, prompt):
        calls.append(prompt)
        extra = [{'level': 3, 'start_block_id': 'b00003', 'title': '오류의 이해', 'evidence': '독립적인 오류 설명'}]
        if maximum == 4:
            extra += [{'level': 4, 'start_block_id': 'b00003', 'title': '컴파일 오류', 'evidence': '컴파일 단계 개념'},
                      {'level': 4, 'start_block_id': 'b00004', 'title': '실행 오류', 'evidence': '실행 시점으로 설명 대상 변경'}]
        return {'nodes': extra if len(calls) == 1 else []}, {'model': model}
    monkeypatch.setattr(depth, '_response', response)
    monkeypatch.setattr(depth, 'record', lambda *args: None)
    built = publish(job, ['web', 'pdf', 'epub'], depth_mode=True, max_depth=maximum, structure_model='fixture')
    assert built['qa']['passed'], built['qa']['checks']
    result = json.loads((job.work / 'ai-depth-final.json').read_text(encoding='utf-8'))
    assert result['added_3'] == 1 and result['added_4'] == (2 if maximum == 4 else 0)
    tree = html.parse(built['outputs']['web'])
    assert len(tree.xpath('//h4')) == (2 if maximum == 4 else 0)
    assert len(tree.xpath('//nav//ol/ol')) == 0  # Valid nested lists use li wrappers.
    assert asdict(job.master()) == before
    assert (job.work / 'structure.json').read_bytes() == saved
    publish(job, ['web'], depth_mode=True, max_depth=maximum, structure_model='fixture')
    assert len(calls) == 2  # Completed sections are reused, including empty results.


@pytest.mark.parametrize('extra,maximum', [
    ([{'level':4,'start_block_id':'b00003','title':'고아 Topic','evidence':'이유'}],4),
    ([{'level':3,'start_block_id':'b00007','title':'다른 Section','evidence':'이유'}],4),
    ([{'level':3,'start_block_id':'b00002','title':'기존 제목 덮기','evidence':'이유'}],4),
    ([{'level':4,'start_block_id':'b00003','title':'범위 초과','evidence':'이유'}],3),
    ([{'level':5,'start_block_id':'b00003','title':'범위 초과','evidence':'이유'}],4),
])
def test_invalid_depth_rejected(tmp_path, extra, maximum):
    job = job_for(tmp_path)
    base = propose_rules(job.master())
    with pytest.raises(ValueError):
        depth.merge_section(job.master(), base, base[1], extra, maximum)


def test_gui_default_and_existing_structure_option(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import QSettings
    import app.gui.window as gui
    shutil.copytree(Path(__file__).resolve().parents[1] / 'config', tmp_path / 'config')
    monkeypatch.setattr(gui, 'QSettings', lambda *_: QSettings(str(tmp_path / 'prefs.ini'), QSettings.IniFormat))
    app = QApplication.instance() or QApplication([])
    win = gui.MainWindow(tmp_path)
    assert win.depth_ai.isChecked() and win.max_depth.currentData() == 4
    win.depth_existing.setChecked(True)
    assert not win.max_depth.isEnabled()
    win.close()
