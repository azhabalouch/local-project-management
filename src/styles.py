"""
Centralized enterprise visual theme.

Holds the shared colour palette (reused by the hand-styled buttons and by
the Gantt/Milestone status colours in charts.py) and a single global QSS
stylesheet, applied once at the QApplication level in app.py, so every
default Qt widget - text inputs, combo boxes, trees, scrollbars, tabs,
dialogs - matches the accent-coloured buttons instead of falling back to
the plain OS look.
"""

# --- Palette -------------------------------------------------------------
NAVY = "#172B4D"           # primary text / headings
SLATE = "#5E6C84"          # secondary / muted text
BLUE = "#0052CC"           # primary actions, links, active/selected states
BLUE_DARK = "#0747A6"      # hover state for primary actions
GREEN = "#36B37E"          # constructive actions (create, save, export)
RED = "#DE350B"            # destructive actions (delete)
AMBER = "#FF991F"          # warnings / on-hold status
BORDER = "#DFE1E6"
SURFACE = "#FFFFFF"
BACKGROUND = "#F4F5F7"
BACKGROUND_ALT = "#EBECF0"

FONT_FAMILY = "'Segoe UI', 'Inter', -apple-system, sans-serif"

# --- Beginner-friendly iconography ---------------------------------------
# Small emoji glyphs used throughout the UI (tab labels, cards, headers) so
# a first-time user can recognize a section by shape/color, not just text.
TAB_ICONS = {
    "List View": "\U0001F4CB",       # clipboard
    "Board View": "\U0001F5C2\uFE0F",  # card index
    "Edit View": "\u270F\uFE0F",      # pencil
    "Gantt Chart": "\U0001F4C6",      # calendar
    "Milestone Chart": "\U0001F3C1",  # checkered flag
    "Critical Path": "\U0001F517",    # link
    "Settings": "\u2699\uFE0F",       # gear
    "Trash": "\U0001F5D1\uFE0F",      # wastebasket
}

STATUS_ICONS = {
    "Not Started": "\u26aa",   # white circle
    "In Progress": "\U0001F535",  # blue circle
    "On Hold": "\U0001F7E0",   # orange circle
    "Completed": "\U0001F7E2",  # green circle
}

PRIORITY_ICONS = {
    "Low": "\U0001F53D",     # down arrow
    "Medium": "\u26AA",
    "High": "\U0001F53A",    # up-pointing red triangle-ish
}


def button_style(bg: str, fg: str = "white", padding: str = "8px 16px") -> str:
    """Shared recipe for the app's accent-coloured call-to-action buttons."""
    return (f"background-color: {bg}; color: {fg}; padding: {padding}; "
            f"font-weight: 600; font-size: 13px; border: none; "
            f"border-radius: 6px;")


def hint_style() -> str:
    """Shared recipe for the small italic 'how this screen works' hint
    labels sprinkled across tabs, so first-time users always have a plain-
    language explainer without hunting for a manual."""
    return (f"color: {SLATE}; font-size: 12px; font-style: italic; "
            f"padding: 2px 2px 6px 2px;")


ENTERPRISE_STYLESHEET = f"""
* {{
    font-family: {FONT_FAMILY};
}}
QMainWindow, QWidget {{
    background-color: {BACKGROUND};
    color: {NAVY};
}}
QDialog {{
    background-color: {SURFACE};
}}
QLabel {{
    color: {NAVY};
}}
QPushButton {{
    background-color: {SURFACE};
    color: {NAVY};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 7px 14px;
    font-weight: 600;
}}
QPushButton:hover {{
    background-color: {BACKGROUND_ALT};
}}
QPushButton:pressed {{
    background-color: {BORDER};
}}
QPushButton:disabled {{
    color: {SLATE};
    background-color: {BACKGROUND_ALT};
}}
QLineEdit, QTextEdit, QComboBox, QDateEdit, QSpinBox {{
    background-color: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 4px;
    padding: 6px 8px;
    selection-background-color: {BLUE};
}}
QLineEdit:focus, QTextEdit:focus, QComboBox:focus, QDateEdit:focus, QSpinBox:focus {{
    border: 1px solid {BLUE};
}}
QComboBox::drop-down {{
    border: none;
    width: 22px;
}}
QTreeWidget, QListWidget, QTableWidget {{
    background-color: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 6px;
    alternate-background-color: {BACKGROUND};
    outline: 0;
}}
QHeaderView::section {{
    background-color: {BACKGROUND_ALT};
    color: {NAVY};
    font-weight: 600;
    padding: 6px;
    border: none;
    border-bottom: 1px solid {BORDER};
}}
QTreeWidget::item, QListWidget::item {{
    padding: 4px;
}}
QTreeWidget::item:selected, QListWidget::item:selected {{
    background-color: {BLUE};
    color: white;
}}
QScrollBar:vertical {{
    background: {BACKGROUND};
    width: 10px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {BORDER};
    border-radius: 5px;
    min-height: 24px;
}}
QScrollBar::handle:vertical:hover {{
    background: {SLATE};
}}
QScrollBar::add-line, QScrollBar::sub-line {{
    height: 0;
    width: 0;
}}
QScrollBar:horizontal {{
    background: {BACKGROUND};
    height: 10px;
}}
QScrollBar::handle:horizontal {{
    background: {BORDER};
    border-radius: 5px;
    min-width: 24px;
}}
QMessageBox {{
    background-color: {SURFACE};
}}
QTabWidget::pane {{
    border: 0;
    background-color: {SURFACE};
}}
QTabBar::tab {{
    background: {BACKGROUND_ALT};
    color: {SLATE};
    padding: 10px 22px;
    margin-right: 2px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    font-size: 13px;
    font-weight: 600;
}}
QTabBar::tab:selected {{
    background: {SURFACE};
    color: {BLUE};
    border-bottom: 2px solid {BLUE};
}}
QTabBar::tab:hover:!selected {{
    background: {BORDER};
}}
QToolTip {{
    background-color: {NAVY};
    color: white;
    border: 1px solid {NAVY};
    border-radius: 4px;
    padding: 6px 8px;
    font-size: 12px;
}}
"""
