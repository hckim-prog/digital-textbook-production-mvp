"""Exercise the real Stop/Resume buttons with delayed local API fixtures."""
import json
import shutil
import sys
import time
from threading import Event
from uuid import uuid4

from docx import Document
from PySide6.QtCore import QSettings, QTimer
from PySide6.QtWidgets import QMessageBox, QScrollArea


def run(app, root):
    import app.gui.window as gui
    from core.ai import service
    audit = root / 'reports/cancellation-verification'
    sandbox = audit / ('run-' + uuid4().hex[:8])
    shutil.copytree(root / 'config', sandbox / 'config')
    source = sandbox / '중단 재개 시험.docx'
    doc = Document()
    for text in ['Chapter 1 시작', '1.1 첫 절', '첫 본문입니다.', '1.2 다음 절', '다음 본문입니다.']:
        doc.add_paragraph(text)
    doc.save(source)
    gui.QSettings = lambda *_: QSettings(str(sandbox / 'prefs.ini'), QSettings.IniFormat)
    win = gui.MainWindow(sandbox)
    win.depth_existing.setChecked(True)
    win.setWindowTitle('중단·재개 검증 · 유료 API 호출 없음')
    entered, release = Event(), Event()
    requests = []
    report = {'passed': False, 'frozen': bool(getattr(sys, 'frozen', False)), 'api_mode': 'delayed_fixture_no_paid_calls'}
    state = {'stage': 0, 'started': time.monotonic()}
    def fake_response(root, model, reasoning, prompt):
        requests.append(prompt)
        if len(requests) == 1:
            entered.set()
            if not release.wait(10):
                raise RuntimeError('중단 버튼 시험 시간 초과')
        return {'suggestions': []}, {'model': model, 'input_tokens': 1, 'output_tokens': 1, 'elapsed_seconds': .1}
    service._response = fake_response
    service.record = lambda *args: None
    service.cost = lambda *args: 0
    def fail(message):
        report['error'] = str(message)
        release.set()
        state['stage'] = -1
    QMessageBox.warning = lambda *args: fail(args[-1])
    def finish(passed):
        report.update(passed=passed, request_count=len(requests))
        (audit / 'acceptance.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        win.verification_timer.stop()
        win.close()
        app.exit(0 if passed else 1)
    def tick():
        try:
            running = win.busy or win.prepare_timer.isActive() or any(t.isRunning() for t in win.threads)
            if time.monotonic() - state['started'] > 25 and state['stage'] != -1:
                fail('중단·재개 검증 시간 초과')
            if state['stage'] == -1:
                if not running:
                    finish(False)
            elif state['stage'] == 0 and not running:
                win.build_button.click()
                state['stage'] = 1
            elif state['stage'] == 1 and entered.is_set():
                assert win.quick_stop.isEnabled()
                win.quick_stop.click()
                assert not win.quick_stop.isEnabled()
                win._phase_progress({'phase': '지연된 진행 알림', 'percent': 20})
                assert '중단 요청됨' in win.status.text()
                release.set()
                state['stage'] = 2
            elif state['stage'] == 2 and not running:
                assert len(requests) == 1 and win.resume_build
                assert win.build_button.text() == '이어서 제작'
                assert '중단 및 저장 완료' in win.status.text()
                assert win.production().last_result() is None
                win.findChild(QScrollArea).ensureWidgetVisible(win.quick_stop)
                win.grab().save(str(audit / 'stopped.png'))
                report['stop_saved_without_failure'] = True
                win.build_button.click()
                state['stage'] = 3
            elif state['stage'] == 3 and not running:
                assert win.production().last_result()['qa']['passed']
                assert requests.count(requests[0]) == 1
                assert not win.resume_build
                report['resume_skips_completed_paragraph'] = True
                finish(True)
        except Exception as exc:
            fail(type(exc).__name__ + ': ' + str(exc))
    win.source_edit.setText(str(source))
    win.show()
    win.verification_timer = QTimer(win)
    win.verification_timer.timeout.connect(tick)
    win.verification_timer.start(50)
    app.verification_window = win
    return app.exec()
