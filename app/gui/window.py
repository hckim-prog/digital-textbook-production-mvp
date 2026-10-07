from __future__ import annotations

from pathlib import Path
import time
from threading import Event

from PySide6.QtCore import QSettings, Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QDialog, QFileDialog, QFormLayout,
    QGroupBox, QHBoxLayout, QHeaderView, QLayout, QInputDialog, QLabel, QLineEdit, QMainWindow, QMessageBox, QRadioButton, QButtonGroup,
    QPushButton, QProgressBar, QScrollArea, QSpinBox, QTableWidget,
    QTableWidgetItem, QTabWidget, QToolButton, QVBoxLayout, QWidget,
)

from app.gui.controls import ClickComboBox
from app.controllers.production import Production
from app.workers.task import start
from core.ai.service import addable_model_ids, available_models, connection_test, cost, model_config, save_custom_model, settings
from core.reporting.comparison import compare
from app.gui.review_display import (
    SEGMENTS_ROLE, STATUS_ROLE, ReviewTextDelegate, StatusDelegate,
    comparison_dialog, diff_segments,
)


ROLES = (
    ("proofreading", "교정/교열 모델", "맞춤법과 문장 표현을 검토합니다."),
    ("technical_review", "기술 검토 모델", "C++ 내용과 기술 설명을 검토합니다."),
    ("final_review", "최종 검토 모델", "자동 출판에서는 수정본을 재검사합니다. 상세 검토에서는 제안을 만들며 사람이 승인합니다. 코드 실행 검사는 하지 않습니다."),
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
        self.is_building = False
        self.resume_build = False
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
        self.pages = QTabWidget()
        page_layouts = []
        for title in ("교재 제작", "검토·관리", "고급 설정"):
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            body = QWidget()
            layout = QVBoxLayout(body)
            layout.setSpacing(10)
            layout.setSizeConstraint(QLayout.SetMinimumSize)
            scroll.setWidget(body)
            self.pages.addTab(scroll, title)
            page_layouts.append(layout)
        outer.addWidget(self.pages, 1)
        main, manage, advanced = page_layouts
        intro = QLabel("원고를 선택하고 제작 설정을 확인한 뒤 ‘교재 만들기’를 누르세요.")
        intro.setWordWrap(True)
        main.addWidget(intro)
        manage.addWidget(QLabel("목차, 교정 제안, 자동 수정 내역을 필요할 때 확인하세요."))
        advanced.addWidget(QLabel("저장된 AI 설정을 사용합니다. 모델과 세부 옵션을 바꿀 때만 이 화면을 이용하세요."))
        self._source_step(main, manage, advanced)
        self._model_step(advanced)
        self._analysis_step(manage)
        self._review_step(manage, main, advanced)
        self._tools_step(main, manage, advanced)
        for page_layout in page_layouts:
            page_layout.addStretch()
        self.status = QLabel("DOCX 원고를 선택해 주세요.")
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

    def _source_step(self, layout, manage, advanced):
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
        self.file_info.setWordWrap(True)
        form.addWidget(self.file_info)
        self.analysis_info = QLabel("DOCX 원고를 선택하면 자동으로 준비합니다.")
        self.analysis_info.setWordWrap(True)
        form.addWidget(self.analysis_info)
        self.source_notice = QLabel()
        self.source_notice.setWordWrap(True)
        self.source_notice.linkActivated.connect(lambda _: (self.pages.setCurrentIndex(1), self.show_preflight()))
        self.source_notice.hide()
        form.addWidget(self.source_notice)
        self.previous_button = QPushButton("이전 작업 불러오기")
        self.previous_button.clicked.connect(self.load_previous)
        row.addWidget(self.previous_button)
        layout.addWidget(box)
        inspection = QGroupBox("목차와 원고 진단")
        form = QVBoxLayout(inspection)
        self.structure_button = QPushButton("목차 직접 편집 · 선택 사항")
        self.structure_button.clicked.connect(self.configure_structure)
        form.addWidget(self.structure_button)
        self.structure_info = QLabel("목차 구성: 자동 제작 시 진단을 통과한 구조가 반영됩니다. 직접 편집은 선택 사항입니다.")
        self.structure_info.setWordWrap(True)
        form.addWidget(self.structure_info)
        self.preflight_info = QLabel("사전 진단: 원고를 선택하면 자동 제작 가능 여부를 확인합니다.")
        self.preflight_info.setWordWrap(True)
        form.addWidget(self.preflight_info)
        self.preflight_button = QPushButton("사전 진단 상세 보기")
        self.preflight_button.clicked.connect(self.show_preflight)
        form.addWidget(self.preflight_button)
        manage.addWidget(inspection)
        structure_options = QGroupBox("목차 세부 설정")
        structure_layout = QVBoxLayout(structure_options)
        self.depth_existing = QRadioButton("기존 구조 사용")
        self.depth_ai = QRadioButton("AI로 소제목 자동 보완")
        self.depth_group = QButtonGroup(self)
        self.depth_group.addButton(self.depth_existing)
        self.depth_group.addButton(self.depth_ai)
        self.depth_ai.setToolTip("선택한 기술 검토 모델로 필요한 하위 제목만 생성하여 바로 적용합니다. API 비용이 발생하며 본문·코드는 변경하지 않습니다.")
        structure_layout.addWidget(self.depth_existing)
        structure_layout.addWidget(self.depth_ai)
        depth_row = QHBoxLayout()
        depth_row.addWidget(QLabel("제목 최대 단계"))
        self.max_depth = ClickComboBox()
        self.max_depth.addItem("3단계 · 장 → 절 → 소단원", 3)
        self.max_depth.addItem("4단계 · 장 → 절 → 소단원 → 주제", 4)
        self.max_depth.setCurrentIndex(max(0, self.max_depth.findData(int(self.prefs.value('max_depth', 4)))))
        depth_row.addWidget(self.max_depth)
        structure_layout.addLayout(depth_row)
        self.depth_ai.setChecked(str(self.prefs.value('depth_mode', 'ai')) == 'ai')
        self.depth_existing.setChecked(not self.depth_ai.isChecked())
        self.max_depth.setEnabled(self.depth_ai.isChecked())
        self.depth_ai.toggled.connect(lambda enabled: (self.prefs.setValue('depth_mode', 'ai' if enabled else 'existing'), self.max_depth.setEnabled(enabled and not self.busy)))
        self.depth_ai.toggled.connect(lambda _: self._depth_mode_changed())
        self.max_depth.currentIndexChanged.connect(lambda _: self.prefs.setValue('max_depth', self.max_depth.currentData()))
        advanced.addWidget(structure_options)

    def _model_step(self, layout):
        box = QGroupBox("AI 모델 설정")
        content = QVBoxLayout(box)
        form = QFormLayout()
        self.model_boxes = {}
        self.model_descriptions = {}
        enabled = [m for m in self.config["models"] if m.get("enabled", True)]
        for role, label, hint in ROLES:
            combo = ClickComboBox()
            combo.setToolTip(hint)
            combo.setMaxVisibleItems(12)
            for model in enabled:
                self._append_model_option(combo, model)
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
        self.advanced_toggle.setText("추론 강도 바꾸기 ▸")
        self.advanced_toggle.setCheckable(True)
        self.advanced_toggle.toggled.connect(self._toggle_advanced)
        content.addWidget(self.advanced_toggle)
        self.advanced = QWidget()
        advanced_form = QFormLayout(self.advanced)
        self.reasoning_role = ClickComboBox()
        for role, label, _ in ROLES:
            self.reasoning_role.addItem(label, role)
        self.reasoning_role.currentIndexChanged.connect(self._update_reasoning)
        advanced_form.addRow("추론 강도 적용 역할", self.reasoning_role)
        self.reasoning = ClickComboBox()
        self.reasoning.setToolTip("AI가 내용을 검토하는 깊이입니다. 높을수록 시간과 사용량이 늘 수 있습니다.")
        self.reasoning.currentTextChanged.connect(lambda value: self.prefs.setValue("reasoning_" + self.reasoning_role.currentData(), value))
        advanced_form.addRow("추론 강도", self.reasoning)
        self.advanced.hide()
        content.addWidget(self.advanced)
        layout.addWidget(box)
        self._update_reasoning()

    def _analysis_step(self, layout):
        box = QGroupBox("선택 사항 · 단계별 AI 검토")
        self.analysis_panel = box
        content = QVBoxLayout(box)
        self.active_role = ClickComboBox()
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
        self.scope = ClickComboBox()
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

    def _review_step(self, layout, main, advanced):
        self.detail_toggle = QCheckBox("문장별로 직접 검토하기 · 선택 사항")
        layout.insertWidget(layout.indexOf(self.analysis_panel), self.detail_toggle)
        self.analysis_panel.hide()
        box = QGroupBox("상세 교정 결과 · 수동 검토")
        box.hide()
        self.detail_toggle.toggled.connect(self.analysis_panel.setVisible)
        self.detail_toggle.toggled.connect(box.setVisible)
        content = QVBoxLayout(box)
        detail_note = QLabel('이 표는 수동 검토 기록입니다. 자동 출판의 반영 결과와 되돌리기는 아래 자동 변경 관리에서 확인하세요.')
        detail_note.setWordWrap(True)
        content.addWidget(detail_note)
        self.review_filter = ClickComboBox()
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
        production = QGroupBox("② 제작 설정")
        p_layout = QVBoxLayout(production)
        self.settings_panel = production
        design_row = QHBoxLayout()
        design_row.addWidget(QLabel("교재 디자인"))
        self.design_theme = ClickComboBox()
        from core.export.themes import THEMES
        self.design_theme.addItem("자동 추천 · 원고 구성에 맞춰 적용", "auto")
        for theme_id, theme in THEMES.items():
            self.design_theme.addItem(theme['name'], theme_id)
        self.design_theme.setCurrentIndex(max(0, self.design_theme.findData(str(self.prefs.value('design_theme', 'auto')))))
        self.design_theme.currentIndexChanged.connect(lambda _: self.prefs.setValue('design_theme', self.design_theme.currentData()))
        design_row.addWidget(self.design_theme, 1)
        self.preview_design_button = QPushButton("디자인 미리보기")
        self.preview_design_button.clicked.connect(self.preview_design)
        design_row.addWidget(self.preview_design_button)
        p_layout.addLayout(design_row)
        self.design_info = QLabel("미리보기는 예시 교재입니다. 디자인 선택에는 AI 비용이 들지 않습니다.")
        self.design_info.setWordWrap(True)
        p_layout.addWidget(self.design_info)
        output_policy = QGroupBox("제작 방식 · 수동 검토를 사용할 때")
        policy_layout = QVBoxLayout(output_policy)
        self.quick_mode = QCheckBox("자동 제작 사용 · 끄면 기존 승인본으로 제작")
        self.quick_mode.setChecked(True)
        policy_layout.addWidget(self.quick_mode)
        advanced.addWidget(output_policy)
        self.quick_ai = QCheckBox("AI로 문장 교정하기 · 검사 후 수정본에 반영")
        self.quick_ai.setToolTip("문장 교정 → 기술 검토 → 변경 문장 재검사를 거쳐 반영합니다. API 비용이 발생합니다.")
        self.quick_ai.setChecked(True)
        self.quick_mode.toggled.connect(self.quick_ai.setEnabled)
        p_layout.addWidget(self.quick_ai)
        self.learning_ai = QCheckBox("부족한 학습 문제와 정답 추가하기 · 새 내용 생성")
        self.learning_ai.setToolTip("원고에 근거한 새 문제·정답·해설을 생성하고 별도 검수합니다. API 비용이 발생합니다.")
        self.learning_ai.setChecked(str(self.prefs.value('learning_ai', 'true')).lower() == 'true')
        self.learning_ai.toggled.connect(lambda value: self.prefs.setValue('learning_ai', value))
        self.editorial_ai = QCheckBox("제작 전 문장 최종 검사하기 · 남은 오류 확인")
        self.editorial_ai.setToolTip("교정 후 남은 오탈자와 미완성 문장을 별도로 검사합니다. API 비용이 발생합니다.")
        self.editorial_ai.setChecked(str(self.prefs.value('editorial_ai', 'true')).lower() == 'true')
        self.editorial_ai.toggled.connect(lambda value: self.prefs.setValue('editorial_ai', value))
        p_layout.addWidget(self.editorial_ai)
        self.depth_option = QCheckBox("소제목 자동 보완하기 · 장·절은 유지")
        self.depth_option.setToolTip("장·절은 유지하고 필요한 하위 제목만 추가합니다. API 비용이 발생합니다.")
        self.depth_option.setChecked(self.depth_ai.isChecked())
        self.depth_option.toggled.connect(lambda checked: (self.depth_ai if checked else self.depth_existing).setChecked(True))
        self.depth_ai.toggled.connect(self.depth_option.setChecked)
        p_layout.addWidget(self.depth_option)
        p_layout.addWidget(self.learning_ai)
        def update_enrichment_options():
            enabled = self.quick_mode.isChecked() and self.quick_ai.isChecked()
            self.learning_ai.setEnabled(enabled)
            self.editorial_ai.setEnabled(enabled)
        self.quick_mode.toggled.connect(update_enrichment_options)
        self.quick_ai.toggled.connect(update_enrichment_options)
        update_enrichment_options()
        self.editorial_button = QPushButton("문장 최종 검사 결과 보기")
        self.editorial_button.clicked.connect(self.show_editorial_report)
        self.allow_restructure = QCheckBox("기본 목차가 부족할 때 AI 새 제목·목차 구성 허용 · API 비용 발생")
        self.allow_restructure.setToolTip("원문·코드·그림은 보존하고 새 제목만 추가합니다. 구조 검사 실패 시 교정 전에 멈춥니다. 현재 AI 구조 분석은 입력 60,000자까지 지원합니다.")
        policy_layout.addWidget(self.allow_restructure)
        self.quick_mode.toggled.connect(self.allow_restructure.setEnabled)
        note = QLabel("원본 DOCX와 수동 검토 기록은 유지합니다. 자동 수정은 검사 후 출력에 반영됩니다.\n학습 문제 추가는 새 내용을 생성합니다. 공식 문서·이미지 내용 대조와 사람의 최종 확인은 별도입니다.")
        note.setWordWrap(True)
        policy_layout.addWidget(note)
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
            item = QCheckBox({"web": "웹 교재 (HTML)", "pdf": "인쇄용 (PDF)", "epub": "전자책 (EPUB)"}[key])
            item.setChecked(True)
            self.format_boxes[key] = item
            format_row.addWidget(item)
        format_row.addStretch()
        p_layout.addLayout(format_row)
        self.settings_summary = QLabel()
        self.settings_summary.setWordWrap(True)
        p_layout.addWidget(self.settings_summary)
        model_link = QPushButton("AI 모델·세부 설정 보기")
        model_link.clicked.connect(lambda: self.pages.setCurrentIndex(2))
        p_layout.addWidget(model_link)
        main.addWidget(production)
        creation = QGroupBox("③ 교재 제작")
        p_layout = QVBoxLayout(creation)
        self.build_button = QPushButton("교재 만들기")
        self.build_button.setProperty('primary', True)
        self.build_button.clicked.connect(self.build)
        self.quick_mode.toggled.connect(lambda _: self.update_buttons())
        p_layout.addWidget(self.build_button)
        self.quick_stop = QPushButton("중단 및 저장")
        self.quick_stop.setToolTip("새 API 요청을 멈춥니다. 이미 보낸 요청은 응답을 받아 저장한 뒤 중단하며, 파일 생성은 안전한 지점에서 중단합니다.")
        self.quick_stop.clicked.connect(self.stop_review)
        p_layout.addWidget(self.quick_stop)
        self.changes_button = QPushButton("자동 수정 확인·되돌리기")
        self.changes_button.clicked.connect(self.show_quick_changes)
        self.changes_button.setEnabled(False)
        self.result_info = QLabel("제작 후 저장 위치가 여기에 표시됩니다.")
        self.result_info.setWordWrap(True)
        p_layout.addWidget(self.result_info)
        main.addWidget(creation)
        self.result_layout = p_layout
        changes = QGroupBox("제작 결과 검토")
        changes_layout = QVBoxLayout(changes)
        changes_layout.addWidget(self.changes_button)
        changes_layout.addWidget(self.editorial_button)
        layout.addWidget(changes)
        for control in (self.quick_mode, self.quick_ai, self.editorial_ai, self.learning_ai, self.depth_ai, self.allow_restructure):
            control.toggled.connect(self._update_settings_summary)
        self.max_depth.currentIndexChanged.connect(self._update_settings_summary)
        self._update_settings_summary()

    def _tools_step(self, layout, manage, advanced):
        results = QHBoxLayout()
        self.qa_button = QPushButton("보존 검사 결과 보기")
        self.qa_button.clicked.connect(self.show_qa)
        self.open_output_button = QPushButton("결과 폴더 열기")
        self.open_output_button.clicked.connect(self.open_output)
        results.addWidget(self.qa_button)
        results.addWidget(self.open_output_button)
        self.result_layout.addLayout(results)
        self.tools_panel = QGroupBox("모델 확인·비교 · 선택 사항")
        row = QVBoxLayout(self.tools_panel)
        self.tool_buttons = []
        for label, callback in (
            ("API 응답 시험 · 유료", self.api_test),
            ("내 API 키로 사용할 수 있는 모델 확인", self.check_models),
            ("모델 검색·추가", self.add_model),
            ("원고 일부로 모델 비교 · 유료", self.compare_models),
            ("이전 모델 비교 결과 보기", self.review_comparison),
        ):
            button = QPushButton(label)
            button.clicked.connect(callback)
            row.addWidget(button)
            self.tool_buttons.append(button)
        advanced.addWidget(self.tools_panel)

    def _toggle_advanced(self, checked):
        self.advanced.setVisible(checked)
        self.advanced_toggle.setText("추론 강도 바꾸기 ▾" if checked else "추론 강도 바꾸기 ▸")

    def _update_settings_summary(self, *_):
        if not hasattr(self, "settings_summary"):
            return
        automatic = self.quick_mode.isChecked() and self.quick_ai.isChecked()
        has_ai = automatic or self.depth_ai.isChecked() or (self.quick_mode.isChecked() and self.allow_restructure.isChecked())
        cost_note = ("선택한 AI 기능에는 API 비용이 발생합니다. 제작 시작 전에 요청 범위를 안내합니다."
                     if has_ai else "추가 AI 요청 없이 원문과 기존 승인 내용을 사용합니다.")
        if not self.quick_mode.isChecked():
            cost_note = "기존 승인본 제작 모드입니다. 문장 자동 교정은 제외됩니다. " + cost_note
        models = " · ".join(label.removesuffix(" 모델") + ": " +
                            model_config(self.root, self.model_boxes[role].currentData()).get("display_name", self.model_boxes[role].currentData())
                            for role, label, _ in ROLES)
        self.settings_summary.setText(cost_note + "\n저장된 모델: " + models)

    def _model_changed(self, role, combo):
        self.prefs.setValue(role, combo.currentData())
        self.model_descriptions[role].setText(model_config(self.root, combo.currentData()).get("description", ""))
        if role == self.reasoning_role.currentData():
            self._update_reasoning()
        if hasattr(self, "scope_info"):
            self.update_scope()
        self._update_settings_summary()

    @staticmethod
    def _append_model_option(combo, model):
        combo.addItem(f"{model.get('tier', '모델')} · {model.get('display_name', model['id'])}", model["id"])
        combo.setItemData(combo.count() - 1, model["id"] + "\n" + model.get("description", ""), Qt.ToolTipRole)

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
            self.file_info.setText(f"✓ 원고 선택 완료 · {path.name} · {path.stat().st_size / 1024 / 1024:.2f} MB")
            self.file_info.setToolTip(str(path))
        else:
            self.file_info.setText("DOCX 원고를 선택해 주세요.")
        if self.analyzed_path != path:
            self.source_notice.hide()
            self.resume_build = False
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
        self._fit_result_info()
        self.update_buttons()

    def _fit_result_info(self):
        # A growing result label must enlarge the scroll content, not shrink
        # to one line underneath the surrounding fixed-size controls.
        self.result_info.setMinimumHeight(max(0, self.result_info.heightForWidth(max(1, self.result_info.width()))))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'result_info'):
            QTimer.singleShot(0, self._fit_result_info)

    def update_buttons(self):
        source_ok = Path(self.source_edit.text()).is_file() and self.source_edit.text().lower().endswith(".docx")
        analyzed = source_ok and self.analyzed_path == Path(self.source_edit.text()).resolve()
        self.structure_button.setEnabled(analyzed and not self.busy)
        self.proofread_button.setEnabled(analyzed and not self.busy)
        self.stop_review_button.setEnabled(self.busy and self.is_reviewing and not self.cancel_review.is_set())
        self.build_button.setEnabled(analyzed and not self.busy)
        self.build_button.setText("이어서 제작" if self.resume_build else ("교재 만들기" if self.quick_mode.isChecked() else "기존 승인본으로 만들기"))
        self.design_theme.setEnabled(not self.busy)
        self.depth_ai.setEnabled(not self.busy)
        self.depth_existing.setEnabled(not self.busy)
        self.depth_option.setEnabled(not self.busy)
        self.max_depth.setEnabled(not self.busy and self.depth_ai.isChecked())
        self.preview_design_button.setEnabled(not self.busy)
        self.preflight_button.setEnabled(analyzed and not self.busy)
        self.allow_restructure.setEnabled(not self.busy and self.quick_mode.isChecked())
        self.quick_mode.setEnabled(not self.busy)
        self.quick_ai.setEnabled(not self.busy and self.quick_mode.isChecked())
        self.learning_ai.setEnabled(not self.busy and self.quick_mode.isChecked() and self.quick_ai.isChecked())
        self.editorial_ai.setEnabled(not self.busy and self.quick_mode.isChecked() and self.quick_ai.isChecked())
        self.editorial_button.setEnabled(analyzed and not self.busy)
        active_creation = self.busy and (self.is_reviewing or self.is_building)
        self.quick_stop.setVisible(active_creation)
        self.quick_stop.setEnabled(active_creation and not self.cancel_review.is_set())
        self.quick_stop.setText("중단 처리 중…" if self.busy and self.cancel_review.is_set() else "중단 및 저장")
        self.detail_toggle.setEnabled(not self.busy)
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
        self.changes_button.setEnabled(bool(self.last_output_folder and (self.last_output_folder / 'reports/quick-changes.html').is_file()) and not self.busy)
        self.previous_button.setEnabled(not self.busy)
        self.tool_buttons[3].setEnabled(analyzed and not self.busy)
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
        thread = start(action, lambda result: self._done(result, done), self._failed, progress, self._cancelled)
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
        self.resume_build = self.is_building
        self.busy = False
        self.is_reviewing = False
        self.is_building = False
        self.progress.setRange(0, 100)
        self.status.setText("제작 중단 · 저장된 응답으로 이어서 제작 가능" if self.resume_build else "작업 실패")
        self.update_buttons()
        QMessageBox.warning(self, "작업 실패", message)

    def _cancelled(self, message):
        self.timer.stop()
        self.resume_build = self.is_building
        self.busy = self.is_reviewing = self.is_building = False
        self.status.setText("중단 및 저장 완료 · " + ("이어서 제작을 누르면 저장된 교정을 재사용합니다." if self.resume_build else "AI 교정을 다시 시작할 수 있습니다."))
        self.progress_base = "완료된 교정은 저장됐습니다. 파일 출력은 다시 생성합니다."
        self.progress_details.setText(self.progress_base)
        self.load_suggestions()
        self.update_scope()
        self.update_buttons()

    def api_test(self):
        labels = [label for _, label, _ in ROLES]
        chosen, accepted = QInputDialog.getItem(self, "확인할 모델", "실제 API 응답을 확인할 역할", labels, 0, False)
        if not accepted:
            return
        role = ROLES[labels.index(chosen)][0]
        model = self.model_boxes[role].currentData()
        reasoning = self._effort(role)
        def finished(info):
            amount = cost(self.root, info)
            price = f"USD {amount:.6f}" if amount is not None else "가격 미설정"
            self.status.setText(f"API 응답 확인 완료 · {info['model']} · {info['elapsed_seconds']}초 · {info['input_tokens'] + info['output_tokens']} tokens · {price}")
        self.run_task("선택한 모델의 실제 API 응답 확인 중", lambda: connection_test(self.root, model, reasoning), finished)

    def add_model(self):
        def lookup():
            try:
                return addable_model_ids(self.root), False
            except Exception:
                return [], True

        def finished(result):
            ids, unavailable = result
            dialog = QDialog(self)
            dialog.setWindowTitle("AI 모델 추가")
            layout = QVBoxLayout(dialog)
            note = QLabel("API 목록은 모델 ID만 제공합니다. Responses API의 JSON 출력과 추론 강도, 가격을 공식 문서에서 확인한 뒤 등록하세요. 가격을 비우면 비용은 '가격 미설정'으로 표시됩니다.")
            note.setWordWrap(True)
            layout.addWidget(note)
            if unavailable:
                layout.addWidget(QLabel("API 목록을 가져오지 못했습니다. 모델 ID를 직접 입력할 수 있습니다."))
            form = QFormLayout()
            model_box = ClickComboBox()
            model_box.setEditable(True)
            model_box.addItems(ids)
            model_box.setEditText("")
            form.addRow("모델 ID", model_box)
            name_edit = QLineEdit()
            name_edit.setPlaceholderText("비우면 모델 ID로 표시")
            form.addRow("표시 이름", name_edit)
            efforts_edit = QLineEdit("none, low, medium, high, xhigh, max")
            form.addRow("지원 추론 강도", efforts_edit)
            input_price = QLineEdit()
            output_price = QLineEdit()
            input_price.setPlaceholderText("USD / 100만 입력 토큰 · 선택")
            output_price.setPlaceholderText("USD / 100만 출력 토큰 · 선택")
            form.addRow("입력 가격", input_price)
            form.addRow("출력 가격", output_price)
            layout.addLayout(form)
            save_button = QPushButton("선택 목록에 추가")
            layout.addWidget(save_button)

            def save():
                try:
                    if bool(input_price.text().strip()) != bool(output_price.text().strip()):
                        raise ValueError("가격은 입력·출력 값을 모두 적거나 둘 다 비워 두세요.")
                    model = {"id": model_box.currentText().strip(),
                             "display_name": name_edit.text().strip() or model_box.currentText().strip(),
                             "tier": "사용자 추가", "description": "API 사용 가능 여부와 기능은 별도로 확인하세요.",
                             "enabled": True, "comparison_default": False,
                             "reasoning_options": [item.strip() for item in efforts_edit.text().split(",") if item.strip()]}
                    if input_price.text().strip():
                        model["input_price_per_million"] = float(input_price.text().strip())
                        model["output_price_per_million"] = float(output_price.text().strip())
                    save_custom_model(self.root, model)
                except (ValueError, OSError) as exc:
                    QMessageBox.warning(dialog, "모델 추가", str(exc))
                    return
                self.config = settings(self.root)
                for combo in self.model_boxes.values():
                    self._append_model_option(combo, model)
                self.status.setText(f"{model['id']} 등록 완료 · 역할별 선택 목록에서 고를 수 있습니다.")
                dialog.accept()

            save_button.clicked.connect(save)
            dialog.exec()

        self.run_task("API 모델 목록 확인 중", lookup, finished)

    def check_models(self):
        def lookup():
            try:
                return available_models(self.root)
            except Exception:
                return {"error": True}
        def finished(result):
            if result.get("error"):
                self.status.setText("설정된 모델 목록을 사용합니다")
                QMessageBox.information(self, "등록 모델 API 사용 가능 확인", "API 모델 목록을 확인할 수 없습니다. 등록된 모델 목록은 그대로 표시합니다.")
                return
            available = result["available"]
            missing = result["unavailable"]
            self.status.setText(f"설정된 모델 {len(available)}개 사용 가능")
            QMessageBox.information(self, "등록 모델 API 사용 가능 확인", "API 목록에서 확인됨: " + ", ".join(available) +
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
        from app.controllers.publishing import preflight, diagnostic_summary
        try:
            diagnostic = preflight(job)
            self.preflight_info.setText('사전 진단: ' + diagnostic_summary(diagnostic))
            self.source_notice.setText(diagnostic_summary(diagnostic) + " · <a href='details'>진단 결과 보기</a>")
            self.source_notice.setVisible(not diagnostic['passed'])
        except (ValueError, OSError) as exc:
            self.preflight_info.setText("사전 진단 실패: " + str(exc))
            self.source_notice.setText("원고 진단 실패 · <a href='details'>원인 확인하기</a>")
            self.source_notice.show()
        try:
            structure = job.structure().load()
            self.structure_info.setText("목차 구성: " + (f"{len(structure['nodes'])}개 · " + ("승인됨" if structure["status"] == "approved" else "초안 · 승인 필요") if structure else "자동 제작 시 사전 진단을 통과한 목차를 사용합니다."))
        except ValueError:
            self.structure_info.setText("목차 구성: 원고 정보가 변경되어 다시 분석해야 합니다.")
        if self.depth_ai.isChecked():
            self.structure_info.setText("목차 구성: 제작 시 AI가 필요한 하위 제목을 생성하여 바로 적용합니다.")
        counts = {}
        for block in master.blocks:
            counts[block.kind] = counts.get(block.kind, 0) + 1
        image_count = sum(len(block.assets) for block in master.blocks)
        links = sum(len(block.links) for block in master.blocks)
        self.analysis_info.setText(f"✓ 원고 준비 완료 · 본문 문단 {counts.get('paragraph', 0)}개 · 이미지 {image_count} · 코드 {counts.get('code-block', 0)} · 표 {counts.get('table', 0)} · 링크 {links}")
        self.status.setText("원고 준비 완료 · 제작 설정을 확인하고 ‘교재 만들기’를 누르세요.")
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
        self.status.setText("중단 요청됨 · 새 요청은 보내지 않습니다. 진행 중인 API 응답 저장 또는 파일 처리 정리를 기다립니다.")
        self.update_buttons()

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
        if not self.cancel_review.is_set():
            self.status.setText(info["phase"])
        self.progress.setValue(info["percent"])

    def _depth_mode_changed(self):
        if self.depth_ai.isChecked():
            self.structure_info.setText("목차 구성: 제작 시 AI가 필요한 하위 제목을 생성하여 바로 적용합니다.")
        else:
            self.structure_info.setText("목차 구성: 기존 원고의 구조를 사용합니다.")
        self.update_buttons()

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
        if not self.quick_mode.isChecked() and unresolved and QMessageBox.question(self, "제작할 내용 확인", f"미검토·보류·다시 검토 필요 항목이 {unresolved}건 있습니다.\n이 항목은 반영하지 않고, 현재 승인한 내용으로 제작할까요?") != QMessageBox.Yes:
            return
        formats = [key for key, box in self.format_boxes.items() if box.isChecked()]
        if not formats:
            QMessageBox.warning(self, "출력 형식", "출력 형식을 하나 이상 선택해 주세요.")
            return
        destination = Path(self.output_edit.text())
        chosen = None if destination == job.default_output_base else destination
        quick = self.quick_mode.isChecked()
        run_ai = quick and self.quick_ai.isChecked()
        model = self.model_boxes['proofreading'].currentData()
        reasoning = self._effort('proofreading')
        self.cancel_review.clear()
        allow_restructure = quick and self.allow_restructure.isChecked()
        structure_model = self.model_boxes['technical_review'].currentData()
        structure_reasoning = self._effort('technical_review')
        theme = self.design_theme.currentData()
        depth_mode = self.depth_ai.isChecked()
        max_depth = self.max_depth.currentData()
        automatic_models = {role: (box.currentData(), self._effort(role)) for role, box in self.model_boxes.items()}
        learning = run_ai and self.learning_ai.isChecked()
        editorial_ai = run_ai and self.editorial_ai.isChecked()
        request_lines = []
        if run_ai:
            from core.ai.automatic import plan
            try:
                _, eligible, _ = plan(job)
            except (ValueError, OSError) as exc:
                QMessageBox.warning(self, '자동 출판 준비 실패', str(exc))
                return
            request_lines.append(f'문장 교정: 대상 {len(eligible)}문단 · 최대 {len(eligible)*3}회 요청\n'
                                 '최대 3문단씩 묶어 교정·기술 검토하며, 동시에 최대 2개 요청을 처리합니다.\n'
                                 '변경 문장은 원문 순서로 개별 재검사 후 반영합니다.')
        if depth_mode:
            request_lines.append(f'소제목 자동 보완: 절별로 분석하여 최대 {max_depth}단계 제목까지 추가합니다. 목차 AI 요청은 별도입니다.')
        if allow_restructure:
            request_lines.append('새 목차 구성: 기본 목차가 부족할 때 AI에 제목 구성을 요청합니다.')
        if learning:
            request_lines.append('학습 문제 추가: 부족한 절·장마다 생성과 검수 각 1회. 본문·코드를 읽기 전용 근거로 전송합니다.')
        if editorial_ai:
            request_lines.append('문장 최종 검사: 최대 4,000자 묶음마다 순서대로 검사합니다. 응답 대기시간은 120초입니다.')
        if request_lines:
            models_text = '\n'.join(label + ': ' + str(automatic_models[role][0]) for role,label,_ in ROLES) if run_ai else '목차 분석 모델: ' + str(structure_model)
            if QMessageBox.question(self, 'AI 사용 범위와 비용 확인',
                '\n\n'.join(request_lines) + '\n\n저장된 응답은 재사용합니다. API 비용은 원고 길이·모델·응답량에 따라 달라집니다.\n'
                + models_text + '\n\n이 설정으로 교재를 만들까요?') != QMessageBox.Yes:
                return
        self.is_reviewing = run_ai or allow_restructure or depth_mode
        self.is_building = True
        cancelled = self.cancel_review.is_set
        def produce(emit):
            if quick or depth_mode:
                from app.controllers.publishing import publish
                return publish(job, formats, chosen, emit, run_ai=run_ai, model=model, reasoning=reasoning,
                    allow_restructure=allow_restructure, structure_model=structure_model,
                    structure_reasoning=structure_reasoning, cancelled=cancelled, theme=theme,
                    depth_mode=depth_mode, max_depth=max_depth, quick=False,
                    automatic_models=automatic_models if run_ai else None, learning=learning, editorial_ai=editorial_ai)
            return job.build(formats, chosen, emit, quick=False, theme=theme, cancelled=cancelled)
        self.run_task("교재 제작 준비 중", produce, self._build_done, self._phase_progress)

    def _build_done(self, result):
        self.is_reviewing = False
        self.is_building = self.resume_build = False
        self.load_suggestions()
        self.update_scope()
        self.last_output_folder = Path(result["folder"])
        self.last_report = Path(result["report"])
        self.prefs.setValue("output_dir", self.output_edit.text())
        self.status.setText("결과물 제작 완료 · 품질 검사 " + ("통과" if result["qa"]["passed"] and not result["qa"].get("warnings") else "확인 필요"))
        lines = [f"{'HTML' if kind == 'web' else kind.upper()}: {path}" for kind, path in result["outputs"].items()]
        lines.append(f"품질 검사: {result['report']}")
        self.result_info.setText("제작 완료: " + ", ".join("HTML" if k == "web" else k.upper() for k in result["outputs"]) + "\n저장 폴더: " + result["folder"])
        self.result_info.setToolTip("\n".join(lines))
        if result.get('design'):
            self.result_info.setText(self.result_info.text() + '\n디자인: ' + result['design']['name'])
        if result.get('editorial'):
            self.result_info.setText(self.result_info.text() + '\n출판 완결성: ' +
                ('추가 확인 필요' if result['editorial']['status'] == 'REVIEW_REQUIRED' else '자동 검사 통과 · 사람의 최종 승인 별도'))
        if result.get('learning'):
            self.result_info.setText(self.result_info.text() + f"\n추가 학습 문제: {result['learning']['question_count']}개 · 정답·해설 포함")
        if result.get('quick') is not None:
            q = result['quick']
            if q.get('policy', '').startswith('automatic-publication'):
                summary = f"기존 승인 {q['manual_approved_count']}문단 유지 · 자동 수정 {q['applied_count']}건 · 확인 필요 {q['retained_count']}건 · 보호/사용자 제외 {q['protected_count']}문단"
                self.result_info.setText(self.result_info.text() + '\n' + summary)
            else:
                self.result_info.setText(self.result_info.text() + f"\n제한 교정 {q['applied_count']}건 적용 · 미검토 제안 {q['retained_count']}건 미적용")
        self._fit_result_info()
        self.update_buttons()

    def show_editorial_report(self):
        job = self.production()
        if not job:
            return
        path = job.work / 'editorial-qa.html'
        if not path.is_file():
            from core.qa import editorial
            path = editorial.save(editorial.report(job.workflow().output_master()), job.work)
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(path))):
            QMessageBox.warning(self, '검사 보고서', '보고서 위치: ' + str(path))

    def preview_design(self):
        from core.export.preview import create_preview
        from core.export.themes import resolve
        try:
            selected = self.design_theme.currentData()
            source = Path(self.source_edit.text())
            if selected == 'auto' and source.is_file() and source.suffix.lower() == '.docx':
                job = Production(self.root, source)
                if (job.work / 'structured-master.json').is_file():
                    selected = resolve(job.master())['id']
            path = create_preview(self.root / 'reports/design-preview', selected)
            if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(path))):
                raise RuntimeError('브라우저를 열 수 없습니다. 미리보기 파일: ' + str(path))
        except Exception as exc:
            QMessageBox.warning(self, '디자인 미리보기', str(exc))

    def show_preflight(self):
        job = self.production()
        if job:
            from app.controllers.publishing import preflight, diagnostic_summary
            try:
                report = preflight(job)
                dialog = QMessageBox(self)
                dialog.setWindowTitle('원고 사전 진단')
                dialog.setIcon(QMessageBox.Information)
                dialog.setText(diagnostic_summary(report))
                dialog.setInformativeText(f"목차 후보 {len(report['nodes'])}개\n" + report['note'])
                if report['issues']:
                    dialog.setDetailedText('\n'.join(i['block_id'] + ' · ' + i['message'] for i in report['issues']))
                open_report = dialog.addButton('전체 보고서 열기', QMessageBox.ActionRole)
                dialog.addButton('닫기', QMessageBox.RejectRole)
                for button in dialog.buttons():
                    if button.text() == 'Show Details...':
                        button.setText('상세 항목 보기')
                dialog.exec()
                if dialog.clickedButton() is open_report:
                    QDesktopServices.openUrl(QUrl.fromLocalFile(str(job.work / 'preflight.html')))
            except (ValueError, OSError) as exc:
                QMessageBox.warning(self, "사전 진단", str(exc))

    def show_quick_changes(self):
        if self.last_output_folder:
            from core.ai.workflow import read_json
            report = read_json(self.last_output_folder / 'reports/quick-changes.json', {})
            if report.get('policy', '').startswith('automatic-publication'):
                from app.gui.automatic_changes import show_changes
                job = self.production()
                if job:
                    show_changes(self, job, report, self.last_output_folder)
                return
            path = self.last_output_folder / 'reports/quick-changes.html'
            if path.is_file():
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

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
        count = int(self.config.get("max_comparison_samples", 5))
        note = QLabel(f"같은 원고에서 교정 가능한 앞부분 최대 {count}개 문단을 선택한 모델들이 각각 교정합니다. API 비용이 발생하며, 비교 제안은 원고에 자동 적용되지 않습니다.")
        note.setWordWrap(True)
        layout.addWidget(note)
        choices = []
        for model in self.config["models"]:
            if not model.get("enabled", True):
                continue
            box = QCheckBox(f"{model.get('tier', '')} · {model.get('display_name', model['id'])}")
            box.setToolTip(model["id"] + "\n" + model.get("description", ""))
            box.setChecked(model.get("comparison_default", model.get("tier") in ("빠름/저비용", "균형", "정밀")))
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
