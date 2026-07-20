"""
Tracking and reporting visuals for business-meeting use: the Critical Path
Method engine and its dependency canvas, the Gantt chart, and the Milestone
chart. Kept separate from views.py so the reporting/analysis layer can be
reused or tested independently of the day-to-day task-editing widgets.
"""
import datetime

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QGraphicsView,
                             QGraphicsScene, QGraphicsRectItem,
                             QGraphicsTextItem, QGraphicsLineItem, QPushButton,
                             QMessageBox, QLabel)
from PyQt6.QtGui import QPen, QBrush, QColor
from PyQt6.QtCore import Qt

from matplotlib.figure import Figure
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
import matplotlib.dates as mdates

from styles import (INK, ACCENT, SUCCESS, WARNING, RED, BORDER, button_style,
                    hint_style)
from icons import icon
from widgets import hint_row

# Status -> colour mapping shared across the Gantt and Milestone charts so
# a task's stage reads consistently across every reporting view.
STATUS_COLOURS = {
    "Not Started": "#9AA0AC",
    "In Progress": ACCENT,
    "On Hold": WARNING,
    "Completed": SUCCESS,
}


def calculate_critical_path(tasks: list) -> list:
    """
    Executes the Forward and Backward pass algorithms to determine the Critical Path.

    Args:
        tasks (list): A list of Task objects belonging to the Project.

    Returns:
        list: A list of Task titles that make up the critical path.
    """
    # Dictionary to hold the computed CPM variables for each task
    cpm_data = {
        task.title: {
            'ES': 0,
            'EF': 0,
            'LS': 0,
            'LF': 0,
            'duration': task.duration_days,
            'deps': task.dependencies
        }
        for task in tasks
    }

    # FORWARD PASS: Calculate ES and EF
    # We must process tasks in topological order (prerequisites first)
    processed = []
    while len(processed) < len(tasks):
        made_progress = False
        for task in tasks:
            if task.title in processed:
                continue

            # Check if all dependencies have been processed
            if all(dep in processed for dep in task.dependencies):
                if not task.dependencies:
                    cpm_data[task.title]['ES'] = 0
                else:
                    cpm_data[task.title]['ES'] = max(
                        cpm_data[dep]['EF'] for dep in task.dependencies)

                cpm_data[task.title]['EF'] = cpm_data[
                    task.title]['ES'] + cpm_data[task.title]['duration']
                processed.append(task.title)
                made_progress = True

        # A pass that adds nothing means the remaining tasks form a cycle -
        # bail out rather than loop forever.
        if not made_progress:
            raise ValueError(
                "Cyclic dependency detected among the remaining tasks.")

    # Calculate the total project duration (Max EF of all tasks)
    project_duration = max(data['EF'] for data in cpm_data.values())

    # BACKWARD PASS: Calculate LF and LS
    # Traverse in reverse topological order
    for task_title in reversed(processed):
        # Find all tasks that depend on THIS task (successors)
        successors = [t for t in cpm_data if task_title in cpm_data[t]['deps']]

        if not successors:
            cpm_data[task_title]['LF'] = project_duration
        else:
            cpm_data[task_title]['LF'] = min(cpm_data[succ]['LS']
                                             for succ in successors)

        cpm_data[task_title]['LS'] = cpm_data[task_title]['LF'] - cpm_data[
            task_title]['duration']

    # CRITICAL PATH EXTRACTION: Slack == 0
    critical_path = []
    for task_title, data in cpm_data.items():
        slack = data['LS'] - data['ES']
        if slack == 0:
            critical_path.append(task_title)

    return critical_path


class TaskNode(QGraphicsRectItem):
    """
    A visual representation of a Task on the Dependency Canvas.
    Users can drag these nodes around the workspace.
    """

    def __init__(self, task, x, y, on_moved=None):
        super().__init__(x, y, 150, 50)
        self.task = task
        # Invoked with (task, scene_x, scene_y) once a drag finishes, so
        # the canvas can persist the new layout onto the Task itself
        # instead of losing it the next time this view is rebuilt.
        self.on_moved = on_moved
        self.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemIsMovable)
        self.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemIsSelectable)

        # Enterprise Styling
        self.setBrush(QBrush(QColor(ACCENT)))
        self.setPen(QPen(Qt.PenStyle.NoPen))

        # Task Title Text
        self.text = QGraphicsTextItem(task.title, self)
        self.text.setDefaultTextColor(QColor("white"))
        self.text.setPos(x + 10, y + 15)

    def mouseReleaseEvent(self, event):
        """Reports the node's resting position once a drag completes."""
        super().mouseReleaseEvent(event)
        if self.on_moved:
            top_left = self.sceneBoundingRect().topLeft()
            self.on_moved(self.task, top_left.x(), top_left.y())


class DependencyCanvas(QWidget):
    """
    The Visual Mapping UI. Replaces standard dropdowns by allowing 
    users to view and generate the Critical Path visually.
    """

    def __init__(self, active_project, file_manager=None):
        super().__init__()
        self.active_project = active_project
        # Used to persist node positions as they're dragged. Optional so
        # the widget stays constructible (e.g. in tests) without one; in
        # that case positions simply aren't saved.
        self.file_manager = file_manager
        self.layout = QVBoxLayout(self)

        caption = hint_row(
            "Each box is a task. Drag a box onto this canvas to reposition "
            "it; arrows show which tasks depend on which.")
        self.layout.addWidget(caption)

        # Setup the 2D Graphics Scene
        self.scene = QGraphicsScene()
        self.view = QGraphicsView(self.scene)
        self.view.setRenderHint(self.view.renderHints().Antialiasing)
        self.view.setStyleSheet(
            f"border: 1px solid {BORDER}; border-radius: 12px; background-color: white;"
        )

        # Calculation Button
        self.calc_btn = QPushButton("Calculate Critical Path")
        self.calc_btn.setIcon(icon("milestone_chart", color="white"))
        self.calc_btn.setStyleSheet(button_style(SUCCESS, padding="10px 16px"))
        self.calc_btn.setToolTip(
            "Works out the longest chain of dependent tasks - the "
            "sequence that determines your earliest possible finish date.")
        self.calc_btn.clicked.connect(self.run_cpm_analysis)

        self.layout.addWidget(self.view)
        self.layout.addWidget(self.calc_btn)

        self.nodes = {}
        self.populate_canvas()

    def refresh(self, active_project):
        """Re-targets the canvas at a (possibly updated) project and redraws."""
        self.active_project = active_project
        self.populate_canvas()

    def populate_canvas(self):
        """
        Draws the task nodes and their existing dependency lines.

        A node whose Task has a saved canvas_x/canvas_y (from a previous
        drag) is placed there; nodes without a saved position fall back to
        the auto-scatter grid, which keeps advancing regardless so newly
        added tasks don't land on top of an already-positioned one.
        """
        self.scene.clear()
        self.nodes.clear()

        x_offset = 50
        y_offset = 50
        for task in self.active_project.tasks:
            if task.is_deleted:
                continue

            if task.canvas_x is not None and task.canvas_y is not None:
                node_x, node_y = task.canvas_x, task.canvas_y
            else:
                node_x, node_y = x_offset, y_offset

            node = TaskNode(task,
                            node_x,
                            node_y,
                            on_moved=self.handle_node_moved)
            self.scene.addItem(node)
            self.nodes[task.title] = node

            x_offset += 180
            if x_offset > 600:
                x_offset = 50
                y_offset += 80

        self.draw_dependency_lines()

    def handle_node_moved(self, task, x, y):
        """
        Persists a node's resting position onto its Task once a drag
        finishes, so the layout survives a rebuild of this tab (or the
        app restarting) instead of resetting to the auto-scatter grid.
        """
        task.canvas_x = x
        task.canvas_y = y
        if self.file_manager:
            self.file_manager.save_project(self.active_project)

    def draw_dependency_lines(self):
        """Renders arrows/lines between dependent task nodes."""
        pen = QPen(QColor(INK), 2)

        for target_title, target_node in self.nodes.items():
            for dep_title in target_node.task.dependencies:
                if dep_title in self.nodes:
                    source_node = self.nodes[dep_title]

                    # Connect the center of the source to the target
                    source_center = source_node.sceneBoundingRect().center()
                    target_center = target_node.sceneBoundingRect().center()

                    line = QGraphicsLineItem(source_center.x(),
                                             source_center.y(),
                                             target_center.x(),
                                             target_center.y())
                    line.setPen(pen)
                    line.setZValue(-1)  # Send lines behind nodes
                    self.scene.addItem(line)

    def run_cpm_analysis(self):
        """Triggers the backend CPM algorithm and displays the results to the client."""
        try:
            active_tasks = [
                t for t in self.active_project.tasks if not t.is_deleted
            ]
            critical_path = calculate_critical_path(active_tasks)
            path_str = " \n\u2193\n ".join(critical_path)

            msg = QMessageBox()
            msg.setWindowTitle("Critical Path Method Results")
            msg.setText(
                f"The exact sequence of critical tasks that dictates your timeline is:\n\n{path_str}"
            )
            msg.exec()
        except Exception:
            QMessageBox.critical(
                self, "Error",
                "Cyclic dependency detected or missing data. Please verify your prerequisites."
            )


class GanttChartWidget(QWidget):
    """
    Renders a Gantt chart of every non-deleted task in the active project,
    for use in status/business-meeting reporting.

    Bars run from date_started to date_to_be_completed. Where either date is
    missing, the project's creation date and the task's duration_days are
    used as a fallback so a task always appears on the timeline.
    """

    def __init__(self, active_project):
        super().__init__()
        self.active_project = active_project
        layout = QVBoxLayout(self)

        caption = hint_row(
            "Each bar is a task, running from its start date to its "
            "deadline. This chart is read-only - edit tasks from the List "
            "or Board tab.")
        layout.addWidget(caption)

        self.figure = Figure(figsize=(8, 5), tight_layout=True)
        self.canvas = FigureCanvas(self.figure)
        layout.addWidget(self.canvas)

        self.render_chart()

    def refresh(self, active_project):
        """Re-targets the chart at a (possibly updated) project and redraws."""
        self.active_project = active_project
        self.render_chart()

    def render_chart(self):
        """Clears and redraws the chart from the current project state."""
        self.figure.clear()
        ax = self.figure.add_subplot(111)

        tasks = [t for t in self.active_project.tasks if not t.is_deleted]

        if not tasks:
            ax.text(0.5,
                    0.5,
                    "No tasks yet.\nAdd one from the List or Board tab to "
                    "see it here.",
                    ha="center",
                    va="center")
            ax.axis("off")
            self.canvas.draw()
            return

        fallback_start = self.active_project.date_created.date()

        for row, task in enumerate(tasks):
            start = task.date_started or fallback_start
            end = task.date_to_be_completed or (
                start + datetime.timedelta(days=max(task.duration_days, 1)))
            if end < start:
                end = start

            span_days = max((end - start).days, 1)
            # Overdue tasks get a red outline on top of their status
            # colour, so at-risk work reads consistently with the rest of
            # the app without losing the status-colour coding.
            ax.barh(row,
                    span_days,
                    left=mdates.date2num(start),
                    height=0.5,
                    color=STATUS_COLOURS.get(task.status, "#9AA0AC"),
                    edgecolor=RED if task.is_overdue else "none",
                    linewidth=2.2 if task.is_overdue else 0)

        ax.set_yticks(range(len(tasks)))
        ax.set_yticklabels([("OVERDUE - " if t.is_overdue else "") + t.title
                            for t in tasks])
        ax.invert_yaxis()
        ax.xaxis_date()
        ax.set_xlabel("Date")
        ax.set_title(f"Gantt Chart - {self.active_project.title}")
        self.figure.autofmt_xdate()
        self.canvas.draw()


class MilestoneChartWidget(QWidget):
    """
    Renders a milestone timeline for the active project.

    A task is treated as a milestone when duration_days == 0, following
    standard PM convention: a milestone marks a point in time rather than a
    span of work, so it consumes no duration of its own.
    """

    def __init__(self, active_project):
        super().__init__()
        self.active_project = active_project
        layout = QVBoxLayout(self)

        caption = hint_row(
            "Milestones are tasks with 0 days of duration - set a task's "
            "duration to 0 in its editor to have it show up here.")
        layout.addWidget(caption)

        self.figure = Figure(figsize=(8, 3), tight_layout=True)
        self.canvas = FigureCanvas(self.figure)
        layout.addWidget(self.canvas)

        self.render_chart()

    def refresh(self, active_project):
        """Re-targets the chart at a (possibly updated) project and redraws."""
        self.active_project = active_project
        self.render_chart()

    def render_chart(self):
        """Clears and redraws the milestone timeline from the current project state."""
        self.figure.clear()
        ax = self.figure.add_subplot(111)

        milestones = [
            t for t in self.active_project.tasks
            if not t.is_deleted and t.duration_days == 0
        ]

        if not milestones:
            ax.text(
                0.5,
                0.5,
                "No milestones defined.\n(Set a task's duration to 0 days to mark it as a milestone.)",
                ha="center",
                va="center")
            ax.axis("off")
            self.canvas.draw()
            return

        fallback_date = self.active_project.date_created.date()
        milestones = sorted(
            milestones, key=lambda t: t.date_to_be_completed or fallback_date)
        dates = [t.date_to_be_completed or fallback_date for t in milestones]

        ax.plot(dates, [0] * len(dates), color=INK, zorder=1)
        ax.scatter(
            dates,
            [0] * len(dates),
            s=140,
            marker="D",
            color=[
                STATUS_COLOURS.get(t.status, "#9AA0AC") for t in milestones
            ],
            # Overdue milestones get a red ring, matching the
            # Gantt chart's red-outline treatment for overdue bars.
            edgecolors=[RED if t.is_overdue else "none" for t in milestones],
            linewidths=[2.2 if t.is_overdue else 0 for t in milestones],
            zorder=2)

        for date, task in zip(dates, milestones):
            label = ("OVERDUE - " if task.is_overdue else "") + task.title
            ax.annotate(label, (date, 0),
                        textcoords="offset points",
                        xytext=(0, 18),
                        ha="center",
                        fontsize=9)

        ax.get_yaxis().set_visible(False)
        ax.xaxis_date()
        ax.set_title(f"Milestone Chart - {self.active_project.title}")
        self.figure.autofmt_xdate()
        self.canvas.draw()
