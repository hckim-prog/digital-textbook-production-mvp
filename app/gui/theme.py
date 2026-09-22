"""App-owned light palette, independent of the Windows color theme."""
from pathlib import Path
from PySide6.QtGui import QColor, QFont, QPalette


def apply_light_theme(app):
    app.setStyle('Fusion')
    app.setFont(QFont('Malgun Gothic', 10))
    palette = QPalette()
    colors = {
        'Window': '#f3f5f8', 'WindowText': '#243247', 'Base': '#ffffff',
        'AlternateBase': '#f7f9fc', 'Text': '#243247', 'Button': '#f5f7fa',
        'ButtonText': '#243247', 'Highlight': '#dbeafe', 'HighlightedText': '#172e50',
        'ToolTipBase': '#ffffff', 'ToolTipText': '#243247', 'Link': '#1d4ed8',
        'PlaceholderText': '#64748b', 'Light': '#ffffff', 'Midlight': '#eef2f6',
        'Mid': '#cbd5e1', 'Dark': '#64748b', 'Shadow': '#94a3b8',
    }
    for role, color in colors.items():
        palette.setColor(getattr(QPalette, role), QColor(color))
    for role in (QPalette.Text, QPalette.WindowText, QPalette.ButtonText):
        palette.setColor(QPalette.Disabled, role, QColor('#738095'))
    app.setPalette(palette)
    stylesheet = '''
        QMainWindow, QDialog { background: #f3f5f8; }
        QGroupBox { background: white; border: 1px solid #d6dde7; border-radius: 8px;
                    margin-top: 14px; padding: 14px 12px 10px; font-weight: 600; }
        QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 5px; color: #243247; }
        QLabel { background: transparent; }
        QScrollArea { border: none; }
        QLineEdit, QComboBox, QSpinBox, QTextEdit { background: white; color: #243247;
                    border: 1px solid #c5cfdd; border-radius: 5px; padding: 5px; }
        QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QTextEdit:focus { border-color: #2563eb; }
        QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled { background: #edf1f5; color: #738095; }
        QComboBox QAbstractItemView { background: white; color: #243247;
                    selection-background-color: #dbeafe; selection-color: #172e50; }
        QComboBox::drop-down { border: none; width: 24px; }
        QCheckBox { spacing: 6px; }
        QCheckBox::indicator { width: 16px; height: 16px; border: 1px solid #94a3b8;
                    border-radius: 3px; background: white; }
        QCheckBox::indicator:checked { background: #2563eb; border-color: #2563eb; image: url("__CHECK__"); }
        QCheckBox::indicator:disabled { background: #dce3ed; border-color: #bac5d5; }
        QPushButton, QToolButton { background: #f5f7fa; color: #243247; border: 1px solid #c5cfdd;
                    border-radius: 5px; padding: 6px 12px; }
        QPushButton:hover, QToolButton:hover { background: #e9eff8; border-color: #94a8c5; }
        QPushButton:pressed, QToolButton:pressed { background: #dbeafe; }
        QPushButton:focus, QToolButton:focus { border: 2px solid #2563eb; }
        QPushButton[primary="true"] { background: #2563eb; border-color: #2563eb; color: white; font-weight: 600; }
        QPushButton[primary="true"]:hover { background: #1d4ed8; }
        QPushButton:disabled, QToolButton:disabled { background: #edf1f5; color: #738095; border-color: #d6dde7; }
        QTableView { background: white; alternate-background-color: #f7f9fc; color: #243247;
                    border: 1px solid #d6dde7; gridline-color: #e2e8f0;
                    selection-background-color: #dbeafe; selection-color: #172e50; }
        QHeaderView::section { background: #eef2f7; color: #334155; padding: 7px 5px;
                    border: none; border-right: 1px solid #d6dde7; border-bottom: 1px solid #d6dde7; font-weight: 600; }
        QProgressBar { background: #e2e8f0; color: #243247; border: none; border-radius: 5px;
                    min-height: 18px; text-align: center; }
        QProgressBar::chunk { background: #93b9fa; border-radius: 5px; }
        QToolTip { background: white; color: #243247; border: 1px solid #c5cfdd; padding: 5px; }
    '''
    app.setStyleSheet(stylesheet.replace('__CHECK__', (Path(__file__).parent / 'assets/check.svg').as_posix()))
