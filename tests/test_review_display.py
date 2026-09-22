import os

import pytest

from app.gui.review_display import diff_segments


@pytest.mark.parametrize('source,target', [
    ('  <iostream> & "값"\n\n\t원문', '  <iostream> & "값"\n\n\t수정문'),
    ('삭제할 문장', ''), ('', '추가한 문장'),
    ('동일한 문장', '동일한 문장'), ('가\r\n나', '가\n나'),
])
def test_diff_reconstructs_exact_manuscript_strings(source, target):
    before, after = diff_segments(source, target)
    assert ''.join(text for text, _ in before) == source
    assert ''.join(text for text, _ in after) == target
    if source == target:
        assert not any(changed for _, changed in before + after)


def test_comparison_displays_literal_markup_and_whitespace():
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    from PySide6.QtWidgets import QApplication
    from app.gui.review_display import comparison_dialog
    from app.gui.theme import apply_light_theme
    from PySide6.QtGui import QPalette
    app = QApplication.instance() or QApplication([])
    apply_light_theme(app)
    source = '<b>원문 & 내용</b>\n\n\t  유지'
    target = '<b>수정 & 내용</b>\n\n\t  유지'
    dialog = comparison_dialog(None, source, target, '이유 <검토>', '미검토')
    assert [e.toPlainText() for e in dialog.comparison_editors] == [source, target]
    assert app.palette().color(QPalette.Window).lightness() > 230
    assert app.palette().color(QPalette.Text).lightness() < 100
    dialog.close()
