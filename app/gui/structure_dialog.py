from __future__ import annotations

import copy
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont
from app.gui.controls import ClickComboBox
from PySide6.QtWidgets import (QCheckBox, QDialog, QFormLayout, QHBoxLayout, QLabel,
                               QLineEdit, QMessageBox, QPushButton, QSplitter, QTextEdit,
                               QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)
from app.workers.task import TaskThread
from core.manuscript.structure import LEVELS, node, propose_ai, propose_rules, validate


class StructureDialog(QDialog):
    def __init__(self, job, model, reasoning, parent=None):
        super().__init__(parent)
        self.job, self.master = job, job.master()
        self.model, self.reasoning = model, reasoning
        self.store = job.structure()
        self.thread = None
        self.nodes = []
        self.dirty = False
        self.setWindowTitle("장·절·소단원 구성")
        self.resize(1120, 780)
        layout = QVBoxLayout(self)
        help_text = QLabel("기본 분석 또는 AI 분석 → 목차와 본문 확인 → 항목 수정 → 구조 승인\n원문과 코드는 바뀌지 않습니다. 새 제목은 본문 앞에 추가합니다. 승인한 구조만 결과물에 반영됩니다.")
        help_text.setWordWrap(True)
        layout.addWidget(help_text)
        self.controls = QWidget()
        controls = QHBoxLayout(self.controls)
        basic = QPushButton("기본 분석 (무료)")
        basic.clicked.connect(self.rules)
        controls.addWidget(basic)
        self.mode = ClickComboBox()
        self.mode.addItem("기존 제목 분류", "existing")
        self.mode.addItem("제목 없는 본문에 새 제목도 제안", "create")
        controls.addWidget(self.mode)
        ai = QPushButton("AI 구조 분석")
        ai.clicked.connect(self.ai)
        controls.addWidget(ai)
        controls.addWidget(QLabel(f"기술 검토 모델: {model} / {reasoning}"))
        layout.addWidget(self.controls)
        self.status = QLabel("아직 승인된 구조가 없습니다.")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        split = QSplitter()
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["목차", "시작 → 끝"])
        self.tree.setColumnWidth(0, 320)
        self.tree.currentItemChanged.connect(self.selected)
        split.addWidget(self.tree)
        self.preview = QTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setFont(QFont("Consolas", 10))
        split.addWidget(self.preview)
        split.setSizes([500, 600])
        layout.addWidget(split, 1)
        self.editor = QWidget()
        form = QFormLayout(self.editor)
        self.level = ClickComboBox()
        for value, label in LEVELS.items():
            self.level.addItem(label, value)
        form.addRow("수준", self.level)
        self.anchor = ClickComboBox()
        for b in self.master.blocks:
            self.anchor.addItem(f"{b.id} · {b.text[:85] or '[' + b.kind + ']'}", b.id)
        self.anchor.currentIndexChanged.connect(self.anchor_changed)
        form.addRow("시작 문단", self.anchor)
        self.source_title = QCheckBox("이 문단의 원문을 제목으로 사용")
        self.source_title.toggled.connect(self.anchor_changed)
        form.addRow(self.source_title)
        self.title_edit = QLineEdit()
        self.title_edit.setMaxLength(240)
        form.addRow("제목", self.title_edit)
        buttons = QHBoxLayout()
        for label, callback in (("선택 항목 수정", self.edit), ("항목 추가", self.add), ("선택 항목 삭제", self.remove)):
            button = QPushButton(label)
            button.clicked.connect(callback)
            buttons.addWidget(button)
        form.addRow(buttons)
        layout.addWidget(self.editor)
        self.bottom = QWidget()
        row = QHBoxLayout(self.bottom)
        for label, callback in (("초안 저장", self.save_draft), ("구조 승인 및 저장", self.approve), ("닫기", self.reject)):
            button = QPushButton(label)
            button.clicked.connect(callback)
            row.addWidget(button)
        layout.addWidget(self.bottom)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.elapsed = 0
        try:
            saved = self.store.load()
        except (ValueError, OSError):
            saved = None
            self.status.setText("저장된 구조를 현재 원고에 적용할 수 없습니다. 기본/AI 분석 후 새로 승인하세요.")
        if saved:
            self.nodes = saved["nodes"]
            self.status.setText("저장된 구조: " + ("승인됨" if saved["status"] == "approved" else "초안 · 승인 필요"))
            self.refresh()

    def tick(self):
        self.elapsed += 1
        self.status.setText(f"AI 구조 분석 중 · {self.elapsed}초 · 결과를 받은 뒤 검토가 필요합니다.")

    def anchor_changed(self, *_):
        self.title_edit.setEnabled(not self.source_title.isChecked())
        if self.source_title.isChecked():
            self.title_edit.setText(self.master.blocks[self.anchor.currentIndex()].text)

    def selected(self, item, *_):
        if item is None:
            return
        n = self.nodes[item.data(0, Qt.UserRole)]
        self.source_title.setChecked(False)
        self.level.setCurrentIndex(n["level"] - 1)
        self.anchor.setCurrentIndex(self.anchor.findData(n["start_block_id"]))
        self.title_edit.setText(n["title"])
        self.source_title.setChecked(n["use_source_title"])
        positions = {b.id: i for i, b in enumerate(self.master.blocks)}
        blocks = self.master.blocks[positions[n["start_block_id"]]:positions[n["end_block_id"]]+1]
        text = "분류 근거: " + n.get("evidence", "") + "\n\n"
        text += "\n\n".join(f"[{b.id} · {b.kind}]\n" + ("\n".join("\t".join(row) for row in b.rows) if b.kind == "table" else b.text) + (f"\n[이미지 {len(b.assets)}개]" if b.assets else "") for b in blocks)
        self.preview.setPlainText(text)

    def refresh(self):
        self.tree.clear()
        parents = {}
        for index, n in enumerate(self.nodes):
            item = QTreeWidgetItem([f'{LEVELS[n["level"]]} · {n["title"]}', f'{n["start_block_id"]} → {n["end_block_id"]}'])
            item.setData(0, Qt.UserRole, index)
            item.setToolTip(0, n.get("evidence", ""))
            if n["parent_id"]:
                parents[n["parent_id"]].addChild(item)
            else:
                self.tree.addTopLevelItem(item)
            parents[n["id"]] = item
        self.tree.expandAll()
        if self.nodes:
            self.tree.setCurrentItem(self.tree.topLevelItem(0))

    def replace(self, nodes):
        try:
            self.nodes = validate(self.master, nodes)
        except ValueError as exc:
            QMessageBox.warning(self, "구조 확인", str(exc))
            return False
        self.dirty = True
        self.status.setText(f"구조 초안 {len(self.nodes)}개 · 항목과 범위를 확인한 뒤 승인하세요.")
        self.refresh()
        return True

    def rules(self):
        self.replace(propose_rules(self.master))

    def edited_node(self):
        result = node(self.master.blocks[self.anchor.currentIndex()], self.level.currentData(),
                      None if self.source_title.isChecked() else self.title_edit.text())
        return result

    def edit(self):
        item = self.tree.currentItem()
        if item:
            nodes = copy.deepcopy(self.nodes)
            nodes[item.data(0, Qt.UserRole)] = self.edited_node()
            self.replace(nodes)

    def add(self):
        nodes = copy.deepcopy(self.nodes) + [self.edited_node()]
        indices = {b.id: i for i, b in enumerate(self.master.blocks)}
        nodes.sort(key=lambda n: (indices[n["start_block_id"]], n["level"]))
        self.replace(nodes)

    def remove(self):
        item = self.tree.currentItem()
        if item:
            nodes = copy.deepcopy(self.nodes)
            nodes.pop(item.data(0, Qt.UserRole))
            self.replace(nodes)

    def persist(self, approved):
        try:
            current = self.tree.currentItem()
            if current:
                index = current.data(0, Qt.UserRole)
                edited = self.edited_node()
                if any(edited[k] != self.nodes[index][k] for k in ("level", "start_block_id", "title", "use_source_title")):
                    nodes = copy.deepcopy(self.nodes)
                    nodes[index] = edited
                    self.nodes = validate(self.master, nodes)
                    self.refresh()
            self.store.save(self.nodes, approved)
        except (ValueError, OSError) as exc:
            QMessageBox.warning(self, "구조 저장", str(exc))
            return False
        self.dirty = False
        self.status.setText("구조 승인 완료 · 다음 결과물 제작에 반영됩니다." if approved else "초안 저장 완료 · 제작 전 구조 승인이 필요합니다.")
        return True

    def save_draft(self):
        self.persist(False)

    def approve(self):
        if self.persist(True):
            self.accept()

    def ai(self):
        if self.thread is not None:
            return
        if QMessageBox.question(self, "AI 구조 분석", f"{self.model} 모델로 원고 구조를 분석합니다. API 비용이 발생합니다.\n코드·표·그림 내용은 보내지 않습니다. 기존 화면의 초안은 새 제안으로 바뀝니다.\n계속할까요?") != QMessageBox.Yes:
            return
        mode = self.mode.currentData()
        for widget in (self.controls, self.editor, self.bottom):
            widget.setEnabled(False)
        self.elapsed = 0
        self.timer.start(1000)
        self.tick()
        self.thread = TaskThread(lambda: propose_ai(self.job.root, self.master, self.model, self.reasoning, mode))
        self.thread.completed.connect(self.replace)
        self.thread.failed.connect(self.failure)
        self.thread.finished.connect(self.finished_task)
        self.thread.start()

    def failure(self, message):
        self.status.setText("AI 구조 분석 실패 · 기존 초안을 유지합니다.")
        QMessageBox.warning(self, "구조 분석 실패", message)

    def finished_task(self):
        self.timer.stop()
        thread = self.thread
        self.thread = None
        thread.deleteLater()
        for widget in (self.controls, self.editor, self.bottom):
            widget.setEnabled(True)

    def reject(self):
        if self.thread is not None:
            return
        if self.dirty and QMessageBox.question(self, "저장하지 않은 구조", "저장하지 않은 초안을 닫을까요? 마지막 저장 상태는 유지됩니다.") != QMessageBox.Yes:
            return
        super().reject()

    def closeEvent(self, event):
        event.ignore()
        self.reject()
