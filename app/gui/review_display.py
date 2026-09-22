"""Presentation-only text differences; stored manuscript strings are never changed."""
from difflib import SequenceMatcher

from PySide6.QtCore import Qt
from PySide6.QtGui import (
    QColor, QFont, QPalette, QTextBlockFormat, QTextCharFormat, QTextCursor,
    QTextDocument, QTextOption,
)
from PySide6.QtWidgets import (
    QApplication, QDialog, QDialogButtonBox, QHBoxLayout, QLabel,
    QStyle, QStyledItemDelegate, QStyleOptionViewItem, QTextEdit, QVBoxLayout,
)

SEGMENTS_ROLE = Qt.UserRole + 10
STATUS_ROLE = Qt.UserRole + 11
STATUS_COLORS = {
    'approved': ('#e0f2e8', '#17613a'), 'rejected': ('#fee7e7', '#922b35'),
    'hold': ('#fff4cf', '#755600'), 'pending': ('#edf1f5', '#475569'),
    'superseded': ('#ece9f6', '#605077'), 'outdated': ('#ffedd5', '#92400e'),
}


def diff_segments(source, target):
    before, after = [], []
    for tag, a, b, c, d in SequenceMatcher(None, source, target, autojunk=False).get_opcodes():
        if b > a:
            before.append((source[a:b], tag != 'equal'))
        if d > c:
            after.append((target[c:d], tag != 'equal'))
    return before, after


def text_document(segments, font, side, parent=None):
    doc = QTextDocument(parent)
    doc.setDefaultFont(font)
    doc.setDocumentMargin(8)
    option = QTextOption()
    option.setWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere)
    doc.setDefaultTextOption(option)
    cursor = QTextCursor(doc)
    block = QTextBlockFormat()
    block.setLineHeight(135, QTextBlockFormat.ProportionalHeight.value)
    cursor.setBlockFormat(block)
    for text, changed in segments:
        fmt = QTextCharFormat()
        fmt.setForeground(QColor('#243247'))
        if changed:
            fmt.setBackground(QColor('#fde3e3' if side == 'source' else '#d9f1e3'))
            fmt.setForeground(QColor('#922b35' if side == 'source' else '#17613a'))
            fmt.setFontWeight(QFont.DemiBold)
            fmt.setFontUnderline(True)
        cursor.insertText(text, fmt)
    return doc


class ReviewTextDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        text = opt.text
        opt.text = ''
        style = opt.widget.style() if opt.widget else QApplication.style()
        style.drawControl(QStyle.CE_ItemViewItem, opt, painter, opt.widget)
        segments = index.data(SEGMENTS_ROLE)
        doc = text_document(segments if segments is not None else [(text, False)], opt.font,
                            'source' if index.column() == 1 else 'target')
        doc.setTextWidth(opt.rect.width())
        painter.save()
        painter.setClipRect(opt.rect)
        painter.translate(opt.rect.topLeft())
        doc.drawContents(painter)
        painter.restore()


class StatusDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        label = opt.text
        opt.text = ''
        style = opt.widget.style() if opt.widget else QApplication.style()
        style.drawControl(QStyle.CE_ItemViewItem, opt, painter, opt.widget)
        bg, fg = STATUS_COLORS.get(index.data(STATUS_ROLE), STATUS_COLORS['pending'])
        rect = opt.rect.adjusted(6, 0, -6, 0)
        rect.setTop(opt.rect.center().y() - 15)
        rect.setHeight(30)
        painter.save()
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(bg))
        painter.drawRoundedRect(rect, 5, 5)
        painter.setPen(QColor(fg))
        painter.setFont(opt.font)
        painter.drawText(rect, Qt.AlignCenter, label)
        painter.restore()


def comparison_dialog(parent, source, target, reason, details):
    dialog = QDialog(parent)
    dialog.setWindowTitle('수정 제안 비교')
    dialog.resize(1020, 670)
    layout = QVBoxLayout(dialog)
    legend = QLabel('밑줄과 색으로 변경 부분을 표시합니다. 원문: 삭제·변경 / 수정 제안: 추가·변경')
    legend.setWordWrap(True)
    layout.addWidget(legend)
    columns = QHBoxLayout()
    before, after = diff_segments(source, target)
    font = QFont('Malgun Gothic', 11)
    dialog.comparison_editors = []
    for title, segments, side in (('원문 / 이 단계의 기준 문장', before, 'source'), ('수정 제안', after, 'target')):
        column = QVBoxLayout()
        column.addWidget(QLabel(title))
        editor = QTextEdit()
        editor.setReadOnly(True)
        editor.setDocument(text_document(segments, font, side, editor))
        column.addWidget(editor)
        columns.addLayout(column, 1)
        dialog.comparison_editors.append(editor)
    layout.addLayout(columns, 1)
    layout.addWidget(QLabel('수정 이유와 검토 상태'))
    explanation = QTextEdit()
    explanation.setReadOnly(True)
    explanation.setPlainText(reason + '\n\n' + details)
    explanation.setMaximumHeight(130)
    layout.addWidget(explanation)
    buttons = QDialogButtonBox(QDialogButtonBox.Close)
    buttons.button(QDialogButtonBox.Close).setText('닫기')
    buttons.rejected.connect(dialog.reject)
    layout.addWidget(buttons)
    return dialog
