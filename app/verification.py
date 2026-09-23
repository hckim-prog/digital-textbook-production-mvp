"""Explicit acceptance mode for checking the frozen application on this PC."""
import json
import sys
import time
from pathlib import Path

from PySide6.QtCore import QSettings, QTimer
from PySide6.QtWidgets import QScrollArea

from core.ai.service import connection_test


def run_verification(app, root):
    import app.gui.window as gui
    audit = root / 'reports/publisher-audit'
    audit.mkdir(parents=True, exist_ok=True)
    prefs = audit / 'exe-verification.ini'
    gui.QSettings = lambda *_: QSettings(str(prefs), QSettings.IniFormat)
    window = gui.MainWindow(root)
    window.depth_existing.setChecked(True)
    window.quick_mode.setChecked(False)
    window.quick_ai.setChecked(False)
    window.detail_toggle.setChecked(True)
    window.show()
    window.source_edit.setText(str(next((root / 'input/chapter-01').glob('*.docx'))))
    state = {'stage': 0, 'started': time.monotonic(), 'api': None}
    report = {'frozen': bool(getattr(sys, 'frozen', False)), 'executable': sys.executable}

    def failed(message):
        window.timer.stop()
        window.busy = False
        report['error'] = message
        state['stage'] = -1
    window._failed = failed

    def finish(success):
        report['passed'] = success
        report['elapsed_seconds'] = round(time.monotonic() - state['started'], 2)
        (audit / 'exe-acceptance.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        window.verification_timer.stop()
        window.close()
        app.exit(0 if success else 1)

    def tick():
        try:
            if window.busy or window.prepare_timer.isActive() or any(t.isRunning() for t in window.threads):
                return
            if state['stage'] == -1:
                finish(False)
            elif state['stage'] == 0:
                assert window.proofread_button.isEnabled(), '자동 원고 준비 실패'
                report['preparation'] = window.analysis_info.text()
                report['review_summary'] = window.review_summary.text()
                state['stage'] = 1
                if '--verify-api' in sys.argv:
                    window.run_task('배포본 API 연결 검사 중', lambda: connection_test(root, 'gpt-5.6-luna', 'none'),
                                    lambda value: report.update(api=value))
            elif state['stage'] == 1:
                # Allow queued completion/cleanup events before the next task.
                state['stage'] = 2
                state['api_finished'] = time.monotonic()
            elif state['stage'] == 2 and time.monotonic() - state['api_finished'] > 2:
                folder = root / 'output/exe-acceptance'
                folder.mkdir(exist_ok=True)
                window.output_edit.setText(str(folder))
                window.build_button.click()
                state['stage'] = 3
            elif state['stage'] == 3:
                result = window.production().last_result()
                assert result['qa']['passed'], '배포본 출력 품질 검사 실패'
                assert window.qa_button.isEnabled() and window.open_output_button.isEnabled()
                report.update(result=result, status=window.status.text())
                window.grab().save(str(audit / 'exe-top.png'))
                scroll = window.findChild(QScrollArea)
                scroll.verticalScrollBar().setValue(scroll.verticalScrollBar().maximum())
                state['stage'] = 4
            elif state['stage'] == 4:
                window.grab().save(str(audit / 'exe-results.png'))
                finish(True)
        except Exception as exc:
            failed(type(exc).__name__ + ': ' + str(exc))

    window.verification_timer = QTimer(window)
    window.verification_timer.timeout.connect(tick)
    window.verification_timer.start(100)
    app.verification_window = window
    return app.exec()
