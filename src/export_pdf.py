"""
PDF export for the Settings tab.

Produces a report grouped by month (the "monthly plan"), with each month
broken down into its constituent ISO weeks (the "weekly plans") as
requested in the brief - reusing the same grouping logic as the List View
so the report matches what the user sees on screen.
"""
import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                                TableStyle)

from data import Project


def _group_by_month_then_week(project: Project):
    """
    Groups the project's active tasks by month, and each month's tasks by
    ISO week, mirroring ListView's monthly/weekly logic so the exported
    report matches the on-screen breakdown.

    Returns:
        dict: {month_label: {week_label: [Task, ...]}}, plus a separate
              list of unscheduled tasks.
    """
    months: dict = {}
    unscheduled = []

    for task in project.tasks:
        if task.is_deleted:
            continue
        if not task.date_to_be_completed:
            unscheduled.append(task)
            continue

        month_label = task.date_to_be_completed.strftime("%B %Y")
        year, week, _ = task.date_to_be_completed.isocalendar()
        week_label = f"Week {week}, {year}"

        months.setdefault(month_label, {}).setdefault(week_label,
                                                       []).append(task)

    return months, unscheduled


def generate_monthly_report(project: Project, save_path: str) -> None:
    """
    Writes a PDF report for the given project to save_path: the monthly
    plan, with each month's weekly plans listed underneath it.

    Args:
        project: The Project to report on.
        save_path: Destination file path, chosen by the user via the
            Settings tab's file dialog.
    """
    styles = getSampleStyleSheet()
    month_style = ParagraphStyle("MonthHeading",
                                 parent=styles["Heading2"],
                                 textColor=colors.HexColor("#0052CC"),
                                 spaceBefore=14)
    week_style = ParagraphStyle("WeekHeading",
                                parent=styles["Heading3"],
                                textColor=colors.HexColor("#172B4D"),
                                spaceBefore=8)

    doc = SimpleDocTemplate(save_path,
                            pagesize=A4,
                            topMargin=2 * cm,
                            bottomMargin=2 * cm)
    story = [
        Paragraph(f"Project Report: {project.title}", styles["Title"]),
        Paragraph(
            f"Subject: {project.subject} &nbsp;|&nbsp; Progress: {project.progress:.0f}% "
            f"&nbsp;|&nbsp; Generated: {datetime.date.today().isoformat()}",
            styles["Normal"]),
        Spacer(1, 0.6 * cm),
    ]

    months, unscheduled = _group_by_month_then_week(project)

    if not months and not unscheduled:
        story.append(Paragraph("No tasks recorded for this project.",
                               styles["Normal"]))

    for month_label, weeks in months.items():
        story.append(Paragraph(month_label, month_style))

        for week_label, tasks in weeks.items():
            story.append(Paragraph(week_label, week_style))

            table_data = [["Task", "Status", "Priority", "Deadline"]]
            for task in tasks:
                table_data.append([
                    task.title, task.status, task.priority,
                    task.date_to_be_completed.isoformat()
                ])

            table = Table(table_data,
                          colWidths=[6.5 * cm, 3 * cm, 3 * cm, 3.5 * cm])
            table.setStyle(
                TableStyle([
                    ("BACKGROUND", (0, 0), (-1, 0),
                     colors.HexColor("#E0E0E0")),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CCCCCC")),
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1),
                     [colors.white, colors.HexColor("#F4F5F7")]),
                ]))
            story.append(table)
            story.append(Spacer(1, 0.3 * cm))

    if unscheduled:
        story.append(Paragraph("Unscheduled", month_style))
        table_data = [["Task", "Status", "Priority"]]
        for task in unscheduled:
            table_data.append([task.title, task.status, task.priority])
        table = Table(table_data, colWidths=[7 * cm, 4 * cm, 4 * cm])
        table.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E0E0E0")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CCCCCC")),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
            ]))
        story.append(table)

    doc.build(story)
