"""
Day-to-day task-editing widgets: the weekly/monthly List View, the
drag-and-drop Kanban Board View, the multi-select Edit View, and the
Trash View for restoring soft-deleted items.
"""
import copy
from typing import List, Callable, Optional

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                             QListWidget, QListWidgetItem, QAbstractItemView,
                             QComboBox, QLineEdit, QTreeWidget,
                             QTreeWidgetItem, QPushButton, QMessageBox,
                             QDialog, QMenu)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor

from data import FileManager, Project
from dialogs import ProjectDialog, TaskDialog, TodoDialog
from styles import (INK, MUTED, ACCENT, SUCCESS, RED, BORDER, SURFACE,
                    BACKGROUND, BACKGROUND_ALT, ACCENT_SOFT, button_style,
                    ghost_button_style, hint_style, SPACE_SM, SPACE_MD)
from icons import icon, status_icon, priority_icon
from widgets import add_search_icon, hint_row

# Shared with TaskDialog's own status list (dialogs.py) so quick-edit menus
# in this file always offer the same set of statuses as the full dialog.
STATUSES = ["Not Started", "In Progress", "On Hold", "Completed"]
PRIORITIES = ["Low", "Medium", "High"]


class ListView(QWidget):
    """
    Displays tasks categorized on a weekly or monthly basis.
    
    Provides a high-level chronological overview of project deliverables, 
    allowing the user to switch between timeframes dynamically. Supports a
    text/status/priority filter, and a right-click "Change Status" menu on
    any task row for a quick status edit without opening the full Task
    dialog.
    
    Attributes:
        active_project (Project): The currently loaded project data.
        file_manager (FileManager): Used to persist a quick status change.
        on_change (Callable): Invoked after a quick status change so the
            main window can reload every other tab with it.
    """

    def __init__(self,
                 active_project,
                 file_manager: FileManager,
                 on_change: Optional[Callable[[], None]] = None):
        super().__init__()
        self.active_project = active_project
        self.file_manager = file_manager
        self.on_change = on_change
        self.layout = QVBoxLayout(self)

        # --- Controls UI ---
        controls_layout = QHBoxLayout()
        self.view_selector = QComboBox()
        self.view_selector.addItems(["Weekly View", "Monthly View"])
        self.view_selector.setStyleSheet("min-width: 160px;")
        self.view_selector.setToolTip(
            "Group tasks by week or by month, whichever is easier to "
            "plan around.")

        # Connect the dropdown change to our refresh logic
        self.view_selector.currentTextChanged.connect(self.refresh_view)

        timeframe_label = QLabel("Select Timeframe:")
        timeframe_label.setStyleSheet(f"font-weight: 600; color: {MUTED};")
        controls_layout.addWidget(timeframe_label)
        controls_layout.addWidget(self.view_selector)

        # --- Search / filter controls ---
        self.search_edit = QLineEdit()
        add_search_icon(self.search_edit)
        self.search_edit.setPlaceholderText("Search tasks...")
        self.search_edit.setStyleSheet("QLineEdit { min-width: 180px; padding-left: 8px; }")
        self.search_edit.setToolTip("Type part of a task's title to filter the list.")
        self.search_edit.textChanged.connect(
            lambda _: self.refresh_view(self.view_selector.currentText()))

        self.status_filter = QComboBox()
        self.status_filter.addItem("All Statuses")
        self.status_filter.addItems(STATUSES)
        self.status_filter.setStyleSheet("min-width: 140px;")
        self.status_filter.setToolTip("Show only tasks with this status.")
        self.status_filter.currentTextChanged.connect(
            lambda _: self.refresh_view(self.view_selector.currentText()))

        self.priority_filter = QComboBox()
        self.priority_filter.addItem("All Priorities")
        self.priority_filter.addItems(PRIORITIES)
        self.priority_filter.setStyleSheet("min-width: 140px;")
        self.priority_filter.setToolTip("Show only tasks with this priority.")
        self.priority_filter.currentTextChanged.connect(
            lambda _: self.refresh_view(self.view_selector.currentText()))

        controls_layout.addWidget(self.search_edit)
        controls_layout.addWidget(self.status_filter)
        controls_layout.addWidget(self.priority_filter)
        controls_layout.addStretch()  # Pushes controls to the left

        # --- Tree Widget Data Display ---
        self.tree_widget = QTreeWidget()
        self.tree_widget.setHeaderLabels(
            ["Timeframe / Task Title", "Status", "Priority", "Deadline"])
        self.tree_widget.setAlternatingRowColors(True)
        self.tree_widget.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree_widget.customContextMenuRequested.connect(
            self._show_context_menu)
        self.tree_widget.setToolTip(
            "Right-click any task for a quick way to change its status.")

        hint = hint_row(
            "Right-click a task to change its status without opening the "
            "full editor.")

        self.layout.addLayout(controls_layout)
        self.layout.addWidget(hint)
        self.layout.addWidget(self.tree_widget)

        # Initial Population
        self.refresh_view(self.view_selector.currentText())

    def refresh(self, active_project):
        """Re-targets the view at a (possibly updated) project and redraws,
        preserving the current timeframe/search/filter selections."""
        self.active_project = active_project
        self.refresh_view(self.view_selector.currentText())

    def refresh_view(self, view_type: str):
        """
        Clears the current tree and repopulates it based on the selected
        timeframe, current search text, and status/priority filters.
        """
        self.tree_widget.clear()

        if view_type == "Weekly View":
            self._populate_weekly()
        else:
            self._populate_monthly()

        self.tree_widget.expandAll()

    def _active_tasks(self):
        """
        Returns the project's tasks, excluding any soft-deleted from Edit
        View, and matching the current search text and status/priority
        filters.
        """
        search_text = self.search_edit.text().strip().lower()
        status_filter = self.status_filter.currentText()
        priority_filter = self.priority_filter.currentText()

        tasks = []
        for task in self.active_project.tasks:
            if task.is_deleted:
                continue
            if search_text and search_text not in task.title.lower():
                continue
            if status_filter != "All Statuses" and task.status != status_filter:
                continue
            if priority_filter != "All Priorities" and task.priority != priority_filter:
                continue
            tasks.append(task)
        return tasks

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
                if task.is_overdue:
                    deadline_str += "  (Overdue)"
                task_item = QTreeWidgetItem(
                    group_item,
                    [task.title, task.status, task.priority, deadline_str])
                task_item.setIcon(1, status_icon(task.status))
                task_item.setIcon(2, priority_icon(task.priority))
                if task.is_overdue:
                    task_item.setIcon(0, icon("warning", color=RED))
                task_item.setData(0, Qt.ItemDataRole.UserRole, task)
                if task.is_overdue:
                    for col in range(4):
                        task_item.setForeground(col, QColor(RED))

        if unscheduled_tasks:
            un_item = QTreeWidgetItem(self.tree_widget,
                                      ["Unscheduled", "", "", ""])
            un_item.setBackground(0, QColor(BACKGROUND_ALT))
            font = un_item.font(0)
            font.setBold(True)
            un_item.setFont(0, font)
            for task in unscheduled_tasks:
                task_item = QTreeWidgetItem(
                    un_item,
                    [task.title, task.status, task.priority, "No Deadline"])
                task_item.setIcon(1, status_icon(task.status))
                task_item.setIcon(2, priority_icon(task.priority))
                task_item.setData(0, Qt.ItemDataRole.UserRole, task)

    def _show_context_menu(self, position):
        """
        Right-click quick-edit: lets the status of a task row be changed
        directly from the list, without opening the full Task dialog.
        """
        item = self.tree_widget.itemAt(position)
        if item is None:
            return
        task = item.data(0, Qt.ItemDataRole.UserRole)
        if task is None:
            return  # a group/timeframe header row, not a task row

        menu = QMenu(self)
        status_menu = menu.addMenu("Change Status")
        for status in STATUSES:
            action = status_menu.addAction(status)
            action.setEnabled(status != task.status)
            action.triggered.connect(lambda checked=False, s=status: self.
                                     _quick_set_status(task, s))
        menu.exec(self.tree_widget.viewport().mapToGlobal(position))

    def _quick_set_status(self, task, new_status: str):
        """Applies and persists a status change made via the context menu."""
        task.status = new_status
        task.is_completed = new_status == "Completed"
        self.file_manager.save_project(self.active_project)
        if self.on_change:
            self.on_change()
        else:
            self.refresh_view(self.view_selector.currentText())


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
                border-left: 3px solid {ACCENT};
                border-radius: 4px;
                padding: 14px 12px;
                margin-bottom: 8px;
                color: {INK};
                font-weight: 500;
            }}
            QListWidget::item:hover {{
                background-color: {BACKGROUND_ALT};
                border-left: 3px solid {ACCENT};
            }}
            QListWidget::item:selected {{
                background-color: {SURFACE};
                color: {INK};
                border: 1px solid {ACCENT};
                border-left: 3px solid {ACCENT};
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
        task_title = task.title
        came_from_other_column = source_widget is not self

        source_widget.takeItem(source_widget.row(dragged_item))
        new_item = QListWidgetItem(BoardView.card_text(task))
        new_item.setData(Qt.ItemDataRole.UserRole, task)
        if task.is_overdue:
            new_item.setForeground(QColor(RED))
            new_item.setIcon(icon("warning", color=RED))
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

    def __init__(self,
                 active_project,
                 file_manager,
                 on_change: Optional[Callable[[], None]] = None):
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
        self.add_task_btn = QPushButton("Add Task")
        self.add_task_btn.setIcon(icon("add", color="white"))
        self.add_task_btn.setStyleSheet(
            button_style(ACCENT) + "max-width: 160px;")
        self.add_task_btn.setToolTip(
            "Add a new task, starting in the Not Started column.")
        self.add_task_btn.clicked.connect(self.add_task)
        toolbar.addWidget(self.add_task_btn)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search cards...")
        add_search_icon(self.search_edit)
        self.search_edit.setStyleSheet("min-width: 180px;")
        self.search_edit.setToolTip("Type part of a task's title to filter the board.")
        self.search_edit.textChanged.connect(
            lambda _: self.populate_board_from_project())
        toolbar.addWidget(self.search_edit)

        self.priority_filter = QComboBox()
        self.priority_filter.addItem("All Priorities")
        self.priority_filter.addItems(PRIORITIES)
        self.priority_filter.setStyleSheet("min-width: 140px;")
        self.priority_filter.setToolTip("Show only cards with this priority.")
        self.priority_filter.currentTextChanged.connect(
            lambda _: self.populate_board_from_project())
        toolbar.addWidget(self.priority_filter)

        toolbar.addStretch()
        toolbar.addWidget(hint_row(
            "Drag cards between columns, or double-click one to edit it."))
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

            header_row = QHBoxLayout()
            header_icon = QLabel()
            header_icon.setPixmap(status_icon(title).pixmap(10, 10))
            header_row.addWidget(header_icon)
            header = QLabel(title.upper())
            header.setStyleSheet(
                f"font-weight: 700; font-size: 12px; color: {MUTED}; "
                f"letter-spacing: 1px; padding: 4px 2px 8px 2px;")
            header_row.addWidget(header)
            header_row.addStretch()

            add_col_btn = QPushButton()
            add_col_btn.setIcon(icon("add", color=ACCENT))
            add_col_btn.setToolTip(f"Add a task directly into {title}")
            add_col_btn.setStyleSheet(
                button_style("transparent", fg=ACCENT, padding="3px 7px") +
                f"border: 1px solid {BORDER}; max-width: 26px;")
            add_col_btn.clicked.connect(
                lambda checked=False, s=title: self.add_task(initial_status=s))
            header_row.addWidget(add_col_btn)

            col_header_wrapper = QWidget()
            col_header_wrapper.setLayout(header_row)
            col_header_wrapper.setStyleSheet(
                f"border-bottom: 2px solid {ACCENT};")

            col_layout.addWidget(col_header_wrapper)
            col_layout.addWidget(column_widget)
            self.layout.addLayout(col_layout)

        # Load real data instead of dummy data
        self.populate_board_from_project()

    @staticmethod
    def card_text(task) -> str:
        """Display text for a card - just the title; overdue state is now
        shown via a leading icon rather than baked into the text."""
        return task.title

    def refresh(self, active_project):
        """Re-targets the board at a (possibly updated) project and redraws,
        preserving the current search/priority filter selections."""
        self.active_project = active_project
        self.populate_board_from_project()

    def populate_board_from_project(self):
        """
        Reads the active Project object and populates the board 
        columns based on current task statuses. Soft-deleted tasks
        (from the Edit View) are excluded, as are any tasks that don't
        match the current search text / priority filter.
        """
        for column in self.columns.values():
            column.clear()

        search_text = self.search_edit.text().strip().lower()
        priority_filter = self.priority_filter.currentText()

        for task in self.active_project.tasks:
            if task.is_deleted:
                continue
            if search_text and search_text not in task.title.lower():
                continue
            if priority_filter != "All Priorities" and task.priority != priority_filter:
                continue
            # Fallback to "Not Started" if a status is missing or corrupted
            target_col = self.columns.get(task.status,
                                          self.columns["Not Started"])
            item = QListWidgetItem(self.card_text(task))
            item.setData(Qt.ItemDataRole.UserRole, task)
            if task.is_overdue:
                item.setForeground(QColor(RED))
                item.setIcon(icon("warning", color=RED))
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

    def add_task(self, checked=False, initial_status: Optional[str] = None):
        """
        Opens the New Task dialog and appends the result to the active
        project. If initial_status is given (from one of the per-column
        "+" buttons), the dialog pre-selects that status so the new task
        lands directly in that column instead of always defaulting to
        "Not Started".
        """
        dialog = TaskDialog(self.active_project.tasks,
                            task=None,
                            parent=self,
                            initial_status=initial_status)
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

        header_row = QHBoxLayout()
        header_row.addWidget(
            QLabel(
                "Select any combination of Projects, Tasks, and To-dos below.")
        )
        header_row.addStretch()
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText(
            "Search projects, tasks, to-dos...")
        self.search_edit.setStyleSheet("min-width: 220px;")
        self.search_edit.textChanged.connect(lambda _: self.populate_tree())
        header_row.addWidget(self.search_edit)
        self.layout.addLayout(header_row)

        self.tree_widget = QTreeWidget()
        self.tree_widget.setHeaderLabels(["Name", "Type", "Detail"])
        self.tree_widget.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection)
        self.tree_widget.setAlternatingRowColors(True)
        self.tree_widget.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree_widget.customContextMenuRequested.connect(
            self._show_context_menu)
        self.layout.addWidget(self.tree_widget)

        # Double-clicking a Task row opens it for editing.
        self.tree_widget.itemDoubleClicked.connect(self.edit_task)

        # --- Creation Bar ---
        creation_layout = QHBoxLayout()

        self.new_project_btn = QPushButton("New Project")
        self.new_project_btn.setIcon(icon("new_project", color="white"))
        self.new_project_btn.setStyleSheet(button_style(SUCCESS))
        self.new_project_btn.setToolTip("Create another project from scratch.")
        self.new_project_btn.clicked.connect(self.create_project)

        self.add_task_btn = QPushButton("Add Task")
        self.add_task_btn.setIcon(icon("add", color="white"))
        self.add_task_btn.setStyleSheet(button_style(ACCENT))
        self.add_task_btn.setToolTip(
            "Select a Project (or one of its Tasks) above first, then "
            "click here to add a new Task to it.")
        self.add_task_btn.clicked.connect(self.add_task)

        self.add_todo_btn = QPushButton("Add To-do")
        self.add_todo_btn.setIcon(icon("checklist", color="white"))
        self.add_todo_btn.setStyleSheet(button_style(ACCENT))
        self.add_todo_btn.setToolTip(
            "Select a Task (or a Project, for a general to-do) above "
            "first, then click here to add a checklist item.")
        self.add_todo_btn.clicked.connect(self.add_todo)

        creation_layout.addWidget(self.new_project_btn)
        creation_layout.addWidget(self.add_task_btn)
        creation_layout.addWidget(self.add_todo_btn)
        creation_layout.addStretch()
        creation_layout.addWidget(hint_row(
            "Select a Project or Task above, then Add Task / Add To-do. "
            "Double-click a Task to edit it."))

        self.layout.addLayout(creation_layout)

        # --- Action Bar ---
        action_layout = QHBoxLayout()

        self.delete_btn = QPushButton("Delete Selected")
        self.delete_btn.setIcon(icon("delete", color="white"))
        self.delete_btn.setStyleSheet(button_style(RED))
        self.delete_btn.setToolTip(
            "Moves everything checked above to the Trash tab. Nothing is "
            "erased permanently until you purge it from there.")
        self.delete_btn.clicked.connect(self.delete_selected)

        self.dest_combo = QComboBox()
        self.dest_combo.setStyleSheet("min-width: 180px;")
        self.dest_combo.setToolTip("Pick the project the copied task(s) should land in.")

        self.copy_btn = QPushButton("Copy Selected Task(s) to Project")
        self.copy_btn.setIcon(icon("copy", color="white"))
        self.copy_btn.setStyleSheet(button_style(ACCENT))
        self.copy_btn.setToolTip(
            "Duplicates the selected Task(s) into the destination project "
            "picked on the left, leaving the originals untouched.")
        self.copy_btn.clicked.connect(self.copy_selected_tasks)

        dest_label = QLabel("Destination Project:")
        dest_label.setStyleSheet(f"font-weight: 600; color: {MUTED};")
        action_layout.addWidget(self.delete_btn)
        action_layout.addStretch()
        action_layout.addWidget(dest_label)
        action_layout.addWidget(self.dest_combo)
        action_layout.addWidget(self.copy_btn)

        self.layout.addLayout(action_layout)

        self.populate_tree()

    def refresh(self, all_projects: List[Project]):
        """Re-targets the view at a (possibly updated) project list and
        redraws, preserving the current search text."""
        self.all_projects = all_projects
        self.populate_tree()

    def populate_tree(self):
        """
        Rebuilds the tree and the destination combo from all_projects.

        When the search box has text, a Task or To-do is only shown if its
        own title/description matches; a Project is shown if it matches,
        or if any of its Tasks/To-dos do (so matches keep their parent for
        context). The "General To-Dos" folder node is always shown for any
        visible project, search or not, since it also serves as a target
        for "Add To-do".
        """
        self.tree_widget.clear()
        self.dest_combo.clear()

        search_text = self.search_edit.text().strip().lower()

        for project in self.all_projects:
            if project.is_deleted:
                continue

            self.dest_combo.addItem(project.title, userData=project)

            visible_tasks = []
            for task in project.tasks:
                if task.is_deleted:
                    continue

                task_hits = not search_text or search_text in task.title.lower(
                )
                visible_todos = [
                    todo for todo in task.todo_list
                    if not todo.is_deleted and (not search_text or search_text
                                                in todo.description.lower())
                ]
                if search_text and not task_hits and not visible_todos:
                    continue
                visible_tasks.append((task, visible_todos))

            visible_general_todos = [
                todo for todo in project.general_todos
                if not todo.is_deleted and (
                    not search_text or search_text in todo.description.lower())
            ]

            project_hits = not search_text or search_text in project.title.lower(
            )
            if search_text and not project_hits and not visible_tasks and not visible_general_todos:
                continue

            project_item = QTreeWidgetItem(
                self.tree_widget, [project.title, "Project", project.subject])
            project_item.setData(0, Qt.ItemDataRole.UserRole,
                                 ("project", project, None, None))

            for task, visible_todos in visible_tasks:
                task_item = QTreeWidgetItem(project_item,
                                            [task.title, "Task", task.status])
                task_item.setData(0, Qt.ItemDataRole.UserRole,
                                  ("task", project, task, None))
                if task.is_overdue:
                    for col in range(3):
                        task_item.setForeground(col, QColor(RED))

                for todo in visible_todos:
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
            for todo in visible_general_todos:
                completed_label = "Done" if todo.is_completed else "Pending"
                todo_item = QTreeWidgetItem(
                    general_group_item,
                    [todo.description, "To-do", completed_label])
                todo_item.setData(0, Qt.ItemDataRole.UserRole,
                                  ("todo", project, None, todo))

        self.tree_widget.expandAll()

    def _show_context_menu(self, position):
        """
        Right-click quick-edit on a Task row: lets its status be changed
        directly, without opening the full Task dialog (which remains
        available via double-click for everything else).
        """
        item = self.tree_widget.itemAt(position)
        if item is None:
            return
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data or data[0] != "task":
            return
        _, project, task, _ = data

        menu = QMenu(self)
        status_menu = menu.addMenu("Change Status")
        for status in STATUSES:
            action = status_menu.addAction(status)
            action.setEnabled(status != task.status)
            action.triggered.connect(lambda checked=False, s=status: self.
                                     _quick_set_status(project, task, s))
        menu.exec(self.tree_widget.viewport().mapToGlobal(position))

    def _quick_set_status(self, project, task, new_status: str):
        """Applies and persists a status change made via the context menu."""
        task.status = new_status
        task.is_completed = new_status == "Completed"
        self.file_manager.save_project(project)
        self.populate_tree()
        self.on_change()

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
            kind, project, task, todo = item.data(0, Qt.ItemDataRole.UserRole)
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


class TrashView(QWidget):
    """
    Restores (or permanently removes) soft-deleted Projects, Tasks, and
    To-dos.

    is_deleted was already tracked on every Project, Task, and ToDo - set
    by EditView's "Delete Selected" and MainWindow's "Delete Project" - but
    nothing previously exposed those items again once deleted, so deletion
    was effectively permanent from the user's point of view. This view
    lists everything currently soft-deleted across every project and lets
    it be brought back.

    Attributes:
        all_projects (List[Project]): Every project regardless of its own
            is_deleted flag, loaded via
            FileManager.load_all_projects(include_deleted=True) - so both
            whole deleted Projects and deleted Tasks/To-dos belonging to
            still-active projects are visible here.
        file_manager (FileManager): Used to persist a restore, or to
            permanently delete a project's file.
        on_change (Callable): Invoked after a restore or permanent delete
            so the main window can reload the project switcher and every
            other tab.
    """

    def __init__(self, all_projects: List[Project], file_manager: FileManager,
                 on_change: Callable[[], None]):
        super().__init__()
        self.all_projects = all_projects
        self.file_manager = file_manager
        self.on_change = on_change

        self.layout = QVBoxLayout(self)
        self.layout.addWidget(hint_row(
            "Deleted Projects, Tasks, and To-dos. Select one or more, "
            "then Restore to bring them back."))

        self.tree_widget = QTreeWidget()
        self.tree_widget.setHeaderLabels(["Name", "Type", "Detail"])
        self.tree_widget.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection)
        self.tree_widget.setAlternatingRowColors(True)
        self.layout.addWidget(self.tree_widget)

        action_layout = QHBoxLayout()
        self.restore_btn = QPushButton("Restore Selected")
        self.restore_btn.setIcon(icon("restore", color="white"))
        self.restore_btn.setStyleSheet(button_style(SUCCESS))
        self.restore_btn.setToolTip(
            "Brings the selected item(s) back to exactly where they were.")
        self.restore_btn.clicked.connect(self.restore_selected)

        self.purge_btn = QPushButton("Permanently Delete Selected")
        self.purge_btn.setIcon(icon("delete", color="white"))
        self.purge_btn.setStyleSheet(button_style(RED))
        self.purge_btn.setToolTip(
            "Removes the selected item(s) for good. Unlike the regular "
            "Delete elsewhere in the app, this cannot be undone.")
        self.purge_btn.clicked.connect(self.purge_selected)

        action_layout.addWidget(self.restore_btn)
        action_layout.addWidget(self.purge_btn)
        action_layout.addStretch()
        self.layout.addLayout(action_layout)

        self.populate_tree()

    def refresh(self, all_projects: List[Project]):
        """Re-targets the view at a (possibly updated) project list, and
        redraws."""
        self.all_projects = all_projects
        self.populate_tree()

    def _add_group(self, label: str):
        """Adds a bold section header row (e.g. "Deleted Tasks") to the tree."""
        group_item = QTreeWidgetItem(self.tree_widget, [label, "", ""])
        group_item.setBackground(0, QColor(BACKGROUND_ALT))
        font = group_item.font(0)
        font.setBold(True)
        group_item.setFont(0, font)
        return group_item

    def populate_tree(self):
        """
        Rebuilds the tree from all_projects: a "Deleted Projects" group for
        whole soft-deleted projects, plus "Deleted Tasks" and "Deleted
        To-dos" groups for items whose *parent* project is still active.

        Deleted Tasks/To-dos belonging to an already-deleted Project are
        intentionally left out of those latter two groups - restoring the
        Project itself brings its whole task/to-do list back as-is, so
        listing them separately here would just be confusing duplication.
        """
        self.tree_widget.clear()

        deleted_projects = [p for p in self.all_projects if p.is_deleted]
        active_projects = [p for p in self.all_projects if not p.is_deleted]

        deleted_task_rows = []
        deleted_todo_rows = []
        for project in active_projects:
            for task in project.tasks:
                if task.is_deleted:
                    deleted_task_rows.append((project, task))
                for todo in task.todo_list:
                    if todo.is_deleted:
                        deleted_todo_rows.append((project, task, todo))
            for todo in project.general_todos:
                if todo.is_deleted:
                    deleted_todo_rows.append((project, None, todo))

        if deleted_projects:
            group = self._add_group("Deleted Projects")
            for project in deleted_projects:
                item = QTreeWidgetItem(
                    group, [project.title, "Project", project.subject])
                item.setData(0, Qt.ItemDataRole.UserRole,
                             ("deleted_project", project, None, None))

        if deleted_task_rows:
            group = self._add_group("Deleted Tasks")
            for project, task in deleted_task_rows:
                item = QTreeWidgetItem(
                    group, [task.title, "Task", f"from '{project.title}'"])
                item.setData(0, Qt.ItemDataRole.UserRole,
                             ("deleted_task", project, task, None))

        if deleted_todo_rows:
            group = self._add_group("Deleted To-dos")
            for project, task, todo in deleted_todo_rows:
                owner = (f"from '{task.title}'"
                         if task else f"from '{project.title}' (general)")
                item = QTreeWidgetItem(group,
                                       [todo.description, "To-do", owner])
                item.setData(0, Qt.ItemDataRole.UserRole,
                             ("deleted_todo", project, task, todo))

        if not deleted_projects and not deleted_task_rows and not deleted_todo_rows:
            placeholder = QTreeWidgetItem(
                self.tree_widget,
                ["Trash is empty - nothing to restore right now.", "", ""])
            placeholder.setIcon(0, icon("empty", color=MUTED))
            placeholder.setDisabled(True)

        self.tree_widget.expandAll()

    def _selected_restorable_items(self):
        """Returns the (kind, project, task, todo) tuples behind every
        selected row, skipping group-header rows (which carry no data)."""
        items = []
        for tree_item in self.tree_widget.selectedItems():
            data = tree_item.data(0, Qt.ItemDataRole.UserRole)
            if data:
                items.append(data)
        return items

    def restore_selected(self):
        """Un-does is_deleted on every selected item and persists it."""
        selected = self._selected_restorable_items()
        if not selected:
            QMessageBox.information(
                self, "Nothing Selected",
                "Select one or more deleted items to restore.")
            return

        affected_projects = set()
        for kind, project, task, todo in selected:
            if kind == "deleted_project":
                project.is_deleted = False
            elif kind == "deleted_task":
                task.is_deleted = False
            elif kind == "deleted_todo":
                todo.is_deleted = False
            else:
                continue
            affected_projects.add(project)

        for project in affected_projects:
            self.file_manager.save_project(project)

        self.populate_tree()
        self.on_change()

    def purge_selected(self):
        """
        Permanently removes the selected already-deleted items. This is
        the only irreversible action in the Trash, so it asks for
        confirmation first.
        """
        selected = self._selected_restorable_items()
        if not selected:
            QMessageBox.information(
                self, "Nothing Selected",
                "Select one or more deleted items to permanently remove.")
            return

        confirm = QMessageBox.question(
            self, "Permanently Delete",
            f"Permanently remove {len(selected)} item(s)? Unlike a regular "
            f"delete, this cannot be undone from the Trash.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if confirm != QMessageBox.StandardButton.Yes:
            return

        projects_to_purge = set()
        affected_projects = set()

        for kind, project, task, todo in selected:
            if kind == "deleted_project":
                projects_to_purge.add(project)
            elif kind == "deleted_task":
                if task in project.tasks:
                    project.tasks.remove(task)
                affected_projects.add(project)
            elif kind == "deleted_todo":
                owner_list = task.todo_list if task is not None else project.general_todos
                if todo in owner_list:
                    owner_list.remove(todo)
                affected_projects.add(project)

        for project in projects_to_purge:
            self.file_manager.delete_project_file(project)
        # A project being purged makes any task/to-do edits made to it in
        # the loop above moot - drop it from the save list so we don't
        # recreate the very file we just deleted.
        for project in affected_projects - projects_to_purge:
            self.file_manager.save_project(project)

        self.populate_tree()
        self.on_change()
