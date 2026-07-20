"""
The Plan tab: a free-form, word-processor-style writing surface for the
active project (bold/italic/underline/lists, like a lightweight Word doc),
plus a separate checklist underneath for tracking the plan's own to-dos.

Kept as its own module (mirroring charts.py, dialogs.py, widgets.py) since
it owns a genuinely different interaction model - continuous rich-text
editing with debounced autosave - from the tree/list-based tabs in
views.py.
"""
from typing import Optional

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                             QTextEdit, QPushButton, QListWidget,
                             QListWidgetItem, QLineEdit, QMenu, QFrame)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont, QTextCursor, QTextListFormat

from data import FileManager, ToDo
from styles import (INK, MUTED, SUBTLE, ACCENT, BORDER, SURFACE,
                    BACKGROUND, hint_style, card_style, SPACE_SM, SPACE_MD,
                    SPACE_LG)
from icons import icon
from widgets import hint_row

# How long to wait after the user stops typing before writing the plan's
# rich text to disk. Long enough to not thrash the filesystem on every
# keystroke, short enough that a crash never loses more than a moment's
# work.
AUTOSAVE_DELAY_MS = 700


class PlanView(QWidget):
    """
    A Word-like writing surface for the active project, with a checklist
    of plan-related to-dos underneath.

    The rich text body autosaves on a short debounce timer after the user
    stops typing; the checklist (adding, checking, deleting an item)
    saves immediately since those are discrete, deliberate actions rather
    than a continuous stream of keystrokes.

    Attributes:
        active_project (Project): The currently loaded project data.
        file_manager (FileManager): Used to persist the plan document and
            checklist.
    """

    def __init__(self, active_project, file_manager: FileManager):
        super().__init__()
        self.active_project = active_project
        self.file_manager = file_manager

        self._autosave_timer = QTimer(self)
        self._autosave_timer.setSingleShot(True)
        self._autosave_timer.setInterval(AUTOSAVE_DELAY_MS)
        self._autosave_timer.timeout.connect(self._save_content)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(SPACE_LG, SPACE_LG, SPACE_LG, SPACE_LG)
        layout.setSpacing(SPACE_SM)

        heading = QLabel("Plan")
        heading.setProperty("role", "heading")
        layout.addWidget(heading)
        layout.addWidget(hint_row(
            "Write the plan out in full - like a Word document - then use "
            "the checklist below to tick off the plan's own to-dos as you "
            "go. Everything here saves automatically."))

        # --- Formatting toolbar ---
        toolbar = QHBoxLayout()
        toolbar.setSpacing(SPACE_SM)
        self.bold_btn = self._toolbar_button("bold", "Bold", self._toggle_bold)
        self.italic_btn = self._toolbar_button("italic", "Italic", self._toggle_italic)
        self.underline_btn = self._toolbar_button(
            "underline", "Underline", self._toggle_underline)
        self.bullet_btn = self._toolbar_button(
            "bullet_list", "Bullet list", self._toggle_bullet_list)
        self.ordered_btn = self._toolbar_button(
            "ordered_list", "Numbered list", self._toggle_ordered_list)
        self.bigger_btn = self._toolbar_button(
            "add", "Increase text size", lambda: self._nudge_font_size(1))
        self.smaller_btn = self._toolbar_button(
            "minus", "Decrease text size", lambda: self._nudge_font_size(-1))

        for btn in (self.bold_btn, self.italic_btn, self.underline_btn):
            btn.setCheckable(True)
        for btn in (self.bold_btn, self.italic_btn, self.underline_btn,
                   self.bullet_btn, self.ordered_btn, self.bigger_btn,
                   self.smaller_btn):
            toolbar.addWidget(btn)
        toolbar.addStretch()
        layout.addLayout(toolbar)

        # --- The document itself ---
        self.text_edit = QTextEdit()
        self.text_edit.setAcceptRichText(True)
        self.text_edit.setPlaceholderText(
            "Start writing your plan here...")
        self.text_edit.setStyleSheet(
            f"QTextEdit {{ background-color: {SURFACE}; "
            f"border: 1px solid {BORDER}; border-radius: 10px; "
            f"padding: 16px; font-size: 14px; }}")
        self.text_edit.setMinimumHeight(280)
        self.text_edit.textChanged.connect(self._on_text_changed)
        self.text_edit.cursorPositionChanged.connect(
            self._sync_toolbar_to_cursor)
        layout.addWidget(self.text_edit, stretch=3)

        # --- Checklist section ---
        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setStyleSheet(f"color: {BORDER};")
        layout.addWidget(divider)

        checklist_heading = QLabel("Plan Checklist")
        checklist_heading.setStyleSheet(
            f"font-weight: 700; font-size: 14px; color: {INK};")
        layout.addWidget(checklist_heading)

        add_row = QHBoxLayout()
        self.new_item_edit = QLineEdit()
        self.new_item_edit.setPlaceholderText(
            "Add a checklist item and press Enter")
        self.new_item_edit.returnPressed.connect(self._add_checklist_item)
        add_btn = QPushButton("Add")
        add_btn.setIcon(icon("add", color=MUTED))
        add_btn.clicked.connect(self._add_checklist_item)
        add_row.addWidget(self.new_item_edit)
        add_row.addWidget(add_btn)
        layout.addLayout(add_row)

        self.checklist = QListWidget()
        self.checklist.setMaximumHeight(160)
        self.checklist.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu)
        self.checklist.customContextMenuRequested.connect(
            self._show_checklist_menu)
        self.checklist.itemChanged.connect(self._on_item_toggled)
        layout.addWidget(self.checklist, stretch=1)

        self._load_from_project()

    # --- Toolbar helpers ---------------------------------------------

    def _toolbar_button(self, icon_key: str, tooltip: str, handler) -> QPushButton:
        btn = QPushButton()
        btn.setIcon(icon(icon_key, color=MUTED))
        btn.setToolTip(tooltip)
        btn.setFixedWidth(36)
        btn.clicked.connect(handler)
        return btn

    def _toggle_bold(self):
        weight = (QFont.Weight.Bold if self.bold_btn.isChecked()
                 else QFont.Weight.Normal)
        fmt = self.text_edit.currentCharFormat()
        fmt.setFontWeight(weight)
        self.text_edit.setCurrentCharFormat(fmt)
        self.text_edit.setFocus()

    def _toggle_italic(self):
        self.text_edit.setFontItalic(self.italic_btn.isChecked())
        self.text_edit.setFocus()

    def _toggle_underline(self):
        self.text_edit.setFontUnderline(self.underline_btn.isChecked())
        self.text_edit.setFocus()

    def _toggle_bullet_list(self):
        cursor = self.text_edit.textCursor()
        cursor.createList(QTextListFormat.Style.ListDisc)
        self.text_edit.setFocus()

    def _toggle_ordered_list(self):
        cursor = self.text_edit.textCursor()
        cursor.createList(QTextListFormat.Style.ListDecimal)
        self.text_edit.setFocus()

    def _nudge_font_size(self, delta: int):
        cursor = self.text_edit.textCursor()
        fmt = cursor.charFormat() if cursor.hasSelection() else self.text_edit.currentCharFormat()
        size = fmt.fontPointSize() or self.text_edit.font().pointSizeF() or 11.0
        fmt.setFontPointSize(max(8.0, size + delta))
        if cursor.hasSelection():
            cursor.mergeCharFormat(fmt)
        else:
            self.text_edit.setCurrentCharFormat(fmt)
        self.text_edit.setFocus()

    def _sync_toolbar_to_cursor(self):
        """Keeps the Bold/Italic/Underline buttons reflecting whatever is
        directly under the caret, the way Word's ribbon does."""
        fmt = self.text_edit.currentCharFormat()
        self.bold_btn.blockSignals(True)
        self.italic_btn.blockSignals(True)
        self.underline_btn.blockSignals(True)
        self.bold_btn.setChecked(fmt.fontWeight() >= QFont.Weight.Bold)
        self.italic_btn.setChecked(fmt.fontItalic())
        self.underline_btn.setChecked(fmt.fontUnderline())
        self.bold_btn.blockSignals(False)
        self.italic_btn.blockSignals(False)
        self.underline_btn.blockSignals(False)

    # --- Autosave -------------------------------------------------------

    def _on_text_changed(self):
        self._autosave_timer.start()

    def _save_content(self):
        self.active_project.plan_content = self.text_edit.toHtml()
        self.file_manager.save_project(self.active_project)

    # --- Checklist --------------------------------------------------

    def _add_checklist_item(self):
        text = self.new_item_edit.text().strip()
        if not text:
            return
        todo = ToDo(text)
        self.active_project.plan_checklist.append(todo)
        self._append_checklist_row(todo)
        self.new_item_edit.clear()
        self.file_manager.save_project(self.active_project)

    def _append_checklist_row(self, todo: ToDo):
        item = QListWidgetItem(todo.description)
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        item.setCheckState(Qt.CheckState.Checked if todo.is_completed
                           else Qt.CheckState.Unchecked)
        item.setData(Qt.ItemDataRole.UserRole, todo)
        self._apply_strikethrough(item, todo.is_completed)
        self.checklist.addItem(item)

    def _apply_strikethrough(self, item: QListWidgetItem, completed: bool):
        font = item.font()
        font.setStrikeOut(completed)
        item.setFont(font)
        item.setForeground(Qt.GlobalColor.gray if completed else Qt.GlobalColor.black)

    def _on_item_toggled(self, item: QListWidgetItem):
        todo = item.data(Qt.ItemDataRole.UserRole)
        if todo is None:
            return
        todo.is_completed = item.checkState() == Qt.CheckState.Checked
        self._apply_strikethrough(item, todo.is_completed)
        self.file_manager.save_project(self.active_project)

    def _show_checklist_menu(self, pos):
        item = self.checklist.itemAt(pos)
        if item is None:
            return
        menu = QMenu(self)
        delete_action = menu.addAction(icon("delete", color=MUTED),
                                       "Delete Item")
        action = menu.exec(self.checklist.mapToGlobal(pos))
        if action == delete_action:
            todo = item.data(Qt.ItemDataRole.UserRole)
            if todo in self.active_project.plan_checklist:
                self.active_project.plan_checklist.remove(todo)
            self.checklist.takeItem(self.checklist.row(item))
            self.file_manager.save_project(self.active_project)

    # --- Loading / refreshing ----------------------------------------

    def _load_from_project(self):
        self.text_edit.blockSignals(True)
        self.text_edit.setHtml(self.active_project.plan_content)
        self.text_edit.blockSignals(False)

        self.checklist.blockSignals(True)
        self.checklist.clear()
        for todo in self.active_project.plan_checklist:
            self._append_checklist_row(todo)
        self.checklist.blockSignals(False)

    def refresh(self, active_project):
        """
        Re-targets the view at a (possibly updated) project.

        Skips reloading the text/checklist while the user is actively
        typing in this tab, so a save elsewhere in the app (which reloads
        every project from disk) never clobbers an in-progress, not-yet-
        autosaved edit.
        """
        self.active_project = active_project
        if self.text_edit.hasFocus() or self.new_item_edit.hasFocus():
            return
        self._load_from_project()
