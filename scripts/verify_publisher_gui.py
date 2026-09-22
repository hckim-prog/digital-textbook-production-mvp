"""Interactive-window acceptance run using real Chapter 1 and a small paid sample."""
import json
import shutil
import sys
import time
from pathlib import Path

if '--paid-sample' not in sys.argv:
    raise SystemExit('유료 검증은 --paid-sample을 명시해야 합니다. 무료 순차 검증: main.py --verify-review-flow')

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from PySide6.QtCore import QSettings
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication, QMessageBox
import app.gui.window as gui

AUDIT = ROOT / 'reports/publisher-audit'
AUDIT.mkdir(parents=True, exist_ok=True)
app = QApplication([])
app.setFont(QFont('Malgun Gothic', 9))
gui.QSettings = lambda *_: QSettings(str(AUDIT/'acceptance-prefs.ini'), QSettings.IniFormat)
win = gui.MainWindow(ROOT)
win.show()
errors = []
QMessageBox.warning = lambda *args: errors.append(args[-1])
QMessageBox.question = lambda *args: QMessageBox.Yes


def wait_idle(timeout=240):
    deadline = time.monotonic() + timeout
    while win.busy or win.prepare_timer.isActive() or any(t.isRunning() for t in win.threads):
        app.processEvents()
        if time.monotonic() > deadline:
            raise TimeoutError(win.status.text())
        time.sleep(.02)
    app.processEvents()
    if errors:
        raise RuntimeError(errors)


source = next((ROOT/'input/chapter-01').glob('*.docx'))
gui.QFileDialog.getOpenFileName = lambda *args: (str(source), '')
win.browse_button.click()
wait_idle()
assert win.proofread_button.isEnabled() and win.build_button.isEnabled()
assert '원고 준비 완료' in win.analysis_info.text()
job = win.production()
if (job.work/'suggestions.json').is_file():
    shutil.copy2(job.work/'suggestions.json', AUDIT/'suggestions-before-acceptance.json')
win.model_boxes['proofreading'].setCurrentIndex(win.model_boxes['proofreading'].findData('gpt-5.6-luna'))
win.scope.setCurrentIndex(win.scope.findData('sample'))
win.limit.setValue(5)
win.proofread_button.click()
wait_idle()
(AUDIT/'ai-suggestions-for-review.json').write_text(json.dumps(job.suggestions(), ensure_ascii=False, indent=2), encoding='utf-8')
print('AI_READY', win.status.text(), flush=True)
decision_file = AUDIT/'acceptance-decisions.json'
deadline = time.monotonic() + 300
while not decision_file.is_file():
    app.processEvents()
    if time.monotonic() > deadline:
        raise TimeoutError('검토 선택 파일 대기 시간 초과')
    time.sleep(.1)
for decision in json.loads(decision_file.read_text(encoding='utf-8')):
    row = next(i for i in range(win.table.rowCount()) if win.table.item(i,0).text() == decision['id'])
    win.table.selectRow(row)
    index = ['approved','rejected','hold'].index(decision['status'])
    win.review_buttons[index].click()
destination = ROOT/'output/publisher-acceptance'
destination.mkdir(exist_ok=True)
gui.QFileDialog.getExistingDirectory = lambda *args: str(destination)
win.choose_output_button.click()
win.build_button.click()
wait_idle()
assert win.qa_button.isEnabled() and win.open_output_button.isEnabled()
result = job.last_result()
assert result['qa']['passed'], result['qa']
win.grab().save(str(AUDIT/'gui-top.png'))
from PySide6.QtWidgets import QScrollArea
scroll = win.findChild(QScrollArea)
scroll.verticalScrollBar().setValue(scroll.verticalScrollBar().maximum())
app.processEvents()
win.grab().save(str(AUDIT/'gui-results.png'))
win.qa_button.click()
win.open_output_button.click()
result['gui_status'] = win.status.text()
result['review_summary'] = win.review_summary.text()
result['model'] = win.model_boxes['proofreading'].currentData()
result['preparation'] = win.analysis_info.text()
(AUDIT/'gui-acceptance.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
print('GUI_PASS', result['folder'], flush=True)
win.close()
