from __future__ import annotations

from pathlib import Path
import time
from threading import Event

from PySide6.QtCore import QSettings, Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDialog, QFileDialog, QFormLayout,
    QGroupBox, QHBoxLayout, QHeaderView, QLayout, QInputDialog, QLabel, QLineEdit, QMainWindow, QMessageBox,
    QPushButton, QProgressBar, QScrollArea, QSpinBox, QTableWidget,
    QTableWidgetItem, QToolButton, QVBoxLayout, QWidget,
)

from app.controllers.production import Production
from app.workers.task import start
from core.ai.service import available_models, connection_test, cost, model_config, settings
from core.reporting.comparison import compare
from app.gui.review_display import (
    SEGMENTS_ROLE, STATUS_ROLE, ReviewTextDelegate, StatusDelegate,
    comparison_dialog, diff_segments,
)


ROLES = (
    ("proofreading", "교정/교열 모델", "맞춤법과 문장 표현을 검토합니다."),
    ("technical_review", "기술 검토 모델", "C++ 내용과 기술 설명을 검토합니다."),
    ("final_review", "최종 검토 모델", "앞 단계 승인문을 바탕으로 문장 명확성·용어·의미를 다시 검토합니다. 자동 승인이나 코드 실행 검사는 하지 않습니다."),
)


class MainWindow(QMainWindow):
    def __init__(self, root: Path):
        super().__init__()
        self.root = root
        self.config = settings(root)
        self.prefs = QSettings("DigitalTextbookMaker", "MVP")
        self.threads = []
        self.busy = False
        self.is_reviewing = False
        self.cancel_review = Event()
        self.analyzed_path = None
        self.last_output_folder = None
        self.last_report = None
        self.task_started = 0.0
        self.progress_base = ""
        self.setWindowTitle("수업 전용 디지털교재 제작")
        self.resize(1080, 850)
        central = QWidget()
        self.setCentralWidget(central)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(14, 12, 14, 12)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setSpacing(14)
        layout.setSizeConstraint(QLayout.SetMinimumSize)
        scroll.setWidget(body)
        outer.addWidget(scroll, 1)
        self._source_step(layout)
        self._model_step(layout)
        self._analysis_step(layout)
        self._review_step(layout)
        self._tools_step(layout)
        self.status = QLabel("준비됨")
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress_details = QLabel("")
        self.status.setWordWrap(True)
        self.progress_details.setWordWrap(True)
        outer.addWidget(self.status)
        outer.addWidget(self.progress)
        outer.addWidget(self.progress_details)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.source_edit.textChanged.connect(self.update_file_info)
        self.table.itemSelectionChanged.connect(self.update_review_buttons)
        self.prepare_timer = QTimer(self)
        self.prepare_timer.setSingleShot(True)
        self.prepare_timer.timeout.connect(self.analyze)
        self.active_role.currentIndexChanged.connect(self._role_changed)
        self.review_filter.currentIndexChanged.connect(self.load_suggestions)
        self.scope.currentIndexChanged.connect(self.update_scope)
        self.limit.valueChanged.connect(self.update_scope)
        self.repeat_review.toggled.connect(self.update_scope)
        self.reasoning.currentTextChanged.connect(self.update_scope)
        self.update_file_info()

    def _source_step(self, layout):
        box = QGroupBox("① 원고 선택")
        form = QVBoxLayout(box)
        row = QHBoxLayout()
        self.source_edit = QLineEdit(str(self.prefs.value("source", "")))
        self.source_edit.setPlaceholderText("DOCX 원고 파일을 선택하세요")
        browse = QPushButton("파일 선택")
        self.browse_button = browse
        browse.clicked.connect(self.browse)
        row.addWidget(QLabel("원고 파일"))
        row.addWidget(self.source_edit, 1)
        row.addWidget(browse)
        form.addLayout(row)
        self.file_info = QLabel()
        form.addWidget(self.file_info)
        self.analysis_info = QLabel("DOCX 원고를 선택하면 자동으로 준비합니다.")
        self.analysis_info.setWordWrap(True)
        form.addWidget(self.analysis_info)
        self.previous_button = QPushButton("이전 작업 불러오기")
        self.previous_button.clicked.connect(self.load_previous)
        form.addWidget(self.previous_button)
        self.structure_button = QPushButton("장·절·소단원 구성")
        self.structure_button.clicked.connect(self.configure_structure)
        form.addWidget(self.structure_button)
        self.structure_info = QLabel("목차 구성: 기본 분석 또는 AI 분석 후 구조를 승인할 수 있습니다.")
        self.structure_info.setWordWrap(True)
        form.addWidget(self.structure_info)
        layout.addWidget(box)

    def _model_step(self, layout):
        box = QGroupBox("② AI 교정 설정")
        content = QVBoxLayout(box)
        form = QFormLayout()
        self.model_boxes = {}
        self.model_descriptions = {}
        enabled = [m for m in self.config["models"] if m.get("enabled", True)]
        for role, label, hint in ROLES:
            combo = QComboBox()
            combo.setToolTip(hint)
            combo.setMaxVisibleItems(12)
            for model in enabled:
                combo.addItem(f"{model.get('tier', '모델')} · {model.get('display_name', model['id'])}", model["id"])
                combo.setItemData(combo.count() - 1, model["id"] + "\n" + model.get("description", ""), Qt.ToolTipRole)
            preferred = str(self.prefs.value(role, self.config["defaults"][role]))
            index = combo.findData(preferred)
            if index < 0:
                index = combo.findData(self.config["defaults"][role])
            combo.setCurrentIndex(max(index, 0))
            combo.currentIndexChanged.connect(lambda _, r=role, b=combo: self._model_changed(r, b))
            self.model_boxes[role] = combo
            detail = QLabel(model_config(self.root, combo.currentData()).get("description", ""))
            detail.setWordWrap(True)
            self.model_descriptions[role] = detail
            field = QWidget()
            field_layout = QVBoxLayout(field)
            field_layout.setContentsMargins(0, 0, 0, 3)
            field_layout.addWidget(combo)
            field_layout.addWidget(detail)
            form.addRow(label, field)
        content.addLayout(form)
        self.advanced_toggle = QToolButton()
        self.advanced_toggle.setText("고급 설정 ▸")
        self.advanced_toggle.setCheckable(True)
        self.advanced_toggle.toggled.connect(self._toggle_advanced)
        content.addWidget(self.advanced_toggle)
        self.advanced = QWidget()
        advanced_form = QFormLayout(self.advanced)
        self.reasoning_role = QComboBox()
        for role, label, _ in ROLES:
            self.reasoning_role.addItem(label, role)
        self.reasoning_role.currentIndexChanged.connect(self._update_reasoning)
        advanced_form.addRow("추론 강도 적용 역할", self.reasoning_role)
        self.reasoning = QComboBox()
        self.reasoning.setToolTip("AI가 내용을 검토하는 깊이입니다. 높을수록 시간과 사용량이 늘 수 있습니다.")
        self.reasoning.currentTextChanged.connect(lambda value: self.prefs.setValue("reasoning_" + self.reasoning_role.currentData(), value))
        advanced_form.addRow("추론 강도", self.reasoning)
        self.advanced.hide()
        content.addWidget(self.advanced)
        layout.addWidget(box)
        self._update_reasoning()

    def _analysis_step(self, layout):
        box = QGroupBox("③ AI 교정")
        content = QVBoxLayout(box)
        self.active_role = QComboBox()
        for role, label, hint in ROLES:
            self.active_role.addItem(label.removesuffix(" 모델"), role)
            self.active_role.setItemData(self.active_role.count() - 1, hint, Qt.ToolTipRole)
        row = QHBoxLayout()
        row.addWidget(QLabel("이번 검토 단계"))
        row.addWidget(self.active_role, 1)
        content.addLayout(row)
        scope_row = QHBoxLayout()
        self.role_description = QLabel(ROLES[0][2])
        self.role_description.setWordWrap(True)
        content.addWidget(self.role_description)
        scope_row.addWidget(QLabel("검토 범위"))
        self.scope = QComboBox()
        self.scope.addItem("전체 원고", "all")
        self.scope.addItem("일부 문단 시험", "sample")
        scope_row.addWidget(self.scope)
        self.limit = QSpinBox()
        self.limit.setRange(1, 100000)
        self.limit.setValue(int(self.config.get("max_paragraphs", 20)))
        self.limit.setSuffix("개 문단")
        self.limit.setEnabled(False)
        scope_row.addWidget(self.limit)
        self.repeat_review = QCheckBox("이미 검토한 문단도 다시 검토")
        self.repeat_review.setToolTip("기본적으로 같은 단계·모델·추론 강도로 성공한 동일 문장은 건너뜁니다. 실패한 문단은 다시 시도합니다.")
        scope_row.addWidget(self.repeat_review)
        scope_row.addStretch()
        content.addLayout(scope_row)
        self.scope_info = QLabel("원고 준비 후 실제 검토 대상 수를 표시합니다.")
        self.scope_info.setWordWrap(True)
        content.addWidget(self.scope_info)
        content.addWidget(QLabel("앞 단계의 승인 내용을 이어받습니다. 필요한 단계만 실행해도 됩니다."))
        self.proofread_button = QPushButton("AI 교정 시작")
        self.proofread_button.setProperty('primary', True)
        self.proofread_button.clicked.connect(self.proofread)
        content.addWidget(self.proofread_button)
        self.stop_review_button = QPushButton("검토 중단")
        self.stop_review_button.clicked.connect(self.stop_review)
        content.addWidget(self.stop_review_button)
        content.addWidget(QLabel("원본은 변경하지 않고 수정 제안만 생성합니다."))
        layout.addWidget(box)

    def _review_step(self, layout):
        box = QGroupBox("④ 교정 결과 검토")
        content = QVBoxLayout(box)
        self.review_filter = QComboBox()
        self.review_filter.addItem("현재 단계의 제안", "current")
        self.review_filter.addItem("모든 새 검토 제안", "all")
        for role, label, _ in ROLES:
            self.review_filter.addItem(label.removesuffix(" 모델"), role)
        self.review_filter.addItem("이전 버전 검토 기록 (읽기 전용)", "legacy")
        content.addWidget(self.review_filter)
        self.review_notice = QLabel("")
        self.review_notice.setWordWrap(True)
        content.addWidget(self.review_notice)
        self.viewing_legacy = False
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(["ID", "원문 / 이 단계의 기준 문장", "수정 제안", "이유", "분류", "상태", "검토 단계"])
        self.table.horizontalHeaderItem(4).setToolTip("A: 단순 교정\nB: 편집자 검토\nC: 기술 검토\nD: 원본 보호")
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setFixedHeight(370)
        self.table.setAlternatingRowColors(True)
        self.table.setWordWrap(True)
        self.table.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.table.setItemDelegate(ReviewTextDelegate(self.table))
        self.table.setItemDelegateForColumn(5, StatusDelegate(self.table))
        self.table.setColumnHidden(0, True)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.cellDoubleClicked.connect(self.show_suggestion)
        for column, width in enumerate((72, 220, 220, 170, 100, 140, 95)):
            self.table.setColumnWidth(column, width)
        for column in (1, 2):
            self.table.horizontalHeader().setSectionResizeMode(column, QHeaderView.Stretch)
        help_text = QLabel("변경 부분은 밑줄과 색으로 표시합니다. 원문: 삭제·변경 / 수정 제안: 추가·변경\n여러 행을 선택할 수 있습니다. 긴 제안은 두 번 클릭하면 넓은 비교 창에서 전체를 볼 수 있습니다.")
        help_text.setWordWrap(True)
        content.addWidget(help_text)
        content.addWidget(self.table)
        self.review_summary = QLabel("교정 제안이 없습니다.")
        self.review_summary.setWordWrap(True)
        content.addWidget(self.review_summary)
        row = QHBoxLayout()
        self.review_buttons = []
        for label, state in (("선택 항목 승인", "approved"), ("선택 항목 거절", "rejected"), ("선택 항목 보류", "hold")):
            button = QPushButton(label)
            button.clicked.connect(lambda _, s=state: self.set_status(s))
            row.addWidget(button)
            self.review_buttons.append(button)
        content.addLayout(row)
        layout.addWidget(box)
        production = QGroupBox("⑤ 결과물 제작")
        p_layout = QVBoxLayout(production)
        folder_row = QHBoxLayout()
        project_root = self.root.parent.parent if self.root.name == "DigitalTextbookMaker" and self.root.parent.name.startswith("dist") else self.root
        default_output = project_root / "output"
        stored = Path(str(self.prefs.value("output_dir", default_output)))
        self.output_edit = QLineEdit(str(stored if stored.is_dir() else default_output))
        self.output_edit.setToolTip("HTML, PDF, EPUB 및 품질 검사 보고서가 저장될 폴더입니다.")
        choose = QPushButton("폴더 선택")
        self.choose_output_button = choose
        choose.clicked.connect(self.choose_output)
        folder_row.addWidget(QLabel("결과물 저장 위치"))
        folder_row.addWidget(self.output_edit, 1)
        folder_row.addWidget(choose)
        p_layout.addLayout(folder_row)
        format_row = QHBoxLayout()
        format_row.addWidget(QLabel("출력 형식"))
        self.format_boxes = {}
        for key, label in (("web", "HTML"), ("pdf", "PDF"), ("epub", "EPUB")):
            item = QCheckBox(label)
            item.setChecked(True)
            self.format_boxes[key] = item
            format_row.addWidget(item)
        format_row.addStretch()
        p_layout.addLayout(format_row)
        self.build_button = QPushButton("결과물 제작")
        self.build_button.setProperty('primary', True)
        self.build_button.clicked.connect(self.build)
        p_layout.addWidget(self.build_button)
        self.result_info = QLabel("제작 후 저장 위치가 여기에 표시됩니다.")
        self.result_info.setWordWrap(True)
        p_layout.addWidget(self.result_info)
        layout.addWidget(production)

    def _tools_step(self, layout):
        results = QHBoxLayout()
        self.qa_button = QPushButton("결과물 품질 확인")
        self.qa_button.clicked.connect(self.show_qa)
        self.open_output_button = QPushButton("결과 폴더 열기")
        self.open_output_button.clicked.connect(self.open_output)
        results.addWidget(self.qa_button)
        results.addWidget(self.open_output_button)
        layout.addLayout(results)
        toggle = QToolButton()
        toggle.setText("고급 도구 ▸")
        toggle.setCheckable(True)
        layout.addWidget(toggle)
        self.tools_panel = QWidget()
        row = QHBoxLayout(self.tools_panel)
        self.tool_buttons = []
        for label, callback in (
            ("API 연결 확인", self.api_test),
            ("사용 가능한 AI 모델 확인", self.check_models),
            ("AI 모델 비교", self.compare_models),
            ("이전 모델 비교 검토", self.review_comparison),
        ):
            button = QPushButton(label)
            button.clicked.connect(callback)
            row.addWidget(button)
            self.tool_buttons.append(button)
        self.tools_panel.hide()
        toggle.toggled.connect(lambda checked: (self.tools_panel.setVisible(checked), toggle.setText("고급 도구 ▾" if checked else "고급 도구 ▸")))
        layout.addWidget(self.tools_panel)

    def _toggle_advanced(self, checked):
        self.advanced.setVisible(checked)
        self.advanced_toggle.setText("고급 설정 ▾" if checked else "고급 설정 ▸")

    def _model_changed(self, role, combo):
        self.prefs.setValue(role, combo.currentData())
        self.model_descriptions[role].setText(model_config(self.root, combo.currentData()).get("description", ""))
        if role == self.reasoning_role.currentData():
            self._update_reasoning()
        if hasattr(self, "scope_info"):
            self.update_scope()

    def _update_reasoning(self):
        role = self.reasoning_role.currentData()
        model = model_config(self.root, self.model_boxes[role].currentData())
        options = model.get("reasoning_options", ["none"])
        previous = str(self.prefs.value("reasoning_" + role, self.prefs.value("reasoning", "none")))
        self.reasoning.blockSignals(True)
        self.reasoning.clear()
        self.reasoning.addItems(options)
        self.reasoning.setCurrentText(previous if previous in options else options[0])
        self.reasoning.blockSignals(False)
        self.prefs.setValue("reasoning_" + role, self.reasoning.currentText())
        if hasattr(self, "scope_info"):
            self.update_scope()

    def _effort(self, role):
        model = model_config(self.root, self.model_boxes[role].currentData())
        options = model.get("reasoning_options", ["none"])
        stored = str(self.prefs.value("reasoning_" + role, self.prefs.value("reasoning", "none")))
        if stored not in options:
            stored = options[0]
            self.prefs.setValue("reasoning_" + role, stored)
        return stored

    def browse(self):
        path, _ = QFileDialog.getOpenFileName(self, "DOCX 원고 선택", str(self.root / "input"), "Word 문서 (*.docx)")
        if path:
            self.source_edit.setText(path)

    def choose_output(self):
        folder = QFileDialog.getExistingDirectory(self, "결과물 저장 폴더 선택", self.output_edit.text())
        if folder:
            self.output_edit.setText(folder)
            self.prefs.setValue("output_dir", folder)

    def update_file_info(self):
        path = Path(self.source_edit.text()).resolve()
        if path.is_file() and path.suffix.lower() == ".docx":
            self.file_info.setText(f"✓ 원고 선택 완료 · {path.name} · {path.stat().st_size / 1024 / 1024:.2f} MB\n파일 위치: {path.parent}")
        else:
            self.file_info.setText("DOCX 원고를 선택해 주세요.")
        if self.analyzed_path != path:
            self.structure_info.setText("목차 구성: 원고 준비 후 확인할 수 있습니다.")
            self.analyzed_path = None
            self.analysis_info.setText("원고 준비 중…" if path.is_file() else "DOCX 원고를 선택하면 자동으로 준비합니다.")
            self.last_output_folder = self.last_report = None
            self.table.setRowCount(0)
            self._review_counts([])
            self.result_info.setText("제작 후 저장 위치가 여기에 표시됩니다.")
            self.prepare_timer.stop()
            if path.is_file() and path.suffix.lower() == ".docx":
                self.prepare_timer.start(300)
        self.update_buttons()

    def update_buttons(self):
        source_ok = Path(self.source_edit.text()).is_file() and self.source_edit.text().lower().endswith(".docx")
        analyzed = source_ok and self.analyzed_path == Path(self.source_edit.text()).resolve()
        self.structure_button.setEnabled(analyzed and not self.busy)
        self.proofread_button.setEnabled(analyzed and not self.busy)
        self.stop_review_button.setEnabled(self.busy and self.is_reviewing and not self.cancel_review.is_set())
        self.build_button.setEnabled(analyzed and not self.busy)
        self.active_role.setEnabled(not self.busy)
        self.scope.setEnabled(not self.busy)
        self.limit.setEnabled(not self.busy and self.scope.currentData() == "sample")
        self.repeat_review.setEnabled(not self.busy)
        self.review_filter.setEnabled(not self.busy)
        self.source_edit.setEnabled(not self.busy)
        self.output_edit.setEnabled(not self.busy)
        self.browse_button.setEnabled(not self.busy)
        self.choose_output_button.setEnabled(not self.busy)
        for box in self.model_boxes.values():
            box.setEnabled(not self.busy)
        for button in self.tool_buttons:
            button.setEnabled(not self.busy)
        self.open_output_button.setEnabled(bool(self.last_output_folder and self.last_output_folder.is_dir()) and not self.busy)
        self.qa_button.setEnabled(bool(self.last_report and self.last_report.is_file()) and not self.busy)
        self.previous_button.setEnabled(not self.busy)
        self.tool_buttons[2].setEnabled(analyzed and not self.busy)
        self.advanced.setEnabled(not self.busy)
        for box in self.format_boxes.values():
            box.setEnabled(not self.busy)
        self.update_review_buttons()

    def update_review_buttons(self):
        selected = bool(self.table.selectionModel() and self.table.selectionModel().selectedRows())
        for button in self.review_buttons:
            button.setEnabled(selected and not self.busy and not self.viewing_legacy)

    def production(self):
        path = Path(self.source_edit.text())
        if not path.is_file() or path.suffix.lower() != ".docx":
            QMessageBox.warning(self, "원고 확인", "읽을 수 있는 DOCX 원고를 선택해 주세요.")
            return None
        self.prefs.setValue("source", str(path))
        return Production(self.root, path)

    def configure_structure(self):
        from app.gui.structure_dialog import StructureDialog
        job = self.production()
        if not job:
            return
        try:
            dialog = StructureDialog(job, self.model_boxes["technical_review"].currentData(), self._effort("technical_review"), self)
            dialog.exec()
            saved = job.structure().load()
            self.structure_info.setText("목차 구성: " + (f"{len(saved['nodes'])}개 · " + ("승인됨" if saved["status"] == "approved" else "초안 · 승인 필요") if saved else "미설정"))
        except (ValueError, OSError) as exc:
            QMessageBox.warning(self, "구조 확인", str(exc))

    def run_task(self, label, action, done, progress=None):
        if self.busy:
            return
        self.busy = True
        self.task_started = time.monotonic()
        self.status.setText(label)
        self.progress_details.setText("처리시간 00:00")
        self.progress_base = ""
        self.progress.setRange(0, 100 if progress else 0)
        self.progress.setValue(0)
        self.update_buttons()
        self.timer.start(1000)
        thread = start(action, lambda result: self._done(result, done), self._failed, progress)
        self.threads.append(thread)
        thread.finished.connect(lambda: self.threads.remove(thread) if thread in self.threads else None)

    def _tick(self):
        seconds = int(time.monotonic() - self.task_started)
        prefix = self.progress_base + " · " if self.progress_base else ""
        self.progress_details.setText(f"{prefix}처리시간 {seconds // 60:02d}:{seconds % 60:02d}")

    def _done(self, result, callback):
        self.timer.stop()
        self.busy = False
        self.progress.setRange(0, 100)
        self.progress.setValue(100)
        callback(result)
        self.update_buttons()

    def _failed(self, message):
        self.timer.stop()
        self.busy = False
        self.is_reviewing = False
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.status.setText("작업 실패")
        self.update_buttons()
        QMessageBox.warning(self, "작업 실패", message)

    def api_test(self):
        labels = [label for _, label, _ in ROLES]
        chosen, accepted = QInputDialog.getItem(self, "확인할 모델", "실제 API 응답을 확인할 역할", labels, 0, False)
        if not accepted:
            return
        role = ROLES[labels.index(chosen)][0]
        model = self.model_boxes[role].currentData()
        reasoning = self._effort(role)
        self.run_task("선택한 모델의 실제 API 응답 확인 중", lambda: connection_test(self.root, model, reasoning),
                      lambda info: self.status.setText(f"API 응답 확인 완료 · {info['model']} · {info['elapsed_seconds']}초 · {info['input_tokens'] + info['output_tokens']} tokens · 비용 USD {cost(self.root, info) or 0:.6f}"))

    def check_models(self):
        def lookup():
            try:
                return available_models(self.root)
            except Exception:
                return {"error": True}
        def finished(result):
            if result.get("error"):
                self.status.setText("설정된 모델 목록을 사용합니다")
                QMessageBox.information(self, "사용 가능한 AI 모델", "AI 모델 목록을 자동 확인할 수 없습니다. 설정된 모델 목록을 사용합니다.")
                return
            available = result["available"]
            missing = result["unavailable"]
            self.status.setText(f"설정된 모델 {len(available)}개 사용 가능")
            QMessageBox.information(self, "사용 가능한 AI 모델", "사용 가능: " + ", ".join(available) +
                                    ("\n확인되지 않음: " + ", ".join(missing) if missing else ""))
        self.run_task("설정된 모델의 사용 가능 여부 확인 중", lookup, finished)

    def analyze(self):
        if self.busy:
            self.prepare_timer.start(300)
            return
        path = Path(self.source_edit.text()).resolve()
        if not path.is_file() or path.suffix.lower() != ".docx" or path == self.analyzed_path:
            return
        job = self.production()
        if job:
            self.run_task("원고 읽는 중", job.analyze, lambda master: self._analysis_done(job, master), self._phase_progress)

    def _analysis_done(self, job, master):
        self.analyzed_path = job.source
        try:
            structure = job.structure().load()
            self.structure_info.setText("목차 구성: " + (f"{len(structure['nodes'])}개 · " + ("승인됨" if structure["status"] == "approved" else "초안 · 승인 필요") if structure else "미설정 · 장·절·소단원 구성 버튼을 눌러 시작하세요."))
        except ValueError:
            self.structure_info.setText("목차 구성: 원고 정보가 변경되어 다시 분석해야 합니다.")
        counts = {}
        for block in master.blocks:
            counts[block.kind] = counts.get(block.kind, 0) + 1
        image_count = sum(len(block.assets) for block in master.blocks)
        links = sum(len(block.links) for block in master.blocks)
        self.analysis_info.setText(f"✓ 원고 준비 완료 · 본문 {counts.get('paragraph', 0)} · 이미지 {image_count} · 코드 {counts.get('code-block', 0)} · 표 {counts.get('table', 0)} · 링크 {links}")
        self.status.setText("원고 준비 완료 · AI 교정을 시작하거나 결과물을 제작하세요.")
        self.load_suggestions()
        self.update_scope()
        previous = job.last_result()
        if previous and Path(previous["folder"]).is_dir():
            self.last_output_folder = Path(previous["folder"])
            self.last_report = Path(previous["report"])
            self.result_info.setText("이전 결과물: " + previous["folder"])
        self.update_buttons()

    def _role_changed(self):
        self.role_description.setText(next(hint for role, _, hint in ROLES if role == self.active_role.currentData()))
        self.review_filter.blockSignals(True)
        self.review_filter.setCurrentIndex(0)
        self.review_filter.blockSignals(False)
        self.load_suggestions()
        self.update_scope()

    def update_scope(self):
        self.limit.setEnabled(not self.busy and self.scope.currentData() == "sample")
        if self.analyzed_path != Path(self.source_edit.text()).resolve():
            return
        job = self.production()
        if not job:
            return
        role = self.active_role.currentData()
        limit = self.limit.value() if self.scope.currentData() == "sample" else None
        try:
            plan = job.review_plan(self.model_boxes[role].currentData(), self._effort(role), limit, role, self.repeat_review.isChecked())
        except ValueError as exc:
            self.scope_info.setText(str(exc))
            return
        self.scope_info.setText(f"교정 가능한 문단 {plan['eligible']}개 · 이미 검토 {plan['already_reviewed']}개 · 이번 대상 {plan['target_count']}개 · 이번 실행 후 남은 대상 {plan['remaining']}개 (코드·표 등 보호 영역 제외)")

    def proofread(self):
        job = self.production()
        if not job:
            return
        role = self.active_role.currentData()
        model = self.model_boxes[role].currentData()
        reasoning = self._effort(role)
        limit = self.limit.value() if self.scope.currentData() == "sample" else None
        repeat = self.repeat_review.isChecked()
        try:
            plan = job.review_plan(model, reasoning, limit, role, repeat)
        except ValueError as exc:
            QMessageBox.warning(self, "검토 기준 확인", str(exc))
            return
        if not plan["target_count"]:
            QMessageBox.information(self, "검토 대상", "현재 설정으로 새로 검토할 문단이 없습니다. 재검토가 필요하면 ‘이미 검토한 문단도 다시 검토’를 선택하세요.")
            return
        workflow = job.workflow()
        migration = ""
        if not workflow.active and workflow.legacy():
            approved_count = sum(i['status'] == 'approved' for i in workflow.legacy())
            migration = f"\n기존 승인 {approved_count}건을 반영한 원고로 새 검토를 시작합니다. 이전 기록은 별도로 보존됩니다."
        earlier = [r for r, _, _ in ROLES][:next(i for i, r in enumerate(ROLES) if r[0] == role)]
        unresolved = sum(i.get("role") in earlier and i['status'] in ('pending', 'hold', 'outdated') for i in workflow.items())
        note = f"\n앞 단계의 미검토·보류·재검토 필요 {unresolved}건은 반영하지 않습니다." if unresolved else ""
        message = f"{self.active_role.currentText()} · {plan['target_count']}개 문단을 검토합니다.\n앞 단계에서 승인한 내용이 반영된 문장을 사용합니다.\nAPI 비용이 발생합니다. 모델: {model}" + migration + note
        if QMessageBox.question(self, "AI 검토 실행 확인", message) != QMessageBox.Yes:
            return
        self.cancel_review = Event()
        self.is_reviewing = True
        self.run_task("AI 검토 중", lambda emit: job.proofread(model, reasoning, limit, emit, role, repeat, self.cancel_review.is_set),
                      self._proofread_done, self._proofread_progress)

    def stop_review(self):
        self.cancel_review.set()
        self.stop_review_button.setEnabled(False)
        self.status.setText("중단 요청됨 · 현재 문단의 응답을 받은 뒤 중단하고 결과를 저장합니다.")

    def _proofread_progress(self, info):
        self.progress.setValue(int(100 * info["done"] / max(info["total"], 1)))
        price = "가격 미설정" if info["estimated_cost_usd"] is None else f"USD {info['estimated_cost_usd']:.6f}"
        self.progress_base = f"처리 {info['done']}/{info['total']} 문단 · API 호출 {info['calls']}회 · 입력 {info['input_tokens']} / 출력 {info['output_tokens']} tokens · 예상 비용 {price}"
        self.progress_details.setText(self.progress_base)

    def _proofread_done(self, result):
        self.is_reviewing = False
        success, failed, unprocessed = result["success_count"], result["failure_count"], result["unprocessed_count"]
        total = result["target_count"]
        complete = failed == 0 and unprocessed == 0
        self.progress.setValue(100 if complete else int(100 * success / max(total, 1)))
        title = "검토 완료" if complete else "검토 중단 · 사용자 요청" if result.get('cancelled') and not failed else "검토 중단 · 일부 실패"
        self.status.setText(f"{title} · 대상 {total} · 성공 {success} · 실패 {failed} · 미처리 {unprocessed} · 새 제안 {result['new_count']}건")
        failures = [c for c in result["calls"] if not c.get("success")]
        if failures:
            self.progress_details.setText(failures[0].get("error", "") + " · 다시 시작하면 성공한 문단을 건너뛰고 남은 문단을 검토합니다.")
        self.review_filter.blockSignals(True)
        self.review_filter.setCurrentIndex(0)
        self.review_filter.blockSignals(False)
        self.load_suggestions()
        self.update_scope()

    def load_suggestions(self):
        if not self.analyzed_path or self.analyzed_path != Path(self.source_edit.text()).resolve():
            return
        job = self.production()
        if not job:
            return
        workflow = job.workflow()
        view = self.review_filter.currentData()
        self.viewing_legacy = view == "legacy" or (not workflow.active and bool(workflow.legacy()))
        if self.viewing_legacy:
            items = workflow.legacy()
            self.review_notice.setText("이전 버전 기록은 읽기 전용으로 보존합니다. 기존 ‘보류’의 변경 이유는 기록되지 않았습니다. 새 AI 검토는 기존 승인본에서 시작합니다.")
        else:
            items = workflow.items()
            role = self.active_role.currentData() if view == "current" else view
            if role != "all":
                items = [item for item in items if item.get("role") == role]
            self.review_notice.setText("‘대체됨’은 같은 단계의 다른 제안을 승인한 경우입니다. ‘다시 검토 필요’는 앞 단계의 기준 문장이 바뀐 경우입니다.")
        labels = {"approved": "승인", "rejected": "거절", "hold": "보류", "pending": "미검토", "superseded": "대체됨", "outdated": "다시 검토 필요"}
        levels = {"A": "A 단순 교정", "B": "B 편집 검토", "C": "C 기술 확인", "D": "D 원본 보호"}
        roles = {r: label.removesuffix(" 모델") for r, label, _ in ROLES}
        self.table.setRowCount(len(items))
        for row, item in enumerate(items):
            before, after = diff_segments(item['source_text'], item['suggested_text'])
            values = (item["id"], item["source_text"], item["suggested_text"], item["reason"], levels.get(item["level"], item["level"]), labels.get(item["status"], item["status"]), roles.get(item.get("role"), "이전 기록"))
            for col, value in enumerate(values):
                cell = QTableWidgetItem(str(value))
                cell.setToolTip(str(value) + ("\n" + item.get("status_reason", "") if col == 5 else ""))
                if col in (1, 2):
                    cell.setData(SEGMENTS_ROLE, before if col == 1 else after)
                if col == 5:
                    cell.setData(STATUS_ROLE, item['status'])
                self.table.setItem(row, col, cell)
            self.table.setRowHeight(row, 104)
        self._review_counts(items)
        self.update_review_buttons()

    def _review_counts(self, items):
        counts = {state: sum(item.get("status") == state for item in items) for state in ("approved", "rejected", "hold", "pending", "superseded", "outdated")}
        self.review_summary.setText(f"표시된 제안 {len(items)} · 승인 {counts['approved']} · 거절 {counts['rejected']} · 보류 {counts['hold']} · 미검토 {counts['pending']} · 대체됨 {counts['superseded']} · 다시 검토 필요 {counts['outdated']}")

    def set_status(self, status):
        job = self.production()
        if not job or self.viewing_legacy:
            return
        rows = sorted({index.row() for index in self.table.selectionModel().selectedRows()})
        ids = [self.table.item(row, 0).text() for row in rows]
        before = {item['id']: item['status'] for item in job.suggestions()}
        try:
            items = job.review(ids, status)
        except ValueError as exc:
            QMessageBox.warning(self, "검토 상태 확인", str(exc))
            return
        replaced = sum(i['status'] == 'superseded' and before.get(i['id']) != i['status'] for i in items)
        outdated = sum(i['status'] == 'outdated' and before.get(i['id']) != i['status'] for i in items)
        self.load_suggestions()
        self.update_scope()
        self.status.setText(f"선택한 {len(ids)}건 저장 · 다른 제안으로 대체 {replaced}건 · 후속 단계 다시 검토 필요 {outdated}건")

    def show_suggestion(self, row, column):
        self.suggestion_dialog(row).exec()

    def suggestion_dialog(self, row):
        details = ' · '.join(self.table.item(row, c).text() for c in (4, 5, 6))
        return comparison_dialog(self, self.table.item(row, 1).text(), self.table.item(row, 2).text(),
                                 self.table.item(row, 3).text(), details + '\n' + self.table.item(row, 5).toolTip())

    def load_previous(self):
        rows = [row for row in Production.recent(self.root) if Path(row["source"]).is_file()]
        if not rows:
            QMessageBox.information(self, "이전 작업", "저장된 작업이 없습니다. DOCX 원고를 선택해 주세요.")
            return
        labels = [row["name"] + " · " + row["updated"] for row in rows]
        chosen, accepted = QInputDialog.getItem(self, "이전 작업 불러오기", "이어갈 작업", labels, 0, False)
        if accepted:
            self.analyzed_path = None
            self.source_edit.setText(rows[labels.index(chosen)]["source"])
            self.update_file_info()

    def _phase_progress(self, info):
        self.status.setText(info["phase"])
        self.progress.setValue(info["percent"])

    def review_comparison(self, path=None):
        from app.gui.comparison import ComparisonDialog
        if not path:
            path, _ = QFileDialog.getOpenFileName(self, "이전 모델 비교 검토", str(self.root / "reports/model-comparison"), "비교 보고서 (model-comparison.html)")
        if path:
            ComparisonDialog(Path(path).parent, self).exec()

    def build(self):
        job = self.production()
        if not job:
            return
        items = job.workflow().items()
        unresolved = sum(i['status'] in ('pending', 'hold', 'outdated') for i in items)
        if unresolved and QMessageBox.question(self, "제작할 내용 확인", f"미검토·보류·다시 검토 필요 항목이 {unresolved}건 있습니다.\n이 항목은 반영하지 않고, 현재 승인한 내용으로 제작할까요?") != QMessageBox.Yes:
            return
        formats = [key for key, box in self.format_boxes.items() if box.isChecked()]
        if not formats:
            QMessageBox.warning(self, "출력 형식", "출력 형식을 하나 이상 선택해 주세요.")
            return
        destination = Path(self.output_edit.text())
        chosen = None if destination == job.default_output_base else destination
        self.run_task("승인 내용 반영 중", lambda emit: job.build(formats, chosen, emit), self._build_done, self._phase_progress)

    def _build_done(self, result):
        self.last_output_folder = Path(result["folder"])
        self.last_report = Path(result["report"])
        self.prefs.setValue("output_dir", self.output_edit.text())
        self.status.setText("결과물 제작 완료 · 품질 검사 " + ("통과" if result["qa"]["passed"] and not result["qa"].get("warnings") else "확인 필요"))
        lines = [f"{'HTML' if kind == 'web' else kind.upper()}: {path}" for kind, path in result["outputs"].items()]
        lines.append(f"품질 검사: {result['report']}")
        self.result_info.setText("제작 완료: " + ", ".join("HTML" if k == "web" else k.upper() for k in result["outputs"]) + "\n저장 폴더: " + result["folder"])
        self.result_info.setToolTip("\n".join(lines))
        self.update_buttons()

    def show_qa(self):
        if self.last_report and self.last_report.is_file():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.last_report)))
        else:
            QMessageBox.information(self, "품질 검사 결과", "이번 실행에서 제작한 결과물이 없습니다.")

    def compare_models(self):
        job = self.production()
        if not job:
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("AI 모델 비교")
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel("대표 문단에 사용할 모델을 선택하세요. 최고 정밀 모델은 기본 선택되지 않습니다."))
        choices = []
        for model in self.config["models"]:
            if not model.get("enabled", True):
                continue
            box = QCheckBox(f"{model.get('tier', '')} · {model.get('display_name', model['id'])}")
            box.setToolTip(model["id"] + "\n" + model.get("description", ""))
            box.setChecked(model.get("tier") in ("빠름/저비용", "균형", "정밀"))
            choices.append((box, model))
            layout.addWidget(box)
        go = QPushButton("선택한 모델 비교")
        go.clicked.connect(dialog.accept)
        layout.addWidget(go)
        if dialog.exec() != QDialog.Accepted:
            return
        chosen = [model for box, model in choices if box.isChecked()]
        if not chosen:
            QMessageBox.warning(self, "모델 선택", "비교할 모델을 하나 이상 선택해 주세요.")
            return
        if any(model.get("tier") == "최고 정밀" for model in chosen):
            if QMessageBox.question(self, "비용 확인", "최고 정밀 모델이 선택되었습니다. API 비용이 높을 수 있습니다. 계속할까요?") != QMessageBox.Yes:
                return
        count = int(self.config.get("max_comparison_samples", 5))
        if QMessageBox.question(self, "모델 비교 확인", f"대표 문단 최대 {count}개를 {len(chosen)}개 모델로 검토합니다. 계속할까요?") != QMessageBox.Yes:
            return
        ids = [model["id"] for model in chosen]
        common = set(chosen[0].get("reasoning_options", ["none"]))
        for model in chosen[1:]:
            common.intersection_update(model.get("reasoning_options", ["none"]))
        if not common:
            QMessageBox.warning(self, "추론 강도", "선택한 모델들이 공통으로 지원하는 추론 강도가 없습니다.")
            return
        effort = self._effort("proofreading")
        if effort not in common:
            ordered = [value for value in ("none", "low", "medium", "high", "xhigh", "max") if value in common]
            effort, accepted = QInputDialog.getItem(self, "추론 강도 선택", "선택 모델에 공통으로 적용할 추론 강도", ordered, 0, False)
            if not accepted:
                return
        self.run_task("AI 모델 비교 중", lambda: compare(self.root, job.master(), ids, effort, count),
                      lambda path: (self.status.setText("AI 모델 비교 완료 · 제안을 검토해 승인률을 확인하세요."), self.review_comparison(path)))

    def open_output(self):
        if self.last_output_folder and self.last_output_folder.is_dir():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.last_output_folder)))

    def closeEvent(self, event):
        if any(thread.isRunning() for thread in self.threads):
            QMessageBox.information(self, "작업 진행 중", "현재 작업이 끝난 뒤 프로그램을 닫아 주세요.")
            event.ignore()
        else:
            event.accept()
