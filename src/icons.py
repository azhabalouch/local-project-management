"""
Central icon registry for the whole app.

Uses qtawesome (https://github.com/spyder-ide/qtawesome), which ships the
Font Awesome 5 + Material Design Icons glyph fonts *inside the Python
package*. That means every icon in this file renders identically whether
the machine is online or fully offline - nothing is fetched over the
network at runtime, and there are no emoji/system-font glyphs involved
anywhere in the UI.

Keeping every icon name + colour choice in one place also means the visual
language (weight, size, palette) stays consistent across tabs instead of
each view inventing its own.
"""
from functools import lru_cache

import qtawesome as qta
from PyQt6.QtGui import QIcon

from styles import INK, MUTED, ACCENT, SUCCESS, DANGER, WARNING, SUBTLE

# --- Semantic name -> Font Awesome / Material glyph -----------------------
# One place to swap the whole app's iconography later if needed.
NAMES = {
    # Tabs
    "list_view": "fa5s.list-ul",
    "board_view": "fa5s.columns",
    "edit_view": "fa5s.pen",
    "gantt_chart": "fa5s.chart-bar",
    "milestone_chart": "fa5s.flag-checkered",
    "critical_path": "fa5s.link",
    "settings": "fa5s.sliders-h",
    "trash": "fa5s.trash-alt",
    "no_data": "fa5s.folder-open",
    "plan_view": "fa5s.file-alt",
    "sketch_view": "fa5s.pen-nib",

    # Actions
    "add": "fa5s.plus",
    "minus": "fa5s.minus",
    "new_project": "fa5s.folder-plus",
    "delete": "fa5s.trash-alt",
    "search": "fa5s.search",
    "restore": "fa5s.undo",
    "export_pdf": "fa5s.file-pdf",
    "copy": "fa5s.copy",
    "save": "fa5s.check",
    "close": "fa5s.times",
    "hint": "fa5s.lightbulb",
    "warning": "fa5s.exclamation-triangle",
    "empty": "fa5s.inbox",
    "rocket": "fa5s.rocket",
    "checklist": "fa5s.check-double",
    "shield": "fa5s.shield-alt",
    "layout": "fa5s.th-large",

    # Plan tab (rich-text toolbar)
    "bold": "fa5s.bold",
    "italic": "fa5s.italic",
    "underline": "fa5s.underline",
    "bullet_list": "fa5s.list-ul",
    "ordered_list": "fa5s.list-ol",

    # Sketch tab (Miro-style board toolbar)
    "tool_select": "fa5s.mouse-pointer",
    "tool_pen": "fa5s.pen",
    "tool_rectangle": "fa5s.square",
    "tool_ellipse": "fa5s.circle",
    "tool_note": "fa5s.sticky-note",
    "tool_eraser": "fa5s.eraser",
    "zoom_in": "fa5s.search-plus",
    "zoom_out": "fa5s.search-minus",
    "clear_board": "fa5s.broom",
    "custom_color": "fa5s.palette",

    # To-do checkbox states
    "todo_open": "fa5s.square",
    "todo_done": "fa5s.check-square",

    # Priority
    "priority_low": "fa5s.chevron-down",
    "priority_medium": "fa5s.equals",
    "priority_high": "fa5s.chevron-up",

    # Generic status dot
    "dot": "fa5s.circle",
}

TAB_ICON_KEYS = {
    "List View": "list_view",
    "Board View": "board_view",
    "Edit View": "edit_view",
    "Gantt Chart": "gantt_chart",
    "Milestone Chart": "milestone_chart",
    "Critical Path": "critical_path",
    "Plan": "plan_view",
    "Sketch": "sketch_view",
    "Settings": "settings",
    "Trash": "trash",
    "No Data": "no_data",
}

STATUS_COLORS = {
    "Not Started": MUTED,
    "In Progress": ACCENT,
    "On Hold": WARNING,
    "Completed": SUCCESS,
}

PRIORITY_COLORS = {
    "Low": SUCCESS,
    "Medium": WARNING,
    "High": DANGER,
}

PRIORITY_ICON_KEYS = {
    "Low": "priority_low",
    "Medium": "priority_medium",
    "High": "priority_high",
}


@lru_cache(maxsize=256)
def icon(key: str, color: str = INK) -> QIcon:
    """Returns a cached QIcon for a semantic icon key (see NAMES above)."""
    glyph = NAMES.get(key, key)
    return qta.icon(glyph, color=color)


def status_icon(status: str) -> QIcon:
    """A small filled dot QIcon colour-coded to a task's status."""
    return icon("dot", color=STATUS_COLORS.get(status, MUTED))


def priority_icon(priority: str) -> QIcon:
    """A directional chevron QIcon colour-coded to a task's priority."""
    return icon(PRIORITY_ICON_KEYS.get(priority, "priority_medium"),
               color=PRIORITY_COLORS.get(priority, MUTED))


def tab_icon(tab_label: str, color: str = MUTED) -> QIcon:
    """QIcon for a tab, keyed off its plain (icon-free) label."""
    return icon(TAB_ICON_KEYS.get(tab_label, "layout"), color=color)


def todo_icon(is_completed: bool) -> QIcon:
    return icon("todo_done" if is_completed else "todo_open",
               color=SUCCESS if is_completed else SUBTLE)
