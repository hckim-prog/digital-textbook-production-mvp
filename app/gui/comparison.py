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
        note = QLabel('모든 선택 모델의 실행 결과를 아래에서 확인하세요. 수정 제안의 승인·거절은 비교 평가용으로 저장됩니다.')
        note.setWordWrap(True)
        layout.addWidget(note)
        self.model_results = QTableWidget(0, 5)
        self.model_results.setHorizontalHeaderLabels(['모델', '실행 결과', '검토 문단', '수정 제안', '승인률'])
        self.model_results.setEditTriggers(QAbstractItemView.NoEditTriggers)
        for col, width in enumerate((180, 230, 100, 100, 140)):
            self.model_results.setColumnWidth(col, width)
        layout.addWidget(self.model_results)
        layout.addWidget(QLabel('수정 제안 · 제안이 있는 항목만 표시합니다. 제안 0건은 원문이 완벽하다는 뜻은 아닙니다.'))
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
        self.model_results.setRowCount(len(rows))
        self.model_results.setFixedHeight(min(220, 44 + 32 * len(rows)))
        for index, result in enumerate(rows):
            count = int(result.get('suggestions', 0))
            status = ('검토 완료' if result.get('sample_count', 0) else '검토 대상 없음') if result.get('success') else '호출 실패 포함'
            rate = '제안 없음' if not count else str(result.get('approval_rate', '미검토'))
            if isinstance(result.get('approval_rate'), (int, float)) and count:
                rate += '%'
            for col, value in enumerate((result['model_id'], status, result.get('sample_count', 0), f'{count}건', rate)):
                self.model_results.setItem(index, col, QTableWidgetItem(str(value)))
            self.model_results.setRowHeight(index, 32)
        self.summary.setText('수정 제안을 선택해 승인·거절·보류로 평가하세요. 비교 평가는 본 원고에 적용되지 않습니다.'
                             if items else '표시할 수정 제안이 없습니다. 모델별 실행 결과는 위 표에서 확인하세요.')

    def decide(self, status):
        selected = [self.keys[index.row()] for index in self.table.selectionModel().selectedRows()]
        review(self.folder, selected, status)
        self.reload()
