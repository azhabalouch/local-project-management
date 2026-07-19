"""
Day-to-day task-editing widgets: the weekly/monthly List View, the
drag-and-drop Kanban Board View, and the multi-select Edit View.
"""
import copy
from typing import List, Callable, Optional

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                             QListWidget, QListWidgetItem, QAbstractItemView,
                             QComboBox, QTreeWidget, QTreeWidgetItem,
                             QPushButton, QMessageBox, QDialog)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor

from data import FileManager, Project
from dialogs import ProjectDialog, TaskDialog, TodoDialog
from styles import NAVY, SLATE, BLUE, GREEN, RED, BORDER, SURFACE, BACKGROUND, BACKGROUND_ALT, button_style


class ListView(QWidget):
    """
    Displays tasks categorized on a weekly or monthly basis.
    
    Provides a high-level chronological overview of project deliverables, 
    allowing the user to switch between timeframes dynamically.
    
    Attributes:
        active_project (Project): The currently loaded project data.
    """

    def __init__(self, active_project):
        super().__init__()
        self.active_project = active_project
        self.layout = QVBoxLayout(self)

        # --- Controls UI ---
        controls_layout = QHBoxLayout()
        self.view_selector = QComboBox()
        self.view_selector.addItems(["Weekly View", "Monthly View"])
        self.view_selector.setStyleSheet("min-width: 160px;")

        # Connect the dropdown change to our refresh logic
        self.view_selector.currentTextChanged.connect(self.refresh_view)

        timeframe_label = QLabel("Select Timeframe:")
        timeframe_label.setStyleSheet(f"font-weight: 600; color: {SLATE};")
        controls_layout.addWidget(timeframe_label)
        controls_layout.addWidget(self.view_selector)
        controls_layout.addStretch()  # Pushes controls to the left

        # --- Tree Widget Data Display ---
        self.tree_widget = QTreeWidget()
        self.tree_widget.setHeaderLabels(
            ["Timeframe / Task Title", "Status", "Priority", "Deadline"])
        self.tree_widget.setAlternatingRowColors(True)

        self.layout.addLayout(controls_layout)
        self.layout.addWidget(self.tree_widget)

        # Initial Population
        self.refresh_view(self.view_selector.currentText())

    def refresh_view(self, view_type: str):
        """
        Clears the current tree and repopulates it based on the selected timeframe.
        """
        self.tree_widget.clear()

        if view_type == "Weekly View":
            self._populate_weekly()
        else:
            self._populate_monthly()

        self.tree_widget.expandAll()

    def _active_tasks(self):
        """Returns the project's tasks, excluding any soft-deleted from Edit View."""
        return [t for t in self.active_project.tasks if not t.is_deleted]

    def _populate_weekly(self):
        """
        Groups tasks by the ISO calendar week of their completion date.
        Tasks without a scheduled deadline are grouped under an 'Unscheduled' node.
        """
        weeks = {}
        unscheduled = []

        for task in self._active_tasks():
            if task.date_to_be_completed:
                # Extract the ISO week number and year
                year, week, _ = task.date_to_be_completed.isocalendar()
                week_label = f"Week {week}, {year}"

                if week_label not in weeks:
                    weeks[week_label] = []
                weeks[week_label].append(task)
            else:
                unscheduled.append(task)

        self._build_tree_nodes(weeks, unscheduled)

    def _populate_monthly(self):
        """
        Groups tasks by the month and year of their completion date.
        """
        months = {}
        unscheduled = []

        for task in self._active_tasks():
            if task.date_to_be_completed:
                # Format string to "Month Year" (e.g., "July 2026")
                month_label = task.date_to_be_completed.strftime("%B %Y")

                if month_label not in months:
                    months[month_label] = []
                months[month_label].append(task)
            else:
                unscheduled.append(task)

        self._build_tree_nodes(months, unscheduled)

    def _build_tree_nodes(self, grouped_data: dict, unscheduled_tasks: list):
        """
        Helper method to generate the QTreeWidgetItems for the grouped data.
        """
        for group_label, tasks in grouped_data.items():
            # Parent Node
            group_item = QTreeWidgetItem(self.tree_widget,
                                         [group_label, "", "", ""])
            group_item.setBackground(0, QColor(BACKGROUND_ALT))
            font = group_item.font(0)
            font.setBold(True)
            group_item.setFont(0, font)

            # Child Nodes (Tasks)
            for task in tasks:
                deadline_str = task.date_to_be_completed.isoformat()
                QTreeWidgetItem(
                    group_item,
                    [task.title, task.status, task.priority, deadline_str])

        if unscheduled_tasks:
            un_item = QTreeWidgetItem(self.tree_widget,
                                      ["Unscheduled", "", "", ""])
            un_item.setBackground(0, QColor(BACKGROUND_ALT))
            font = un_item.font(0)
            font.setBold(True)
            un_item.setFont(0, font)
            for task in unscheduled_tasks:
                QTreeWidgetItem(
                    un_item,
                    [task.title, task.status, task.priority, "No Deadline"])


class KanbanColumn(QListWidget):
    """
    A custom QListWidget representing a single column in the Kanban board.
    
    Equipped with PyQt Signals to communicate with the main view when 
    a task card is successfully dropped, ensuring backend synchronization.
    """
    # Define a custom PyQt signal: emits the task's title and the column's new status
    task_dropped_signal = pyqtSignal(str, str)
    # Emits the Task object behind a card that was double-clicked, so the
    # BoardView can open it for editing.
    task_edit_requested = pyqtSignal(object)

    def __init__(self, title: str):
        super().__init__()
        self.title = title

        # Enable drag-and-drop physics natively. DragDrop (rather than
        # InternalMove) is required for a card to be droppable onto a
        # *different* KanbanColumn instance - InternalMove only supports
        # reordering within the same widget, which is why cards previously
        # couldn't be dragged between columns.
        self.setAcceptDrops(True)
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
        # NOTE: the drop is always resolved as a CopyAction (see dropEvent),
        # even though this reads like a "move" board. If this were
        # MoveAction, Qt's own QAbstractItemView.startDrag() would remove
        # the dragged row from the source column a *second* time after our
        # manual dropEvent handling already moved it - corrupting whichever
        # column lost the extra row and making the status update
        # unreliable. Handling the removal entirely ourselves and reporting
        # CopyAction back to Qt avoids that double-removal.
        self.setDefaultDropAction(Qt.DropAction.CopyAction)

        self.itemDoubleClicked.connect(
            lambda item: self.task_edit_requested.emit(
                item.data(Qt.ItemDataRole.UserRole)))

        # Enterprise card styling
        self.setStyleSheet(f"""
            QListWidget {{
                background-color: {BACKGROUND};
                border: 1px solid {BORDER};
                border-radius: 8px;
                padding: 10px;
            }}
            QListWidget::item {{
                background-color: {SURFACE};
                border: 1px solid {BORDER};
                border-left: 3px solid {BLUE};
                border-radius: 4px;
                padding: 14px 12px;
                margin-bottom: 8px;
                color: {NAVY};
                font-weight: 500;
            }}
            QListWidget::item:hover {{
                background-color: {BACKGROUND_ALT};
                border-left: 3px solid {BLUE};
            }}
            QListWidget::item:selected {{
                background-color: {SURFACE};
                color: {NAVY};
                border: 1px solid {BLUE};
                border-left: 3px solid {BLUE};
            }}
        """)

    def dropEvent(self, event):
        """
        Moves the dragged card into this column, whether it came from this
        same column (reordering) or a different one, then broadcasts the
        change so the BoardView can persist the new status.

        Handled fully manually rather than delegating to Qt's built-in
        move logic: QListWidget's native InternalMove drop only transfers
        items within a single widget, and letting two independent
        QListWidgets both react to the same drop tends to duplicate the
        item instead of moving it.
        """
        source_widget = event.source()
        if not isinstance(source_widget, KanbanColumn):
            event.ignore()
            return

        dragged_item = source_widget.currentItem()
        if not dragged_item:
            event.ignore()
            return

        task = dragged_item.data(Qt.ItemDataRole.UserRole)
        task_title = dragged_item.text()
        came_from_other_column = source_widget is not self

        source_widget.takeItem(source_widget.row(dragged_item))
        new_item = QListWidgetItem(task_title)
        new_item.setData(Qt.ItemDataRole.UserRole, task)
        self.addItem(new_item)
        event.setDropAction(Qt.DropAction.CopyAction)
        event.accept()

        if came_from_other_column:
            self.task_dropped_signal.emit(task_title, self.title)


class BoardView(QWidget):
    """
    The main Kanban Board View container. 
    
    It manages the columns and acts as the controller between the GUI 
    and the FileManager to ensure the user's data persists locally.
    """

    def __init__(self, active_project, file_manager, on_change: Optional[Callable[[], None]] = None):
        super().__init__()
        self.active_project = active_project
        self.file_manager = file_manager
        # Invoked after a task is added or edited from this tab, so the
        # main window can reload every other tab (Gantt, Milestone, List,
        # Critical Path) with the change. Left as a plain local refresh if
        # no callback was supplied.
        self.on_change = on_change

        outer_layout = QVBoxLayout(self)

        toolbar = QHBoxLayout()
        self.add_task_btn = QPushButton("+ Add Task")
        self.add_task_btn.setStyleSheet(button_style(BLUE) + "max-width: 140px;")
        self.add_task_btn.clicked.connect(self.add_task)
        toolbar.addWidget(self.add_task_btn)
        toolbar.addStretch()
        hint_label = QLabel("Drag cards between columns, or double-click one to edit it.")
        hint_label.setStyleSheet(f"color: {SLATE};")
        toolbar.addWidget(hint_label)
        outer_layout.addLayout(toolbar)

        self.layout = QHBoxLayout()
        outer_layout.addLayout(self.layout)

        # Initialize the standard states mapped to our custom widgets
        self.columns = {
            "Not Started": KanbanColumn("Not Started"),
            "In Progress": KanbanColumn("In Progress"),
            "On Hold": KanbanColumn("On Hold"),
            "Completed": KanbanColumn("Completed")
        }

        for title, column_widget in self.columns.items():
            # Connect the column's custom signals to our backend save logic
            column_widget.task_dropped_signal.connect(
                self.sync_task_to_backend)
            column_widget.task_edit_requested.connect(self.edit_task)

            col_layout = QVBoxLayout()
            header = QLabel(title.upper())
            header.setStyleSheet(
                f"font-weight: 700; font-size: 12px; color: {SLATE}; "
                f"letter-spacing: 1px; padding: 4px 2px 8px 2px; "
                f"border-bottom: 2px solid {BLUE};")

            col_layout.addWidget(header)
            col_layout.addWidget(column_widget)
            self.layout.addLayout(col_layout)

        # Load real data instead of dummy data
        self.populate_board_from_project()

    def populate_board_from_project(self):
        """
        Reads the active Project object and populates the board 
        columns based on current task statuses. Soft-deleted tasks
        (from the Edit View) are excluded.
        """
        for column in self.columns.values():
            column.clear()

        for task in self.active_project.tasks:
            if task.is_deleted:
                continue
            # Fallback to "Not Started" if a status is missing or corrupted
            target_col = self.columns.get(task.status,
                                          self.columns["Not Started"])
            item = QListWidgetItem(task.title)
            item.setData(Qt.ItemDataRole.UserRole, task)
            target_col.addItem(item)

    def sync_task_to_backend(self, task_title: str, new_status: str):
        """
        Slot method triggered by the KanbanColumn drop event.
        Updates the Python object and overwrites the local JSON file.
        """
        # 1. Find the specific task in the current project model
        for task in self.active_project.tasks:
            if task.title == task_title:
                task.status = new_status
                break

        # 2. Save the updated project state to Documents/ProjectManagement/
        self.file_manager.save_project(self.active_project)

        # 3. Refresh every other tab (Gantt, Milestone, List, Critical Path)
        # so the status change is reflected app-wide, not just on this
        # board - mirroring what add_task() and edit_task() already do.
        if self.on_change:
            self.on_change()
        else:
            self.populate_board_from_project()

    def add_task(self):
        """Opens the New Task dialog and appends the result to the active project."""
        dialog = TaskDialog(self.active_project.tasks, task=None, parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        new_task = dialog.get_task()
        self.active_project.add_task(new_task)
        self.file_manager.save_project(self.active_project)

        if self.on_change:
            self.on_change()
        else:
            self.populate_board_from_project()

    def edit_task(self, task):
        """
        Opens the Edit Task dialog for a double-clicked card. Triggered by
        KanbanColumn.task_edit_requested.
        """
        if task is None:
            return

        old_title = task.title
        dialog = TaskDialog(self.active_project.tasks, task=task, parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        dialog.get_task()  # mutates `task` in place
        self.active_project.rename_task_references(old_title, task.title)
        self.file_manager.save_project(self.active_project)

        if self.on_change:
            self.on_change()
        else:
            self.populate_board_from_project()


class EditView(QWidget):
    """
    Multi-select maintenance view spanning every loaded project.

    Displays a Project -> Task -> ToDo hierarchy with extended selection,
    so the user can select several items at once (of any mixed type) and
    soft-delete them, or select one or more Tasks and copy them into a
    different project.

    Attributes:
        all_projects (List[Project]): Every project currently loaded by the
            application (not just the one active in the other tabs).
        file_manager (FileManager): Used to persist changes back to disk.
        on_change (Callable): Invoked after a delete or copy operation so
            the main window can reload the project switcher and other tabs.
    """

    def __init__(self, all_projects: List[Project], file_manager: FileManager,
                on_change: Callable[[], None]):
        super().__init__()
        self.all_projects = all_projects
        self.file_manager = file_manager
        self.on_change = on_change

        self.layout = QVBoxLayout(self)
        self.layout.addWidget(
            QLabel(
                "Select any combination of Projects, Tasks, and To-dos below."
            ))

        self.tree_widget = QTreeWidget()
        self.tree_widget.setHeaderLabels(["Name", "Type", "Detail"])
        self.tree_widget.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection)
        self.tree_widget.setAlternatingRowColors(True)
        self.layout.addWidget(self.tree_widget)

        # Double-clicking a Task row opens it for editing.
        self.tree_widget.itemDoubleClicked.connect(self.edit_task)

        # --- Creation Bar ---
        creation_layout = QHBoxLayout()

        self.new_project_btn = QPushButton("New Project")
        self.new_project_btn.setStyleSheet(button_style(GREEN))
        self.new_project_btn.clicked.connect(self.create_project)

        self.add_task_btn = QPushButton("Add Task")
        self.add_task_btn.setStyleSheet(button_style(BLUE))
        self.add_task_btn.clicked.connect(self.add_task)

        self.add_todo_btn = QPushButton("Add To-do")
        self.add_todo_btn.setStyleSheet(button_style(BLUE))
        self.add_todo_btn.clicked.connect(self.add_todo)

        creation_layout.addWidget(self.new_project_btn)
        creation_layout.addWidget(self.add_task_btn)
        creation_layout.addWidget(self.add_todo_btn)
        creation_layout.addStretch()
        tip_label = QLabel("Tip: select a Project or Task above, then Add Task / "
                           "Add To-do. Double-click a Task to edit it.")
        tip_label.setStyleSheet(f"color: {SLATE};")
        creation_layout.addWidget(tip_label)

        self.layout.addLayout(creation_layout)

        # --- Action Bar ---
        action_layout = QHBoxLayout()

        self.delete_btn = QPushButton("Delete Selected")
        self.delete_btn.setStyleSheet(button_style(RED))
        self.delete_btn.clicked.connect(self.delete_selected)

        self.dest_combo = QComboBox()
        self.dest_combo.setStyleSheet("min-width: 180px;")

        self.copy_btn = QPushButton("Copy Selected Task(s) to Project")
        self.copy_btn.setStyleSheet(button_style(BLUE))
        self.copy_btn.clicked.connect(self.copy_selected_tasks)

        dest_label = QLabel("Destination Project:")
        dest_label.setStyleSheet(f"font-weight: 600; color: {SLATE};")
        action_layout.addWidget(self.delete_btn)
        action_layout.addStretch()
        action_layout.addWidget(dest_label)
        action_layout.addWidget(self.dest_combo)
        action_layout.addWidget(self.copy_btn)

        self.layout.addLayout(action_layout)

        self.populate_tree()

    def populate_tree(self):
        """Rebuilds the tree and the destination combo from all_projects."""
        self.tree_widget.clear()
        self.dest_combo.clear()

        for project in self.all_projects:
            if project.is_deleted:
                continue

            self.dest_combo.addItem(project.title, userData=project)

            project_item = QTreeWidgetItem(
                self.tree_widget, [project.title, "Project", project.subject])
            project_item.setData(0, Qt.ItemDataRole.UserRole,
                                 ("project", project, None, None))

            for task in project.tasks:
                if task.is_deleted:
                    continue

                task_item = QTreeWidgetItem(
                    project_item, [task.title, "Task", task.status])
                task_item.setData(0, Qt.ItemDataRole.UserRole,
                                  ("task", project, task, None))

                for todo in task.todo_list:
                    if todo.is_deleted:
                        continue

                    completed_label = "Done" if todo.is_completed else "Pending"
                    todo_item = QTreeWidgetItem(
                        task_item,
                        [todo.description, "To-do", completed_label])
                    todo_item.setData(0, Qt.ItemDataRole.UserRole,
                                      ("todo", project, task, todo))

            # A standalone checklist for this project, separate from any
            # single task's own to-do list. Select this node (or the
            # project itself) and use "Add To-do" to add to it.
            general_group_item = QTreeWidgetItem(
                project_item, ["General To-Dos", "Folder", ""])
            general_group_item.setData(0, Qt.ItemDataRole.UserRole,
                                       ("general_group", project, None, None))
            for todo in project.general_todos:
                if todo.is_deleted:
                    continue

                completed_label = "Done" if todo.is_completed else "Pending"
                todo_item = QTreeWidgetItem(
                    general_group_item,
                    [todo.description, "To-do", completed_label])
                todo_item.setData(0, Qt.ItemDataRole.UserRole,
                                  ("todo", project, None, todo))

        self.tree_widget.expandAll()

    def delete_selected(self):
        """
        Soft-deletes every selected Project, Task, and To-do item
        (setting is_deleted = True) and persists the affected projects.
        """
        selected = self.tree_widget.selectedItems()
        if not selected:
            QMessageBox.information(self, "Nothing Selected",
                                    "Select one or more items to delete.")
            return

        affected_projects = set()

        for item in selected:
            kind, project, task, todo = item.data(0,
                                                   Qt.ItemDataRole.UserRole)
            if kind == "project":
                project.is_deleted = True
            elif kind == "task":
                task.is_deleted = True
            elif kind == "todo":
                todo.is_deleted = True
            else:
                # The "General To-Dos" folder node is just a grouping
                # header, not a deletable object.
                continue
            affected_projects.add(project)

        for project in affected_projects:
            self.file_manager.save_project(project)

        self.populate_tree()
        self.on_change()

    def copy_selected_tasks(self):
        """
        Duplicates every selected Task into the chosen destination project.
        Non-task selections (Projects, To-dos) are ignored for this action,
        since only Tasks were specified as copyable in the brief.
        """
        selected_tasks = [
            item.data(0, Qt.ItemDataRole.UserRole)[2]
            for item in self.tree_widget.selectedItems()
            if item.data(0, Qt.ItemDataRole.UserRole)[0] == "task"
        ]

        if not selected_tasks:
            QMessageBox.information(
                self, "No Tasks Selected",
                "Select one or more Tasks to copy (Projects and To-dos are not copied)."
            )
            return

        destination = self.dest_combo.currentData()
        if destination is None:
            QMessageBox.warning(self, "No Destination",
                                "There is no destination project available.")
            return

        for task in selected_tasks:
            destination.tasks.append(copy.deepcopy(task))

        self.file_manager.save_project(destination)

        QMessageBox.information(
            self, "Copied",
            f"{len(selected_tasks)} task(s) copied to '{destination.title}'.")

        self.populate_tree()
        self.on_change()

    def _current_context(self):
        """
        Returns the (kind, project, task, todo) tuple stored on the
        currently focused tree row, or None if nothing is selected.
        """
        item = self.tree_widget.currentItem()
        if item is None:
            return None
        return item.data(0, Qt.ItemDataRole.UserRole)

    def create_project(self):
        """Opens the New Project dialog and saves the result to disk."""
        dialog = ProjectDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        new_project = dialog.get_project()
        self.file_manager.save_project(new_project)
        self.populate_tree()
        self.on_change()

    def add_task(self):
        """
        Adds a new Task to the currently selected Project (or the Project
        that owns the currently selected Task/To-do).
        """
        context = self._current_context()
        if not context:
            QMessageBox.information(
                self, "Select a Project",
                "Select a project (or one of its tasks) first, so the new "
                "task has somewhere to go.")
            return

        _, project, _, _ = context

        dialog = TaskDialog(project.tasks, task=None, parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        new_task = dialog.get_task()
        project.add_task(new_task)
        self.file_manager.save_project(project)
        self.populate_tree()
        self.on_change()

    def edit_task(self, item, column=0):
        """
        Opens the Edit Task dialog for a double-clicked Task row. Does
        nothing for Project, To-do, or folder rows.
        """
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data or data[0] != "task":
            return

        _, project, task, _ = data
        old_title = task.title

        dialog = TaskDialog(project.tasks, task=task, parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        dialog.get_task()  # mutates `task` in place
        project.rename_task_references(old_title, task.title)
        self.file_manager.save_project(project)
        self.populate_tree()
        self.on_change()

    def add_todo(self):
        """
        Adds a To-do item to whatever is currently selected: to the Task
        itself if a Task row is selected, or to the Project's standalone
        general to-do list if a Project or its "General To-Dos" folder is
        selected. Selecting an existing To-do adds another alongside it,
        in the same list it already belongs to.
        """
        context = self._current_context()
        if not context:
            QMessageBox.information(
                self, "Select a Project or Task",
                "Select a task (to add a to-do to it) or a project / its "
                "General To-Dos node (for a standalone to-do) first.")
            return

        kind, project, task, todo = context

        dialog = TodoDialog(parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        new_todo = dialog.get_todo()

        if kind == "task":
            task.add_todo(new_todo)
        elif kind in ("project", "general_group"):
            project.add_general_todo(new_todo)
        elif kind == "todo":
            if task is not None:
                task.add_todo(new_todo)
            else:
                project.add_general_todo(new_todo)
        else:
            return

        self.file_manager.save_project(project)
        self.populate_tree()
        self.on_change()
