import json
import shutil
import time
from pathlib import Path
from threading import Event

import pytest
from docx import Document
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from app.controllers.production import Production
from app.controllers.publishing import publish
from core.cancellation import OperationCancelled


def make_job(tmp_path):
    root = tmp_path / 'project'
    shutil.copytree(Path(__file__).resolve().parents[1] / 'config', root / 'config')
    source = tmp_path / '원고.docx'
    doc = Document()
    for text in ['Chapter 1 시작', '1.1 첫 번째 주제', '첫 본문입니다.', '1.2 두 번째 주제', '다음 본문입니다.']:
        doc.add_paragraph(text)
    doc.save(source)
    job = Production(root, source)
    job.analyze()
    return job


def test_boolean_cancel_argument_rejected(tmp_path):
    job = make_job(tmp_path)
    with pytest.raises(ValueError, match='확인 함수'):
        publish(job, ['web'], cancelled=False)


@pytest.mark.parametrize('phase', ['HTML 제작 중', 'PDF 제작 중', 'EPUB 제작 중', '결과물 품질 확인 중'])
def test_output_cancellation_not_recorded_as_success_and_restart(tmp_path, phase):
    job = make_job(tmp_path)
    stop = Event()
    def progress(info):
        if info['phase'] == phase:
            stop.set()
    with pytest.raises(OperationCancelled):
        publish(job, ['web', 'pdf', 'epub'], progress=progress, cancelled=stop.is_set)
    assert job.last_result() is None
    reports = list(job.default_output_base.glob('*/reports/production-state.json'))
    assert len(reports) == 1
    assert json.loads(reports[0].read_text(encoding='utf-8'))['status'] == 'cancelled'
    stop.clear()
    result = publish(job, ['web'], cancelled=stop.is_set)
    assert result['qa']['passed']
    assert Path(result['folder']) != reports[0].parent.parent


def test_pdf_cancels_inside_layout(tmp_path, monkeypatch):
    from core.export.outputs import pdf
    from core.export.preview import sample_master
    from core.export.pdf_layout import CodeBlock
    stop = Event()
    original_draw = CodeBlock.draw
    def draw_and_stop(block):
        original_draw(block)
        stop.set()
    monkeypatch.setattr(CodeBlock, 'draw', draw_and_stop)
    with pytest.raises(OperationCancelled):
        pdf(sample_master(), tmp_path / 'assets', tmp_path / 'pdf', cancelled=stop.is_set)


def test_quick_stop_button_saves_current_reply_and_resumes(tmp_path, monkeypatch):
    import app.gui.window as gui
    from core.ai import service
    job = make_job(tmp_path)
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(gui, 'QSettings', lambda *_: QSettings(str(tmp_path / 'prefs.ini'), QSettings.IniFormat))
    errors = []
    monkeypatch.setattr(gui.QMessageBox, 'warning', lambda *args: errors.append(args[-1]))
    entered, release = Event(), Event()
    requests = []
    def response(root, model, reasoning, prompt):
        requests.append(prompt)
        if len(requests) == 1:
            entered.set()
            assert release.wait(5), 'UI did not finish issuing cancellation'
        return {'suggestions': []}, {'model': model, 'input_tokens': 1, 'output_tokens': 1, 'elapsed_seconds': .1}
    monkeypatch.setattr(service, '_response', response)
    monkeypatch.setattr(service, 'record', lambda *args: None)
    monkeypatch.setattr(service, 'cost', lambda *args: .001)
    win = gui.MainWindow(job.root)
    win.depth_existing.setChecked(True)
    win.source_edit.setText(str(job.source))
    win.prepare_timer.stop()
    win._analysis_done(job, job.master())
    for kind, box in win.format_boxes.items():
        box.setChecked(kind == 'web')
    def wait_until(predicate):
        deadline = time.monotonic() + 10
        while not predicate() and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(.005)
        assert predicate()
    try:
        win.build()
        wait_until(entered.is_set)
        assert win.quick_stop.isEnabled()
        win.quick_stop.click()
        assert not win.quick_stop.isEnabled()
        assert '중단 요청됨' in win.status.text()
        win._phase_progress({'phase': 'late progress', 'percent': 25})
        assert '중단 요청됨' in win.status.text()
        release.set()
        wait_until(lambda: not win.busy and not any(t.isRunning() for t in win.threads))
        assert requests and len(requests) == 1
        assert not errors and win.resume_build
        assert win.build_button.text() == '이어서 제작'
        assert '중단 및 저장 완료' in win.status.text()
        assert job.last_result() is None
        win.build_button.click()
        wait_until(lambda: not win.busy and not any(t.isRunning() for t in win.threads))
        assert not errors and not win.resume_build
        assert job.last_result()['qa']['passed']
        # Completed first paragraph was not sent a second time.
        assert requests.count(requests[0]) == 1
    finally:
        release.set()
        wait_until(lambda: not any(t.isRunning() for t in win.threads))
        win.close()
