import json
import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional


class ToDo:
    """
    Represents a single actionable item within a Task.
    
    A To-do list cannot include another Task or Project.
    
    Attributes:
        description (str): What to do field.
        is_completed (bool): Completion status of the to-do item.
        is_deleted (bool): Soft delete flag for the edit mode.
    """

    def __init__(self, description: str):
        self.description = description
        self.is_completed = False
        self.is_deleted = False


class Task:
    """
    Represents a distinct assignment within a Project.
    
    A Task can have multiple To-do items, but cannot belong to multiple 
    Projects or have additional Tasks listed under it.
    
    Attributes:
        title (str): The title of the task.
        status (str): Current state ('Not Started', 'In Progress', 'Completed', 'On Hold').
        priority (str): Triage level ('Low', 'Medium', 'High') for multiple active projects.
        description (str): Detailed explanation of the task.
        date_started (Optional[datetime.date]): The start date.
        date_to_be_completed (Optional[datetime.date]): The deadline.
        is_completed (bool): Overall task completion status.
        is_deleted (bool): Soft delete flag for edit mode.
        todo_list (List[ToDo]): Associated list of ToDo items.
        duration_days (int): Estimated effort in days, used by the Critical
            Path Method engine. A value of 0 marks the task as a milestone.
        dependencies (List[str]): Titles of prerequisite tasks within the
            same project, used by the CPM engine and the dependency canvas.
        canvas_x (Optional[float]): Last manually-arranged X position of
            this task's node on the Dependency Canvas. None until the user
            drags the node at least once, at which point the canvas falls
            back to its auto-scatter layout for this node.
        canvas_y (Optional[float]): Same as canvas_x, for the Y position.
    """

    def __init__(self,
                 title: str,
                 description: str,
                 priority: str = "Medium",
                 duration_days: int = 1):
        self.title = title
        self.status = "Not Started"
        self.priority = priority
        self.description = description
        self.date_started: Optional[datetime.date] = None
        self.date_to_be_completed: Optional[datetime.date] = None
        self.is_completed = False
        self.is_deleted = False
        self.todo_list: List[ToDo] = []
        self.duration_days = duration_days
        self.dependencies: List[str] = [
        ]  # Stores the titles of prerequisite tasks, used by the CPM engine
        self.canvas_x: Optional[float] = None
        self.canvas_y: Optional[float] = None

    @property
    def is_overdue(self) -> bool:
        """
        True when this task has a deadline in the past and hasn't been
        completed yet. Used by the List, Board, Gantt, and Milestone views
        to flag at-risk work consistently across the app.
        """
        if self.is_completed or not self.date_to_be_completed:
            return False
        return self.date_to_be_completed < datetime.date.today()

    def add_todo(self, todo: ToDo) -> None:
        """Appends a new ToDo item to the task's checklist."""
        self.todo_list.append(todo)

    def add_dependency(self, target_task_title: str):
        """Visually linking nodes will trigger this method."""
        if target_task_title not in self.dependencies:
            self.dependencies.append(target_task_title)


def find_dependency_cycle(
        deps_by_title: Dict[str, List[str]]) -> Optional[List[str]]:
    """
    Detects a cycle in a task dependency graph.

    Used both by the CPM engine's own topological pass (indirectly, via
    its "no progress" bail-out) and, more importantly, by TaskDialog
    *before* a dependency selection is ever saved - so a cycle is caught
    at entry time instead of surfacing later as a generic error on the
    Critical Path tab.

    Args:
        deps_by_title: Mapping of task title -> list of prerequisite task
            titles. A dependency title that isn't itself a key (e.g. it
            belongs to a task outside the set being checked) is ignored
            rather than treated as an error.

    Returns:
        Optional[List[str]]: The titles forming a cycle, in order (with
            the first title repeated at the end to show the loop closing),
            or None if the graph is acyclic.
    """
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {title: WHITE for title in deps_by_title}
    path: List[str] = []

    def visit(title: str) -> Optional[List[str]]:
        color[title] = GRAY
        path.append(title)
        for dep in deps_by_title.get(title, []):
            if dep not in color:
                continue
            if color[dep] == GRAY:
                cycle_start = path.index(dep)
                return path[cycle_start:] + [dep]
            if color[dep] == WHITE:
                found = visit(dep)
                if found:
                    return found
        path.pop()
        color[title] = BLACK
        return None

    for title in deps_by_title:
        if color[title] == WHITE:
            found = visit(title)
            if found:
                return found
    return None


class Project:
    """
    Represents a top-level organizational container for Tasks.
    
    A Project can have multiple Tasks assigned to it.
    
    Attributes:
        title (str): Name of the project.
        subject (str): The general category or client.
        description (str): Comprehensive overview of the project.
        date_created (datetime.datetime): Timestamp of creation.
        last_updated (datetime.datetime): Timestamp of most recent activity.
        is_completed (bool): Overall completion status.
        is_archived (bool): Archive option to hide from active views.
        is_deleted (bool): Soft delete option visible on edit mode.
        tasks (List[Task]): Associated list of tasks.
    """

    def __init__(self, title: str, subject: str, description: str):
        self.title = title
        self.subject = subject
        self.description = description
        self.date_created = datetime.datetime.now()
        self.last_updated = self.date_created
        self.is_completed = False
        self.is_archived = False
        self.is_deleted = False
        self.tasks: List[Task] = []
        # A standalone checklist that isn't tied to any single Task, e.g.
        # for project-wide reminders. Kept separate from each Task's own
        # todo_list, which is scoped to that one task.
        self.general_todos: List[ToDo] = []

        # --- Plan tab ---
        # Free-form, word-processor-style writing surface for the project,
        # stored as the QTextEdit's rich-text HTML so formatting (bold,
        # lists, ...) survives a save/reload round-trip.
        self.plan_content: str = ""
        # A separate checklist of "things to get done" for the written
        # plan itself - distinct from general_todos (which is a plain
        # project-wide reminder list rendered without rich text elsewhere).
        self.plan_checklist: List[ToDo] = []

        # --- Sketch tab ---
        # A JSON-encoded list of shape dicts (freehand strokes, rectangles,
        # ellipses, sticky notes) making up the Miro-style sketch board.
        # Kept as an opaque string here (rather than parsed objects) since
        # only sketch_view.py needs to understand its structure.
        self.sketch_data: str = "[]"

    @property
    def progress(self) -> float:
        """
        Auto-calculates the completion percentage based on associated tasks.
        Highly useful for dashboard views.
        
        Returns:
            float: Percentage of completed tasks (0.0 to 100.0). 
                   Returns 0.0 if no tasks exist.
        """
        if not self.tasks:
            return 0.0

        completed_tasks = sum(1 for task in self.tasks if task.is_completed)
        return (completed_tasks / len(self.tasks)) * 100

    def add_task(self, task: Task) -> None:
        """
        Associates a new Task with this Project and updates the 
        last updated activity timestamp.
        """
        self.tasks.append(task)
        self.last_updated = datetime.datetime.now()

    def add_general_todo(self, todo: ToDo) -> None:
        """
        Adds a standalone To-do item to this project's general checklist -
        one that isn't attached to any specific Task.
        """
        self.general_todos.append(todo)
        self.last_updated = datetime.datetime.now()

    def rename_task_references(self, old_title: str, new_title: str) -> None:
        """
        After a task's title changes, updates every other task's
        dependencies list in this project so links that pointed at the old
        title keep pointing at the same task under its new title. The CPM
        engine and dependency canvas both key off of title, so a rename
        would otherwise silently break existing dependency links.
        """
        if old_title == new_title:
            return
        for task in self.tasks:
            task.dependencies = [
                new_title if dep == old_title else dep
                for dep in task.dependencies
            ]


class FileManager:
    """
    Handles the serialization and deserialization of Project data to local JSON files.
    
    Ensures data is securely stored and retrieved from the user's 
    '/ProjectManagement/' directory without relying on an external database.
    
    Attributes:
        storage_dir (Path): The absolute path to the local storage directory.
    """

    def __init__(self):
        # Resolve the folder relative to the current file's directory
        self.storage_dir = Path(__file__).resolve().parent / "ProjectManagement"
        self._initialize_storage()

    def _initialize_storage(self) -> None:
        """
        Verifies if the target directory exists. If not, it creates the directory 
        structure to prevent FileNotFoundError exceptions during save operations.
        """
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def serialize_project(self, project) -> Dict[str, Any]:
        """
        Converts a Project instance (and its nested Tasks and To-do lists) into 
        a JSON-compatible dictionary.
        
        Args:
            project: The Project object to serialize.
            
        Returns:
            Dict[str, Any]: The deeply nested dictionary representing the project.
        """
        return {
            "title":
            project.title,
            "subject":
            project.subject,
            "description":
            project.description,
            "date_created":
            project.date_created.isoformat(),
            "last_updated":
            project.last_updated.isoformat(),
            "is_completed":
            project.is_completed,
            "is_archived":
            project.is_archived,
            "is_deleted":
            project.is_deleted,
            "tasks": [{
                "title":
                task.title,
                "status":
                task.status,
                "priority":
                task.priority,
                "description":
                task.description,
                "date_started":
                task.date_started.isoformat() if task.date_started else None,
                "date_to_be_completed":
                task.date_to_be_completed.isoformat()
                if task.date_to_be_completed else None,
                "is_completed":
                task.is_completed,
                "is_deleted":
                task.is_deleted,
                "duration_days":
                task.duration_days,
                "dependencies":
                task.dependencies,
                "canvas_x":
                task.canvas_x,
                "canvas_y":
                task.canvas_y,
                "todo_list": [{
                    "description": todo.description,
                    "is_completed": todo.is_completed,
                    "is_deleted": todo.is_deleted
                } for todo in task.todo_list]
            } for task in project.tasks],
            "general_todos": [{
                "description": todo.description,
                "is_completed": todo.is_completed,
                "is_deleted": todo.is_deleted
            } for todo in project.general_todos],
            "plan_content":
            project.plan_content,
            "plan_checklist": [{
                "description": todo.description,
                "is_completed": todo.is_completed,
                "is_deleted": todo.is_deleted
            } for todo in project.plan_checklist],
            "sketch_data":
            project.sketch_data
        }

    def deserialize_project(self, data: Dict[str, Any]) -> Project:
        """
        Rebuilds a Project instance (with nested Task and ToDo objects) from
        a dictionary previously produced by serialize_project.

        Required so features that operate on live objects - the project
        switcher, the Edit View, and the chart tabs - can work with data
        that was reloaded from disk rather than only the in-memory session.

        Args:
            data: The dictionary loaded from a project JSON file.

        Returns:
            Project: A fully reconstructed Project, including its Tasks
                     and their ToDo items.
        """
        project = Project(data["title"], data["subject"], data["description"])
        project.date_created = datetime.datetime.fromisoformat(
            data["date_created"])
        project.last_updated = datetime.datetime.fromisoformat(
            data["last_updated"])
        project.is_completed = data["is_completed"]
        project.is_archived = data["is_archived"]
        project.is_deleted = data["is_deleted"]

        for task_data in data.get("tasks", []):
            task = Task(task_data["title"],
                        task_data["description"],
                        priority=task_data.get("priority", "Medium"),
                        duration_days=task_data.get("duration_days", 1))
            task.status = task_data["status"]
            task.is_completed = task_data["is_completed"]
            task.is_deleted = task_data["is_deleted"]
            task.dependencies = task_data.get("dependencies", [])
            task.canvas_x = task_data.get("canvas_x")
            task.canvas_y = task_data.get("canvas_y")
            if task_data.get("date_started"):
                task.date_started = datetime.date.fromisoformat(
                    task_data["date_started"])
            if task_data.get("date_to_be_completed"):
                task.date_to_be_completed = datetime.date.fromisoformat(
                    task_data["date_to_be_completed"])

            for todo_data in task_data.get("todo_list", []):
                todo = ToDo(todo_data["description"])
                todo.is_completed = todo_data["is_completed"]
                todo.is_deleted = todo_data["is_deleted"]
                task.add_todo(todo)

            project.tasks.append(task)

        for todo_data in data.get("general_todos", []):
            todo = ToDo(todo_data["description"])
            todo.is_completed = todo_data["is_completed"]
            todo.is_deleted = todo_data["is_deleted"]
            project.general_todos.append(todo)

        # Both default gracefully for project files saved before the Plan
        # and Sketch tabs existed.
        project.plan_content = data.get("plan_content", "")
        for todo_data in data.get("plan_checklist", []):
            todo = ToDo(todo_data["description"])
            todo.is_completed = todo_data["is_completed"]
            todo.is_deleted = todo_data["is_deleted"]
            project.plan_checklist.append(todo)
        project.sketch_data = data.get("sketch_data", "[]")

        return project

    def _file_path_for(self, project) -> Path:
        """The on-disk JSON path for a project, derived from its title."""
        safe_filename = "".join(c for c in project.title
                                if c.isalnum() or c in (' ', '_')).rstrip()
        return self.storage_dir / f"{safe_filename}.json"

    def save_project(self, project) -> None:
        """
        Writes a single project to a JSON file. The file name is dynamically 
        generated based on the project's title to ensure easy identification.
        
        Args:
            project: The Project object to be saved.
        """
        file_path = self._file_path_for(project)
        project_data = self.serialize_project(project)

        with open(file_path, "w", encoding="utf-8") as file:
            json.dump(project_data, file, indent=4)

    def delete_project_file(self, project) -> None:
        """
        Permanently removes a project's JSON file from disk.

        Used only by the Trash view's "Permanently Delete" action.
        Everywhere else in the app, deletion goes through the is_deleted
        soft-delete flag (via save_project) instead, precisely so it can
        still be undone from the Trash.
        """
        self._file_path_for(project).unlink(missing_ok=True)

    def load_all_projects(self,
                          include_deleted: bool = False) -> List[Project]:
        """
        Scans the storage directory and loads all JSON files back into memory
        as live Project objects. Used by the UI to populate the project
        switcher and the Edit View.

        Args:
            include_deleted: When False (the default, used everywhere
                except the Trash view), soft-deleted projects are left out
                entirely, the same way soft-deleted Tasks and ToDos are
                excluded by the views. When True, every project is
                returned regardless of its is_deleted flag, so the Trash
                view can offer them for restoration.

        Returns:
            List[Project]: Every project found in the storage directory,
                           fully reconstructed with its Tasks and ToDo
                           items, filtered by is_deleted per include_deleted
                           above.
        """
        loaded_projects = []

        for file_path in self.storage_dir.glob("*.json"):
            with open(file_path, "r", encoding="utf-8") as file:
                try:
                    project_data = json.load(file)
                    project = self.deserialize_project(project_data)
                    if project.is_deleted and not include_deleted:
                        continue
                    loaded_projects.append(project)
                except (json.JSONDecodeError, KeyError):
                    # Log error internally or handle corrupted/legacy files gracefully
                    continue

        return loaded_projects
