"""
Modal input forms for creating a Project, creating/editing a Task (with an
embedded to-do adder), and adding a single To-do item.

Kept separate from views.py so the day-to-day tab widgets stay focused on
layout and display, while the forms their toolbar buttons pop up live here
and can be reused across tabs (EditView, BoardView, ...).
"""
import datetime

from PyQt6.QtWidgets import (QDialog, QFormLayout, QVBoxLayout, QHBoxLayout,
                             QLineEdit, QTextEdit, QComboBox, QDateEdit,
                             QSpinBox, QCheckBox, QListWidget,
                             QListWidgetItem, QPushButton,
                             QDialogButtonBox, QAbstractItemView)
from PyQt6.QtCore import Qt, QDate

from data import Project, Task, ToDo


class ProjectDialog(QDialog):
    """Collects title/subject/description for a brand-new Project."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("New Project")
        self.setMinimumWidth(360)

        self.title_edit = QLineEdit()
        self.subject_edit = QLineEdit()
        self.description_edit = QTextEdit()
        self.description_edit.setFixedHeight(80)

        form = QFormLayout()
        form.addRow("Title:", self.title_edit)
        form.addRow("Subject:", self.subject_edit)
        form.addRow("Description:", self.description_edit)

        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                        QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self.try_accept)
        self.buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.buttons)

    def try_accept(self):
        """Blocks the dialog from closing until a title has been entered."""
        if not self.title_edit.text().strip():
            self.title_edit.setStyleSheet("border: 1px solid #DE350B;")
            return
        self.accept()

    def get_project(self) -> Project:
        """Builds and returns the new Project. Call only once accepted."""
        return Project(self.title_edit.text().strip(),
                       self.subject_edit.text().strip(),
                       self.description_edit.toPlainText().strip())


class TaskDialog(QDialog):
    """
    Create or edit a Task, including adding new to-do items to it.

    Pass an existing `task` to edit it in place - title, description,
    status, priority, dates, duration, and dependencies are all mutated
    onto that same object when the dialog is accepted, so callers should
    hold their own reference to it rather than relying on a return value.
    Pass task=None to create a fresh Task instead, retrieved via
    get_task() after the dialog is accepted.

    `sibling_tasks` is the full task list of the owning project, used to
    populate the dependency checklist (the task being edited, if any, is
    excluded from its own dependency list).
    """

    STATUSES = ["Not Started", "In Progress", "On Hold", "Completed"]
    PRIORITIES = ["Low", "Medium", "High"]

    def __init__(self, sibling_tasks, task=None, parent=None):
        super().__init__(parent)
        self.task = task
        self._pending_todos = []
        self.setWindowTitle("Edit Task" if task else "New Task")
        self.setMinimumWidth(440)

        self.title_edit = QLineEdit(task.title if task else "")
        self.description_edit = QTextEdit(task.description if task else "")
        self.description_edit.setFixedHeight(70)

        self.status_combo = QComboBox()
        self.status_combo.addItems(self.STATUSES)
        if task:
            self.status_combo.setCurrentText(task.status)

        self.priority_combo = QComboBox()
        self.priority_combo.addItems(self.PRIORITIES)
        self.priority_combo.setCurrentText(task.priority if task else "Medium")

        self.duration_spin = QSpinBox()
        self.duration_spin.setRange(0, 365)
        self.duration_spin.setValue(task.duration_days if task else 1)
        self.duration_spin.setToolTip(
            "Effort in days, used by the Critical Path engine. "
            "0 marks this task as a milestone.")

        self.start_check = QCheckBox("Set start date")
        self.start_edit = QDateEdit(calendarPopup=True)
        self.start_edit.setDisplayFormat("yyyy-MM-dd")
        if task and task.date_started:
            self.start_check.setChecked(True)
            d = task.date_started
            self.start_edit.setDate(QDate(d.year, d.month, d.day))
        else:
            self.start_edit.setDate(QDate.currentDate())
            self.start_edit.setEnabled(False)
        self.start_check.toggled.connect(self.start_edit.setEnabled)

        self.deadline_check = QCheckBox("Set deadline")
        self.deadline_edit = QDateEdit(calendarPopup=True)
        self.deadline_edit.setDisplayFormat("yyyy-MM-dd")
        if task and task.date_to_be_completed:
            self.deadline_check.setChecked(True)
            d = task.date_to_be_completed
            self.deadline_edit.setDate(QDate(d.year, d.month, d.day))
        else:
            self.deadline_edit.setDate(QDate.currentDate())
            self.deadline_edit.setEnabled(False)
        self.deadline_check.toggled.connect(self.deadline_edit.setEnabled)

        # --- Dependencies ---
        self.dependency_list = QListWidget()
        self.dependency_list.setSelectionMode(
            QAbstractItemView.SelectionMode.NoSelection)
        current_deps = set(task.dependencies) if task else set()
        for sibling in sibling_tasks:
            if task and sibling.title == task.title:
                continue
            if sibling.is_deleted:
                continue
            item = QListWidgetItem(sibling.title)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked
                               if sibling.title in current_deps else
                               Qt.CheckState.Unchecked)
            self.dependency_list.addItem(item)
        self.dependency_list.setMaximumHeight(90)

        # --- Embedded to-do checklist ---
        self.existing_todos_list = QListWidget()
        self.existing_todos_list.setMaximumHeight(80)
        existing = [t for t in task.todo_list if not t.is_deleted] if task else []
        if existing:
            for todo in existing:
                mark = "\u2713 " if todo.is_completed else "\u25a1 "
                self.existing_todos_list.addItem(mark + todo.description)
        else:
            self.existing_todos_list.addItem("(no to-dos yet)")
            self.existing_todos_list.setEnabled(False)

        todo_input_row = QHBoxLayout()
        self.new_todo_edit = QLineEdit()
        self.new_todo_edit.setPlaceholderText("Add a to-do item and press Enter")
        self.new_todo_edit.returnPressed.connect(self._queue_todo)
        add_todo_btn = QPushButton("Add")
        add_todo_btn.clicked.connect(self._queue_todo)
        todo_input_row.addWidget(self.new_todo_edit)
        todo_input_row.addWidget(add_todo_btn)

        form = QFormLayout()
        form.addRow("Title:", self.title_edit)
        form.addRow("Description:", self.description_edit)
        form.addRow("Status:", self.status_combo)
        form.addRow("Priority:", self.priority_combo)
        form.addRow("Duration (days):", self.duration_spin)
        form.addRow(self.start_check, self.start_edit)
        form.addRow(self.deadline_check, self.deadline_edit)
        form.addRow("Depends on:", self.dependency_list)
        form.addRow("To-dos:", self.existing_todos_list)
        form.addRow("", todo_input_row)

        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                        QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self.try_accept)
        self.buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.buttons)

    def _queue_todo(self):
        """Stages a new ToDo, applied to the task once the dialog is accepted."""
        text = self.new_todo_edit.text().strip()
        if not text:
            return
        self._pending_todos.append(ToDo(text))
        if not self.existing_todos_list.isEnabled():
            self.existing_todos_list.clear()
            self.existing_todos_list.setEnabled(True)
        self.existing_todos_list.addItem("\u25a1 " + text)
        self.new_todo_edit.clear()

    def try_accept(self):
        """Blocks the dialog from closing until a title has been entered."""
        if not self.title_edit.text().strip():
            self.title_edit.setStyleSheet("border: 1px solid #DE350B;")
            return
        self.accept()

    def _selected_dependencies(self):
        deps = []
        for i in range(self.dependency_list.count()):
            item = self.dependency_list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                deps.append(item.text())
        return deps

    def get_task(self) -> Task:
        """
        Applies the form onto self.task (editing) or builds a new Task
        (creating), including any to-do items queued via the embedded
        checklist. Call only once the dialog has been accepted.
        """
        title = self.title_edit.text().strip()
        description = self.description_edit.toPlainText().strip()
        priority = self.priority_combo.currentText()
        duration = self.duration_spin.value()

        target = self.task if self.task else Task(title, description,
                                                   priority=priority,
                                                   duration_days=duration)
        target.title = title
        target.description = description
        target.priority = priority
        target.duration_days = duration
        target.status = self.status_combo.currentText()
        target.is_completed = target.status == "Completed"

        if self.start_check.isChecked():
            qd = self.start_edit.date()
            target.date_started = datetime.date(qd.year(), qd.month(), qd.day())
        else:
            target.date_started = None

        if self.deadline_check.isChecked():
            qd = self.deadline_edit.date()
            target.date_to_be_completed = datetime.date(
                qd.year(), qd.month(), qd.day())
        else:
            target.date_to_be_completed = None

        target.dependencies = self._selected_dependencies()

        for todo in self._pending_todos:
            target.add_todo(todo)

        return target


class TodoDialog(QDialog):
    """A single-field dialog for adding one To-do item's description."""

    def __init__(self, title="New To-do", parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(320)

        self.description_edit = QLineEdit()
        self.description_edit.setPlaceholderText("What needs to be done?")

        form = QFormLayout()
        form.addRow("Description:", self.description_edit)

        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                        QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self.try_accept)
        self.buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.buttons)

    def try_accept(self):
        """Blocks the dialog from closing until a description has been entered."""
        if not self.description_edit.text().strip():
            self.description_edit.setStyleSheet("border: 1px solid #DE350B;")
            return
        self.accept()

    def get_todo(self) -> ToDo:
        """Builds and returns the new ToDo. Call only once accepted."""
        return ToDo(self.description_edit.text().strip())
