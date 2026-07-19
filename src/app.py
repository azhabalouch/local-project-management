import sys
from typing import Optional

from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QLabel, QTabWidget, QComboBox,
                             QPushButton, QMessageBox, QFileDialog, QDialog)

from data import FileManager, Task, Project
from views import ListView, BoardView, EditView
from charts import DependencyCanvas, GanttChartWidget, MilestoneChartWidget
from dialogs import ProjectDialog
from styles import (ENTERPRISE_STYLESHEET, NAVY, SLATE, BLUE, GREEN, RED,
                    BORDER, SURFACE, button_style)
import export_pdf


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
        layout.addWidget(QLabel("<h2>Settings</h2>"))
        layout.addWidget(
            QLabel("Export the active project's monthly plan (with weekly "
                   "plans listed) as a PDF report."))

        self.export_btn = QPushButton("Export Monthly Report (PDF)")
        self.export_btn.setStyleSheet(
            button_style(BLUE, padding="10px 18px") + "max-width: 260px;")
        self.export_btn.clicked.connect(self.export_report)

        layout.addWidget(self.export_btn)
        layout.addStretch()

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

    Owns the project switcher and rebuilds all seven tabs whenever the
    active project changes or the on-disk data is mutated (a save/delete/
    copy from the Edit View).

    Attributes:
        file_manager (FileManager): The system handling local JSON saving.
        all_projects (List[Project]): Every non-deleted project currently
            loaded from Documents/ProjectManagement/.
        active_project (Optional[Project]): The project shown in the
            List, Board, Gantt, Milestone, Critical Path, and Settings tabs.
    """

    def __init__(self, file_manager: FileManager):
        super().__init__()
        self.file_manager = file_manager
        self.all_projects: list = []
        self.active_project: Optional[Project] = None

        self.setWindowTitle("Project Management")
        self.resize(1200, 800)

        # --- Header: brand strip + project switcher ---
        self.project_selector = QComboBox()
        self.project_selector.setStyleSheet("min-width: 240px;")
        self.project_selector.currentIndexChanged.connect(
            self.on_project_selected)

        self.new_project_btn = QPushButton("+ New Project")
        self.new_project_btn.setStyleSheet(button_style(GREEN))
        self.new_project_btn.clicked.connect(self.create_project)

        self.delete_project_btn = QPushButton("Delete Project")
        self.delete_project_btn.setStyleSheet(button_style(RED))
        self.delete_project_btn.clicked.connect(self.delete_active_project)

        top_bar = QWidget()
        top_bar.setStyleSheet(
            f"background-color: {SURFACE}; border-bottom: 1px solid {BORDER};")
        top_bar_layout = QHBoxLayout(top_bar)
        top_bar_layout.setContentsMargins(20, 14, 20, 14)
        top_bar_layout.setSpacing(10)

        top_bar_label = QLabel("Active Project:")
        top_bar_label.setStyleSheet(f"font-weight: 600; color: {SLATE};")
        top_bar_layout.addWidget(top_bar_label)
        top_bar_layout.addWidget(self.project_selector)
        top_bar_layout.addStretch()
        top_bar_layout.addWidget(self.new_project_btn)
        top_bar_layout.addWidget(self.delete_project_btn)

        # --- Tab Navigation ---
        self.tabs = QTabWidget()

        central = QWidget()
        central_layout = QVBoxLayout(central)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(0)
        central_layout.addWidget(top_bar)
        central_layout.addWidget(self.tabs)
        self.setCentralWidget(central)

        self.reload_projects()

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
        """Rebuilds all tabs against the current active_project and all_projects."""
        previous_tab_index = self.tabs.currentIndex()
        self.tabs.clear()

        if self.active_project is None:
            placeholder = QWidget()
            placeholder.setLayout(QVBoxLayout())
            placeholder.layout().addWidget(
                QLabel("No projects found in Documents/ProjectManagement."))
            self.tabs.addTab(placeholder, "No Data")
            return

        self.list_view = ListView(self.active_project)
        self.board_view = BoardView(self.active_project, self.file_manager,
                                    self.reload_projects)
        self.edit_view = EditView(self.all_projects, self.file_manager,
                                  self.reload_projects)
        self.gantt_view = GanttChartWidget(self.active_project)
        self.milestone_view = MilestoneChartWidget(self.active_project)
        self.cpm_view = DependencyCanvas(self.active_project)
        self.settings_view = SettingsView(self.active_project)

        self.tabs.addTab(self.list_view, "List View")
        self.tabs.addTab(self.board_view, "Board View")
        self.tabs.addTab(self.edit_view, "Edit View")
        self.tabs.addTab(self.gantt_view, "Gantt Chart")
        self.tabs.addTab(self.milestone_view, "Milestone Chart")
        self.tabs.addTab(self.cpm_view, "Critical Path")
        self.tabs.addTab(self.settings_view, "Settings")

        # Rebuilding tabs (e.g. after a drag-drop status change, an edit,
        # or a reload) otherwise silently snaps the view back to "List
        # View" every time, since QTabWidget.clear() resets the current
        # index to 0. Restore whichever tab the user was actually on.
        if 0 <= previous_tab_index < self.tabs.count():
            self.tabs.setCurrentIndex(previous_tab_index)


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
