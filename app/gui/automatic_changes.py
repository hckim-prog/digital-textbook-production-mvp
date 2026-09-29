"""Optional review and output-only rollback; never edit manual decisions."""
from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QTableWidget,
                              QTableWidgetItem, QPushButton, QMessageBox, QAbstractItemView)
from core.ai.workflow import read_json, write_json


def show_changes(parent, job, report, output):
    if report.get('source_hash') != job.master().source_hash:
        QMessageBox.warning(parent, '원고 확인', '이 결과물을 만든 원고를 먼저 선택하세요.')
        return
    dialog = QDialog(parent)
    dialog.setWindowTitle('자동 변경 관리')
    dialog.resize(1000, 640)
    layout = QVBoxLayout(dialog)
    notice = QLabel('되돌리기는 문단 단위입니다. 저장 후 자동 출판을 다시 실행하면 해당 문단은 기존 승인본으로 유지됩니다.\n'
                    '이미 만든 파일은 변경하지 않으며, 새 결과물로 저장합니다. 수동 승인·거절·보류 기록은 유지합니다.')
    notice.setWordWrap(True)
    layout.addWidget(notice)
    items = report['applied']
    table = QTableWidget(len(items), 4)
    table.setHorizontalHeaderLabels(['문단', '수정 전', '자동 수정 후', '검수 이유'])
    table.setEditTriggers(QAbstractItemView.NoEditTriggers)
    table.setSelectionBehavior(QAbstractItemView.SelectRows)
    table.setSelectionMode(QAbstractItemView.ExtendedSelection)
    for row, item in enumerate(items):
        for col, key in enumerate(('block_id','source_text','suggested_text','reason')):
            table.setItem(row,col,QTableWidgetItem(str(item.get(key,''))))
        table.setRowHeight(row,100)
    for col, width in enumerate((90,290,290,230)):
        table.setColumnWidth(col,width)
    layout.addWidget(table)
    buttons = QHBoxLayout()
    path = job.work / 'automatic-exclusions.json'
    def exclude(all_rows=False):
        rows = range(len(items)) if all_rows else {i.row() for i in table.selectionModel().selectedRows()}
        ids = {items[row]['block_id'] for row in rows}
        if not ids:
            notice.setText('되돌릴 행을 먼저 선택하세요.')
            return
        saved = set(read_json(path, [])) | ids
        write_json(path, sorted(saved))
        notice.setText(f'{len(ids)}개 문단을 자동 수정에서 제외했습니다. 창을 닫고 다시 제작하세요.')
    for title, action in [('선택 문단 되돌리기', lambda: exclude()), ('전체 자동 수정 되돌리기', lambda: exclude(True)),
                          ('확인 필요 항목·전체 보고서', lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(output/'reports/quick-changes.html'))))]:
        button = QPushButton(title)
        button.clicked.connect(action)
        buttons.addWidget(button)
    layout.addLayout(buttons)
    restore = QPushButton('되돌리기 설정 해제 · 다음 제작부터 다시 자동 수정')
    def restore_all():
        write_json(path, [])
        notice.setText('자동 수정 제외 설정을 해제했습니다. 다시 제작할 때 적용됩니다.')
    restore.clicked.connect(restore_all)
    layout.addWidget(restore)
    dialog.exec()
