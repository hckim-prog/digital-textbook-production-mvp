import json
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTableWidget, QTableWidgetItem, QAbstractItemView

from core.reporting.comparison import review, refresh


class ComparisonDialog(QDialog):
    def __init__(self, folder: Path, parent=None):
        super().__init__(parent)
        self.folder = folder
        refresh(folder)
        self.setWindowTitle('AI 모델 비교 · 제안 검토')
        self.resize(1100, 650)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel('모델별 제안을 검토하면 실제 승인률이 보고서에 저장됩니다. 본 원고의 승인 상태와 별도로 관리합니다.'))
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(['모델', '원문', '수정 제안', '이유', '상태'])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        for col, width in enumerate((140, 270, 270, 230, 80)):
            self.table.setColumnWidth(col, width)
        layout.addWidget(self.table)
        self.summary = QLabel()
        layout.addWidget(self.summary)
        row = QHBoxLayout()
        for label, state in [('선택 항목 승인', 'approved'), ('선택 항목 거절', 'rejected'), ('선택 항목 보류', 'hold')]:
            button = QPushButton(label)
            button.clicked.connect(lambda _, s=state: self.decide(s))
            row.addWidget(button)
        report = QPushButton('비교 보고서 열기')
        report.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder / 'model-comparison.html'))))
        row.addWidget(report)
        layout.addLayout(row)
        self.reload()

    def reload(self):
        details = json.loads((self.folder / 'model-comparison-details.json').read_text(encoding='utf-8'))
        items = [(model['model_id'], item) for model in details for item in model['suggestions']]
        self.keys = [(model, item['id']) for model, item in items]
        self.table.setRowCount(len(items))
        labels = {'approved': '승인', 'rejected': '거절', 'hold': '보류', 'pending': '미검토'}
        for row, (model, item) in enumerate(items):
            for col, value in enumerate((model, item['source_text'], item['suggested_text'], item['reason'], labels.get(item.get('status'), '미검토'))):
                cell = QTableWidgetItem(value)
                cell.setToolTip(value)
                self.table.setItem(row, col, cell)
            self.table.setRowHeight(row, 90)
        rows = json.loads((self.folder / 'model-comparison-rows.json').read_text(encoding='utf-8'))
        self.summary.setText(' · '.join(f"{r['model_id']}: 승인률 {r.get('approval_rate', '미검토')}" for r in rows))

    def decide(self, status):
        selected = [self.keys[index.row()] for index in self.table.selectionModel().selectedRows()]
        review(self.folder, selected, status)
        self.reload()
