import sys
from typing import Optional

from PyQt6.QtCore import Qt, QSize
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QLabel, QTabWidget, QComboBox,
                             QPushButton, QMessageBox, QFileDialog, QDialog,
                             QDialogButtonBox)

from data import FileManager, Task, Project
from views import ListView, BoardView, EditView, TrashView
from charts import DependencyCanvas, GanttChartWidget, MilestoneChartWidget
from dialogs import ProjectDialog
from plan_view import PlanView
from sketch_view import SketchView
from styles import (ENTERPRISE_STYLESHEET, INK, MUTED, ACCENT, SUCCESS, RED,
                    BORDER, SURFACE, ACCENT_SOFT, button_style, ghost_button_style,
                    hint_style, apply_shadow, SPACE_SM, SPACE_MD, SPACE_LG,
                    RADIUS_MD)
from icons import icon, tab_icon
from animations import fade_in
import export_pdf


# Per-tab, plain-language reminders shown in the thin hint bar just under
# the header. Written for someone who has never used a project-management
# tool before - what am I looking at, and what's the one thing I can do
# here?
TAB_HINTS = {
    "List View": ("See every task grouped by week or month. Use the search "
                 "box and dropdowns above the list to narrow things down, "
                 "or right-click a task to change its status."),
    "Plan": ("Write out the plan for this project like a Word document - "
            "bold, italic, and lists all work. Tick off items in the "
            "checklist below as the plan comes together. Saves as you go."),
    "Sketch": ("Pick a tool from the toolbar and draw - freehand pen, "
              "rectangles, ellipses, or sticky notes. Ctrl+scroll to "
              "zoom, drag to move things around with Select."),
    "Board View": ("Drag a card into a different column to update its "
                   "status. Click the + at the top of a column to add a "
                   "task straight into it."),
    "Edit View": ("Tick the checkboxes next to any Project, Task, or "
                  "To-do, then use the buttons below to delete or copy "
                  "them. Nothing is lost forever - deleted items go to "
                  "the Trash tab."),
    "Gantt Chart": ("A timeline of every task with a deadline. Longer bars "
                    "mean more days scheduled - this is a read-only "
                    "overview."),
    "Milestone Chart": ("Milestones are tasks with 0 days of duration - "
                        "the big flags in your plan. This chart lines "
                        "them up in order."),
    "Critical Path": ("Drag tasks around to map how they depend on each "
                      "other, then click 'Calculate Critical Path' to see "
                      "the sequence that controls your finish date."),
    "Settings": ("Export a print-ready PDF summary of this project to "
                "share in a meeting."),
    "Trash": ("Anything you've deleted lives here. Select it and click "
             "Restore to bring it back, or Permanently Delete to remove "
             "it for good."),
    "No Data": ("Click '+ New Project' above to get started - it only "
               "takes a few seconds."),
}


class WelcomeDialog(QDialog):
    """
    A one-time, plain-language tour shown the very first time the app is
    opened (see MainWindow._maybe_show_welcome). Never shown again once
    dismissed, so returning users aren't interrupted.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Welcome to Project Management")
        self.setMinimumWidth(480)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 28, 30, 26)
        layout.setSpacing(SPACE_MD)

        header = QLabel(
            "<span style='font-size:20px; font-weight:700;'>Welcome</span>")
        layout.addWidget(header)
        subtitle = QLabel(
            "This app helps you plan a project and track its tasks. "
            "Here's everything you need to know to get going.")
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet(f"color: {MUTED};")
        layout.addWidget(subtitle)
        layout.addSpacing(4)

        points = [
            ("new_project", "<b>Projects</b> are the big picture - like "
                          "\u201cMove to a new office\u201d or \u201cLaunch "
                          "website\u201d."),
            ("checklist", "<b>Tasks</b> are the steps inside a project. Add "
                      "them from the List or Board tab."),
            ("board_view", "<b>Board View</b> lets you drag tasks "
                                 "between Not Started, In Progress, On "
                                 "Hold, and Completed."),
            ("trash", "Deleting something never loses it for "
                                 "good - everything can be brought back "
                                 "from the <b>Trash</b> tab."),
        ]
        for icon_key, text in points:
            row = QHBoxLayout()
            row.setSpacing(SPACE_MD)
            icon_label = QLabel()
            icon_label.setPixmap(icon(icon_key, color=ACCENT).pixmap(20, 20))
            icon_label.setFixedWidth(24)
            text_label = QLabel(text)
            text_label.setWordWrap(True)
            row.addWidget(icon_label, alignment=Qt.AlignmentFlag.AlignTop)
            row.addWidget(text_label, stretch=1)
            layout.addLayout(row)

        layout.addSpacing(6)
        tip = QLabel(
            "Tip: hover over any button or field in the app for a short "
            "explanation.")
        tip.setWordWrap(True)
        tip.setStyleSheet(f"color: {MUTED}; font-style: italic; font-size: 12px;")
        layout.addWidget(tip)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        buttons.accepted.connect(self.accept)
        ok_btn = buttons.button(QDialogButtonBox.StandardButton.Ok)
        ok_btn.setText("Get Started")
        ok_btn.setStyleSheet(button_style(ACCENT, padding="9px 20px"))
        layout.addWidget(buttons)
        fade_in(self, duration=200)


class SettingsView(QWidget):
    """
    Application settings. Currently hosts the data-export function: a PDF
    report of the active project's monthly plan, with each month's weekly
    plans listed beneath it, for use in business-meeting reporting.
    """

    def __init__(self, active_project):
        super().__init__()
        self.active_project = active_project

        layout = QVBoxLayout(self)
        layout.setContentsMargins(SPACE_LG, SPACE_LG, SPACE_LG, SPACE_LG)
        layout.setSpacing(SPACE_MD)

        heading = QLabel("Settings")
        heading.setProperty("role", "heading")
        layout.addWidget(heading)
        subtitle = QLabel("Export the active project's monthly plan (with "
                          "weekly plans listed) as a PDF report.")
        subtitle.setStyleSheet(f"color: {MUTED};")
        layout.addWidget(subtitle)
        layout.addSpacing(6)

        self.export_btn = QPushButton("Export Monthly Report (PDF)")
        self.export_btn.setIcon(icon("export_pdf", color="white"))
        self.export_btn.setStyleSheet(
            button_style(ACCENT, padding="11px 20px") + "max-width: 300px;")
        self.export_btn.setToolTip(
            "Creates a PDF you can print or attach to an email, listing "
            "every task month-by-month and week-by-week.")
        self.export_btn.clicked.connect(self.export_report)

        layout.addWidget(self.export_btn)
        layout.addStretch()

    def refresh(self, active_project):
        """Re-targets this tab at a (possibly updated) project."""
        self.active_project = active_project

    def export_report(self):
        """Prompts for a save location, then writes the PDF report to it."""
        default_name = f"{self.active_project.title} Report.pdf"
        save_path, _ = QFileDialog.getSaveFileName(self,
                                                   "Export Monthly Report",
                                                   default_name,
                                                   "PDF Files (*.pdf)")
        if not save_path:
            return

        try:
            export_pdf.generate_monthly_report(self.active_project, save_path)
            QMessageBox.information(self, "Export Complete",
                                    f"Report saved to:\n{save_path}")
        except Exception as exc:
            QMessageBox.critical(self, "Export Failed",
                                 f"Could not write the PDF report:\n{exc}")


class MainWindow(QMainWindow):
    """
    The core application window.

    Owns the project switcher and keeps all ten tabs (List, Plan, Board,
    Edit, Gantt, Milestone, Critical Path, Settings, Trash, and Sketch) in
    sync whenever the active project changes or the on-disk data is
    mutated (a save/delete/copy from the Edit View, or a restore from the
    Trash).

    Tabs are only torn down and rebuilt from scratch when the tab *set*
    itself needs to change (switching between having no projects at all
    and having an active one); otherwise each tab widget is updated in
    place via its own refresh() method - see init_views().

    Attributes:
        file_manager (FileManager): The system handling local JSON saving.
        all_projects (List[Project]): Every non-deleted project currently
            loaded from Documents/ProjectManagement/.
        all_projects_with_deleted (List[Project]): Every project regardless
            of its own is_deleted flag, used only by the Trash tab.
        active_project (Optional[Project]): The project shown in the
            List, Board, Gantt, Milestone, Critical Path, and Settings tabs.
    """

    def __init__(self, file_manager: FileManager):
        super().__init__()
        self.file_manager = file_manager
        self.all_projects: list = []
        self.all_projects_with_deleted: list = []
        self.active_project: Optional[Project] = None

        # None until the first init_views() call; afterwards tracks
        # whether the tab set currently reflects "has an active project"
        # or "no projects at all", so init_views() knows whether it can
        # refresh the existing tab widgets in place or needs a full
        # rebuild. See init_views()'s docstring.
        self._last_has_project: Optional[bool] = None

        self.setWindowTitle("Project Management")
        self.resize(1280, 820)

        # --- Header: brand strip + project switcher ---
        brand_label = QLabel("Projects")
        brand_label.setStyleSheet(
            f"font-size: 16px; font-weight: 800; color: {INK}; "
            f"letter-spacing: -0.3px;")

        self.project_selector = QComboBox()
        self.project_selector.setStyleSheet("min-width: 240px;")
        self.project_selector.setToolTip(
            "Switch between your projects. Whichever one is picked here "
            "is what every tab (List, Board, Gantt, ...) shows.")
        self.project_selector.currentIndexChanged.connect(
            self.on_project_selected)

        self.new_project_btn = QPushButton("New Project")
        self.new_project_btn.setIcon(icon("new_project", color="white"))
        self.new_project_btn.setStyleSheet(button_style(SUCCESS))
        self.new_project_btn.setToolTip(
            "Start a brand-new project. You'll be asked for a title and a "
            "short description, then you can start adding tasks.")
        self.new_project_btn.clicked.connect(self.create_project)

        self.delete_project_btn = QPushButton("Delete Project")
        self.delete_project_btn.setIcon(icon("delete", color=RED))
        self.delete_project_btn.setStyleSheet(ghost_button_style(RED))
        self.delete_project_btn.setToolTip(
            "Moves the current project to the Trash tab, where it can "
            "still be restored later.")
        self.delete_project_btn.clicked.connect(self.delete_active_project)

        top_bar = QWidget()
        top_bar.setStyleSheet(
            f"background-color: {SURFACE}; border-bottom: 1px solid {BORDER};")
        top_bar_layout = QHBoxLayout(top_bar)
        top_bar_layout.setContentsMargins(SPACE_LG, SPACE_MD, SPACE_LG, SPACE_MD)
        top_bar_layout.setSpacing(SPACE_MD)

        top_bar_layout.addWidget(brand_label)
        divider = QLabel()
        divider.setFixedWidth(1)
        divider.setStyleSheet(f"background-color: {BORDER};")
        divider.setFixedHeight(22)
        top_bar_layout.addWidget(divider)
        top_bar_label = QLabel("Active project")
        top_bar_label.setStyleSheet(f"font-weight: 600; color: {MUTED};")
        top_bar_layout.addWidget(top_bar_label)
        top_bar_layout.addWidget(self.project_selector)
        top_bar_layout.addStretch()
#        top_bar_layout.addWidget(self.delete_project_btn)
        top_bar_layout.addWidget(self.new_project_btn)
        apply_shadow(top_bar, blur=18, y_offset=3, alpha=18)

        # --- Tab Navigation ---
        self.tabs = QTabWidget()
        self.tabs.setIconSize(QSize(15, 15))
        self.tabs.currentChanged.connect(self._update_hint_bar)

        # A thin, ever-present "what am I looking at" strip so a first-
        # time user is never stuck guessing what a tab is for.
        self.hint_bar = QWidget()
        self.hint_bar.setStyleSheet(
            f"background-color: {ACCENT_SOFT}; "
            f"border-bottom: 1px solid {BORDER};")
        hint_bar_layout = QHBoxLayout(self.hint_bar)
        hint_bar_layout.setContentsMargins(SPACE_LG, SPACE_SM, SPACE_LG, SPACE_SM)
        hint_bar_layout.setSpacing(SPACE_SM)
        self.hint_icon_label = QLabel()
        self.hint_icon_label.setPixmap(icon("hint", color=ACCENT).pixmap(15, 15))
        self.hint_text_label = QLabel()
        self.hint_text_label.setWordWrap(True)
        self.hint_text_label.setStyleSheet(
            f"color: {INK}; font-size: 12px; background: transparent;")
        hint_bar_layout.addWidget(self.hint_icon_label,
                                  alignment=Qt.AlignmentFlag.AlignTop)
        hint_bar_layout.addWidget(self.hint_text_label, stretch=1)

        central = QWidget()
        central_layout = QVBoxLayout(central)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(0)
        central_layout.addWidget(top_bar)
        central_layout.addWidget(self.hint_bar)
        central_layout.addWidget(self.tabs)
        self.setCentralWidget(central)

        self.reload_projects()
        self._maybe_show_welcome()

    def _update_hint_bar(self, index: int = 0):
        """Refreshes the hint strip to match whichever tab is now active,
        with a soft fade so the change doesn't just pop."""
        if not (0 <= index < self.tabs.count()):
            self.hint_text_label.setText("")
            return
        tab_label = self.tabs.tabText(index)
        self.hint_text_label.setText(TAB_HINTS.get(tab_label, ""))
        fade_in(self.hint_text_label, duration=160)

    def _maybe_show_welcome(self):
        """
        Shows the one-time WelcomeDialog the very first time the app is
        launched (tracked with a small marker file next to the project
        JSON files), then never again.
        """
        marker = self.file_manager.storage_dir / ".welcomed"
        if marker.exists():
            return
        WelcomeDialog(self).exec()
        try:
            marker.touch()
        except OSError:
            pass

    def reload_projects(self, select_title: Optional[str] = None):
        """
        Re-reads every project from disk, repopulates the project switcher
        (keeping the current selection where possible), and rebuilds the
        tabs. Passed into EditView and BoardView as their on_change
        callback so an add/edit/delete/copy there is immediately reflected
        everywhere else.

        Args:
            select_title: If given, selects the project with this title
                instead of trying to keep the previous selection - used
                right after creating a brand-new project.
        """
        previous_title = self.active_project.title if self.active_project else None
        target_title = select_title if select_title else previous_title

        self.all_projects = self.file_manager.load_all_projects()
        self.all_projects_with_deleted = self.file_manager.load_all_projects(
            include_deleted=True)

        self.project_selector.blockSignals(True)
        self.project_selector.clear()
        for project in self.all_projects:
            self.project_selector.addItem(project.title, userData=project)

        if not self.all_projects:
            self.active_project = None
        else:
            index = 0
            if target_title:
                for i, project in enumerate(self.all_projects):
                    if project.title == target_title:
                        index = i
                        break
            self.project_selector.setCurrentIndex(index)
            self.active_project = self.all_projects[index]
        self.project_selector.blockSignals(False)
        self.delete_project_btn.setEnabled(self.active_project is not None)

        self.init_views()

    def create_project(self):
        """Opens the New Project dialog and switches to it once saved."""
        dialog = ProjectDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        new_project = dialog.get_project()
        self.file_manager.save_project(new_project)
        self.reload_projects(select_title=new_project.title)

    def delete_active_project(self):
        """
        Soft-deletes the currently active project (after confirmation) and
        persists the change, then reloads the switcher so the deleted
        project drops out of it and another project (if any remain) takes
        its place as active.
        """
        if self.active_project is None:
            return

        confirm = QMessageBox.question(
            self, "Delete Project",
            f"Delete '{self.active_project.title}'? This removes it (and "
            f"all its tasks) from every view. This cannot be undone from "
            f"the app.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if confirm != QMessageBox.StandardButton.Yes:
            return

        self.active_project.is_deleted = True
        self.file_manager.save_project(self.active_project)
        self.reload_projects()

    def on_project_selected(self, index: int):
        """Switches the active project when a different entry is picked."""
        if index < 0:
            return
        self.active_project = self.project_selector.itemData(index)
        self.delete_project_btn.setEnabled(self.active_project is not None)
        self.init_views()

    def init_views(self):
        """
        Brings every tab up to date with the current active_project,
        all_projects, and all_projects_with_deleted.

        Only rebuilds the tab set from scratch when it actually has to -
        i.e. transitioning between "no projects at all" (a placeholder
        tab) and "has an active project" (the full set of working tabs).
        Any other change (a different project selected, a task edited
        anywhere, a Trash restore, ...) instead updates the existing tab
        widgets in place via _refresh_tabs(), which avoids the flicker/lag
        of tearing down and recreating matplotlib figures and Qt widgets
        on every small change.
        """
        previous_tab_index = self.tabs.currentIndex()
        has_project = self.active_project is not None
        needs_rebuild = (self._last_has_project is None
                         or self._last_has_project != has_project)

        if needs_rebuild:
            self._rebuild_tabs(has_project)
        else:
            self._refresh_tabs(has_project)

        self._last_has_project = has_project

        # A full rebuild resets QTabWidget's current index to 0 (clear()
        # does this). Restore whichever tab the user was actually on.
        if 0 <= previous_tab_index < self.tabs.count():
            self.tabs.setCurrentIndex(previous_tab_index)

    def _rebuild_tabs(self, has_project: bool):
        """Tears down and recreates every tab widget from scratch."""
        self.tabs.clear()

        if not has_project:
            placeholder = QWidget()
            placeholder_layout = QVBoxLayout(placeholder)
            placeholder_layout.addStretch()
            big_icon = QLabel()
            big_icon.setPixmap(icon("no_data", color=MUTED).pixmap(56, 56))
            big_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
            placeholder_layout.addWidget(big_icon)
            placeholder_layout.addSpacing(SPACE_MD)
            heading = QLabel("No projects yet")
            heading.setProperty("role", "heading")
            heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
            placeholder_layout.addWidget(heading)
            message = QLabel(
                "Click <b>New Project</b> above to create your first one - "
                "it only takes a few seconds.")
            message.setStyleSheet(f"color: {MUTED};")
            message.setAlignment(Qt.AlignmentFlag.AlignCenter)
            placeholder_layout.addWidget(message)
            placeholder_layout.addStretch()
            self.tabs.addTab(placeholder, tab_icon("No Data"), "No Data")
            (self.list_view, self.plan_view, self.board_view, self.edit_view,
             self.gantt_view, self.milestone_view, self.cpm_view,
             self.settings_view, self.sketch_view) = (None, ) * 9
        else:
            self.list_view = ListView(self.active_project, self.file_manager,
                                      self.reload_projects)
            self.plan_view = PlanView(self.active_project, self.file_manager)
            self.board_view = BoardView(self.active_project, self.file_manager,
                                        self.reload_projects)
            self.edit_view = EditView(self.all_projects, self.file_manager,
                                      self.reload_projects)
            self.gantt_view = GanttChartWidget(self.active_project)
            self.milestone_view = MilestoneChartWidget(self.active_project)
            self.cpm_view = DependencyCanvas(self.active_project,
                                             self.file_manager)
            self.settings_view = SettingsView(self.active_project)
            self.sketch_view = SketchView(self.active_project, self.file_manager)

            self.tabs.addTab(self.list_view, tab_icon("List View"), "List View")
            self.tabs.addTab(self.board_view, tab_icon("Board View"), "Board View")
            # Plan sits right after List View (2nd tab overall) - writing
            # up the plan is naturally the next thing to do once you can
            # see the tasks laid out.
            self.tabs.addTab(self.plan_view, tab_icon("Plan"), "Plan")
            self.tabs.addTab(self.sketch_view, tab_icon("Sketch"), "Sketch")
            self.tabs.addTab(self.edit_view, tab_icon("Edit View"), "Edit View")
            self.tabs.addTab(self.gantt_view, tab_icon("Gantt Chart"), "Gantt Chart")
            self.tabs.addTab(self.milestone_view, tab_icon("Milestone Chart"),
                             "Milestone Chart")
            self.tabs.addTab(self.cpm_view, tab_icon("Critical Path"),
                             "Critical Path")
            self.tabs.addTab(self.settings_view, tab_icon("Settings"), "Settings")

        # Always present, in either state, so a fully-emptied project
        # list can still be recovered from.
        self.trash_view = TrashView(self.all_projects_with_deleted,
                                    self.file_manager, self.reload_projects)
        self.tabs.addTab(self.trash_view, tab_icon("Trash"), "Trash")       
        self._update_hint_bar(self.tabs.currentIndex())

    def _refresh_tabs(self, has_project: bool):
        """Updates the already-built tab widgets in place."""
        if has_project:
            self.list_view.refresh(self.active_project)
            self.plan_view.refresh(self.active_project)
            self.board_view.refresh(self.active_project)
            self.edit_view.refresh(self.all_projects)
            self.gantt_view.refresh(self.active_project)
            self.milestone_view.refresh(self.active_project)
            self.cpm_view.refresh(self.active_project)
            self.settings_view.refresh(self.active_project)
            self.sketch_view.refresh(self.active_project)

        self.trash_view.refresh(self.all_projects_with_deleted)


# ==========================================
# Main Execution Loop & Initialization
# ==========================================
if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(ENTERPRISE_STYLESHEET)

    # 1. Initialize the backend storage system
    file_manager = FileManager()

    # 2. Seed a demo project on first run only, so the switcher and every
    #    tab have data to display before the user creates their own.
    if not file_manager.load_all_projects():
        demo_project = Project("Alpha Build", "Internal Development",
                               "Testing the full tab suite integration.")

        task1 = Task("Design Database Schema",
                     "Plan JSON file structure",
                     duration_days=3)
        task2 = Task("Setup PyQt6 Environment",
                     "Install and configure UI",
                     duration_days=2)
        task2.status = "In Progress"
        task2.add_dependency(task1.title)

        demo_project.add_task(task1)
        demo_project.add_task(task2)

        file_manager.save_project(demo_project)

    # 3. Launch the application window
    window = MainWindow(file_manager)
    window.show()

    sys.exit(app.exec())
