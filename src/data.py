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

    def add_todo(self, todo: ToDo) -> None:
        """Appends a new ToDo item to the task's checklist."""
        self.todo_list.append(todo)

    def add_dependency(self, target_task_title: str):
        """Visually linking nodes will trigger this method."""
        if target_task_title not in self.dependencies:
            self.dependencies.append(target_task_title)


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
    'Documents/ProjectManagement/' directory without relying on an external database.
    
    Attributes:
        storage_dir (Path): The absolute path to the local storage directory.
    """

    def __init__(self):
        self.storage_dir = Path.home() / "Documents" / "ProjectManagement"
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
            } for todo in project.general_todos]
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

        return project

    def save_project(self, project) -> None:
        """
        Writes a single project to a JSON file. The file name is dynamically 
        generated based on the project's title to ensure easy identification.
        
        Args:
            project: The Project object to be saved.
        """
        safe_filename = "".join(c for c in project.title
                                if c.isalnum() or c in (' ', '_')).rstrip()
        file_path = self.storage_dir / f"{safe_filename}.json"

        project_data = self.serialize_project(project)

        with open(file_path, "w", encoding="utf-8") as file:
            json.dump(project_data, file, indent=4)

    def load_all_projects(self) -> List[Project]:
        """
        Scans the storage directory and loads all JSON files back into memory
        as live Project objects. Used by the UI to populate the project
        switcher and the Edit View.
        
        Returns:
            List[Project]: Every non-deleted project found in the storage
                           directory, fully reconstructed with its Tasks
                           and ToDo items. Soft-deleted projects (is_deleted
                           == True) are excluded, the same way soft-deleted
                           Tasks and ToDos are excluded by the views.
        """
        loaded_projects = []

        for file_path in self.storage_dir.glob("*.json"):
            with open(file_path, "r", encoding="utf-8") as file:
                try:
                    project_data = json.load(file)
                    project = self.deserialize_project(project_data)
                    if project.is_deleted:
                        continue
                    loaded_projects.append(project)
                except (json.JSONDecodeError, KeyError):
                    # Log error internally or handle corrupted/legacy files gracefully
                    continue

        return loaded_projects
