"""
Small, reusable widget-composition helpers shared by views.py, charts.py,
and dialogs.py - keeps the "icon + text" pattern (search boxes, hint
strips, empty states) consistent and DRY instead of each screen wiring
its own QHBoxLayout for the same thing.
"""
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QLabel, QLineEdit

from icons import icon
from styles import MUTED, SUBTLE, hint_style


def add_search_icon(line_edit: QLineEdit):
    """Adds a small leading search-glyph inside a QLineEdit, replacing the
    old emoji-in-placeholder-text pattern with a real vector icon."""
    return line_edit.addAction(icon("search", color=SUBTLE),
                               QLineEdit.ActionPosition.LeadingPosition)


def hint_row(text: str) -> QWidget:
    """A small 'how this screen works' caption row: a lightbulb icon
    followed by muted explanatory text."""
    row = QWidget()
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 2, 0, 6)
    layout.setSpacing(6)

    icon_label = QLabel()
    icon_label.setPixmap(icon("hint", color=MUTED).pixmap(13, 13))
    icon_label.setFixedWidth(16)

    text_label = QLabel(text)
    text_label.setWordWrap(True)
    text_label.setStyleSheet(hint_style())

    layout.addWidget(icon_label, alignment=Qt.AlignmentFlag.AlignTop)
    layout.addWidget(text_label, stretch=1)
    return row
