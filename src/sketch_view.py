"""
The Sketch tab: a small Miro-style board for freehand diagrams - pen
strokes, rectangles, ellipses, and sticky notes that can be dragged
around a pannable/zoomable canvas.

Kept as its own module (mirroring charts.py's DependencyCanvas, which is
the other hand-rolled QGraphicsView in this app) since the drawing/tool
state machine is a distinct concern from the tree/list-based tabs in
views.py.

Persistence: the board is serialized to a plain JSON list of shape dicts
and stored on Project.sketch_data (see data.py), so it round-trips through
FileManager exactly like every other part of a project.
"""
import json
from typing import Optional

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                             QPushButton, QGraphicsView, QGraphicsScene,
                             QGraphicsItem, QGraphicsPathItem,
                             QGraphicsRectItem, QGraphicsEllipseItem,
                             QGraphicsTextItem, QColorDialog, QMessageBox,
                             QButtonGroup, QFrame)
from PyQt6.QtCore import Qt, QPointF, QRectF
from PyQt6.QtGui import QPainterPath, QPen, QBrush, QColor, QPainter

from data import FileManager
from styles import (INK, MUTED, BORDER, SURFACE, BACKGROUND, ACCENT,
                    SUCCESS, DANGER, WARNING, SPACE_SM, SPACE_MD, SPACE_LG)
from icons import icon
from widgets import hint_row

# The palette offered on the Sketch toolbar - a handful of the app's own
# design-system colours plus a "custom" swatch, rather than a full colour
# wheel, so the board's look stays consistent with the rest of the app.
PALETTE = [INK, ACCENT, SUCCESS, DANGER, WARNING]

PEN_WIDTH = 3
NOTE_DEFAULT_TEXT = "Note"
NOTE_WIDTH = 160


class StickyNoteItem(QGraphicsTextItem):
    """An editable, movable sticky note with a coloured card behind the
    text (QGraphicsTextItem has no background of its own, so this paints
    one before deferring to the base class for the text itself)."""

    def __init__(self, text: str, color: str):
        super().__init__(text)
        self.note_color = color
        self.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextEditorInteraction)
        self.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsMovable |
                     QGraphicsItem.GraphicsItemFlag.ItemIsSelectable |
                     QGraphicsItem.GraphicsItemFlag.ItemIsFocusable)
        self.setDefaultTextColor(QColor(INK))
        self.setTextWidth(NOTE_WIDTH)
        self.setZValue(1)

    def paint(self, painter: QPainter, option, widget=None):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QBrush(QColor(self.note_color)))
        painter.setPen(QPen(QColor(BORDER), 1))
        rect = self.boundingRect().adjusted(0, 0, -1, -1)
        painter.drawRoundedRect(rect, 8, 8)
        super().paint(painter, option, widget)


class SketchCanvas(QGraphicsView):
    """
    The drawing surface itself: a QGraphicsScene wrapped in a QGraphicsView
    that switches its mouse-event behaviour based on the currently active
    tool (select / pen / rectangle / ellipse / note / eraser).

    Attributes:
        tool (str): One of "select", "pen", "rectangle", "ellipse", "note",
            "eraser".
        current_color (str): Hex colour used for the next stroke/shape/note.
        on_change (callable): Invoked after any edit that should be
            persisted (stroke finished, shape finished, note added/edited,
            item erased, board cleared).
    """

    def __init__(self, on_change):
        self.scene_obj = QGraphicsScene(-2000, -2000, 4000, 4000)
        super().__init__(self.scene_obj)
        self.on_change = on_change
        self.tool = "select"
        self.current_color = ACCENT
        self._drawing_item: Optional[QGraphicsItem] = None
        self._draw_start: Optional[QPointF] = None
        self._path: Optional[QPainterPath] = None

        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setBackgroundBrush(QBrush(QColor(BACKGROUND)))
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setMinimumHeight(420)

    # --- Tool switching -------------------------------------------------

    def set_tool(self, tool: str):
        self.tool = tool
        movable_tool = tool == "select"
        for item in self.scene_obj.items():
            flags = item.flags()
            if movable_tool:
                item.setFlags(flags | QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
            else:
                item.setFlags(flags & ~QGraphicsItem.GraphicsItemFlag.ItemIsMovable)

    # --- Mouse handling --------------------------------------------------

    def mousePressEvent(self, event):
        pos = self.mapToScene(event.pos())
        if self.tool == "select":
            super().mousePressEvent(event)
            return
        if self.tool == "pen":
            self._path = QPainterPath(pos)
            item = QGraphicsPathItem(self._path)
            item.setPen(QPen(QColor(self.current_color), PEN_WIDTH,
                             Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                             Qt.PenJoinStyle.RoundJoin))
            item.setData(0, "path")
            item.setData(1, self.current_color)
            self.scene_obj.addItem(item)
            self._drawing_item = item
        elif self.tool in ("rectangle", "ellipse"):
            self._draw_start = pos
            cls = QGraphicsRectItem if self.tool == "rectangle" else QGraphicsEllipseItem
            item = cls(QRectF(pos, pos))
            item.setPen(QPen(QColor(self.current_color), PEN_WIDTH))
            item.setData(0, self.tool)
            item.setData(1, self.current_color)
            self.scene_obj.addItem(item)
            self._drawing_item = item
        elif self.tool == "note":
            note = StickyNoteItem(NOTE_DEFAULT_TEXT, self.current_color)
            note.setPos(pos)
            self.scene_obj.addItem(note)
            note.setFocus()
            cursor = note.textCursor()
            cursor.select(cursor.SelectionType.Document)
            note.setTextCursor(cursor)
            self.on_change()
        elif self.tool == "eraser":
            item = self.itemAt(event.pos())
            if item is not None:
                self.scene_obj.removeItem(item)
                self.on_change()

    def mouseMoveEvent(self, event):
        pos = self.mapToScene(event.pos())
        if self.tool == "select":
            super().mouseMoveEvent(event)
            return
        if self.tool == "pen" and self._drawing_item is not None:
            self._path.lineTo(pos)
            self._drawing_item.setPath(self._path)
        elif self.tool in ("rectangle", "ellipse") and self._drawing_item is not None:
            rect = QRectF(self._draw_start, pos).normalized()
            self._drawing_item.setRect(rect)
        elif self.tool == "eraser" and event.buttons() & Qt.MouseButton.LeftButton:
            item = self.itemAt(event.pos())
            if item is not None:
                self.scene_obj.removeItem(item)

    def mouseReleaseEvent(self, event):
        if self.tool == "select":
            super().mouseReleaseEvent(event)
            return
        if self._drawing_item is not None:
            self._drawing_item = None
            self._path = None
            self._draw_start = None
            self.on_change()
        elif self.tool == "eraser":
            self.on_change()

    def wheelEvent(self, event):
        """Ctrl+scroll zooms; a plain scroll pans, matching common
        whiteboard-tool conventions."""
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
            self.scale(factor, factor)
        else:
            super().wheelEvent(event)

    # --- Serialization ---------------------------------------------------

    def to_shapes(self) -> list:
        """Converts every item currently on the scene into a plain dict,
        suitable for json.dumps and later reconstruction via
        load_shapes()."""
        shapes = []
        for item in self.scene_obj.items():
            kind = item.data(0)
            if kind == "path":
                path = item.path()
                points = [[path.elementAt(i).x, path.elementAt(i).y]
                         for i in range(path.elementCount())]
                shapes.append({
                    "type": "path",
                    "points": points,
                    "color": item.data(1)
                })
            elif kind in ("rectangle", "ellipse"):
                rect = item.rect()
                shapes.append({
                    "type": kind,
                    "x": rect.x(),
                    "y": rect.y(),
                    "w": rect.width(),
                    "h": rect.height(),
                    "color": item.data(1),
                    "pos_x": item.pos().x(),
                    "pos_y": item.pos().y(),
                })
            elif isinstance(item, StickyNoteItem):
                pos = item.pos()
                shapes.append({
                    "type": "note",
                    "x": pos.x(),
                    "y": pos.y(),
                    "color": item.note_color,
                    "text": item.toPlainText(),
                })
        return shapes

    def load_shapes(self, shapes: list):
        """Clears the scene and rebuilds it from a list of shape dicts
        previously produced by to_shapes()."""
        self.scene_obj.clear()
        for shape in shapes:
            kind = shape.get("type")
            color = shape.get("color", ACCENT)
            if kind == "path":
                points = shape.get("points", [])
                if not points:
                    continue
                path = QPainterPath(QPointF(*points[0]))
                for x, y in points[1:]:
                    path.lineTo(QPointF(x, y))
                item = QGraphicsPathItem(path)
                item.setPen(QPen(QColor(color), PEN_WIDTH,
                                 Qt.PenStyle.SolidLine,
                                 Qt.PenCapStyle.RoundCap,
                                 Qt.PenJoinStyle.RoundJoin))
                item.setData(0, "path")
                item.setData(1, color)
                item.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsMovable |
                             QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
                self.scene_obj.addItem(item)
            elif kind in ("rectangle", "ellipse"):
                rect = QRectF(shape.get("x", 0), shape.get("y", 0),
                              shape.get("w", 80), shape.get("h", 80))
                cls = QGraphicsRectItem if kind == "rectangle" else QGraphicsEllipseItem
                item = cls(rect)
                item.setPen(QPen(QColor(color), PEN_WIDTH))
                item.setData(0, kind)
                item.setData(1, color)
                item.setPos(shape.get("pos_x", 0), shape.get("pos_y", 0))
                item.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsMovable |
                             QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
                self.scene_obj.addItem(item)
            elif kind == "note":
                note = StickyNoteItem(shape.get("text", NOTE_DEFAULT_TEXT),
                                      color)
                note.setPos(shape.get("x", 0), shape.get("y", 0))
                self.scene_obj.addItem(note)
        self.set_tool(self.tool)


class SketchView(QWidget):
    """
    The Sketch tab widget: a toolbar (tools, colours, zoom, clear) plus
    the SketchCanvas itself. Every completed action (a finished stroke or
    shape, a new/edited note, an erase, a clear) autosaves to the active
    project immediately - there is no separate save step.
    """

    def __init__(self, active_project, file_manager: FileManager):
        super().__init__()
        self.active_project = active_project
        self.file_manager = file_manager

        layout = QVBoxLayout(self)
        layout.setContentsMargins(SPACE_LG, SPACE_LG, SPACE_LG, SPACE_LG)
        layout.setSpacing(SPACE_SM)

        heading = QLabel("Sketch")
        heading.setProperty("role", "heading")
        layout.addWidget(heading)
        layout.addWidget(hint_row(
            "Pick a tool, then draw on the board below. Ctrl+scroll to "
            "zoom, drag with Select to move things around. Everything "
            "here saves automatically."))

        self.canvas = SketchCanvas(on_change=self._save_board)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(SPACE_SM)

        self.tool_group = QButtonGroup(self)
        self.tool_group.setExclusive(True)
        self.tool_buttons = {}
        for key, icon_key, tooltip in [
            ("select", "tool_select", "Select & move"),
            ("pen", "tool_pen", "Freehand pen"),
            ("rectangle", "tool_rectangle", "Rectangle"),
            ("ellipse", "tool_ellipse", "Ellipse"),
            ("note", "tool_note", "Sticky note"),
            ("eraser", "tool_eraser", "Eraser"),
        ]:
            btn = QPushButton()
            btn.setIcon(icon(icon_key, color=MUTED))
            btn.setToolTip(tooltip)
            btn.setCheckable(True)
            btn.setFixedWidth(36)
            btn.clicked.connect(lambda _checked, k=key: self._select_tool(k))
            self.tool_group.addButton(btn)
            self.tool_buttons[key] = btn
            toolbar.addWidget(btn)
        self.tool_buttons["select"].setChecked(True)

        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.VLine)
        divider.setStyleSheet(f"color: {BORDER};")
        toolbar.addWidget(divider)

        self.color_buttons = []
        for color in PALETTE:
            swatch = QPushButton()
            swatch.setFixedSize(24, 24)
            swatch.setToolTip("Set drawing colour")
            swatch.setStyleSheet(
                f"background-color: {color}; border-radius: 12px; "
                f"border: 2px solid {SURFACE};")
            swatch.clicked.connect(lambda _c, col=color: self._select_color(col))
            self.color_buttons.append((swatch, color))
            toolbar.addWidget(swatch)

        custom_color_btn = QPushButton()
        custom_color_btn.setIcon(icon("custom_color", color=MUTED))
        custom_color_btn.setToolTip("Choose a custom colour")
        custom_color_btn.setFixedWidth(30)
        custom_color_btn.clicked.connect(self._pick_custom_color)
        toolbar.addWidget(custom_color_btn)

        toolbar.addStretch()

        zoom_out_btn = QPushButton()
        zoom_out_btn.setIcon(icon("zoom_out", color=MUTED))
        zoom_out_btn.setToolTip("Zoom out")
        zoom_out_btn.clicked.connect(lambda: self.canvas.scale(1 / 1.15, 1 / 1.15))
        zoom_in_btn = QPushButton()
        zoom_in_btn.setIcon(icon("zoom_in", color=MUTED))
        zoom_in_btn.setToolTip("Zoom in")
        zoom_in_btn.clicked.connect(lambda: self.canvas.scale(1.15, 1.15))
        clear_btn = QPushButton("Clear Board")
        clear_btn.setIcon(icon("clear_board", color=DANGER))
        clear_btn.setToolTip("Removes everything from this board. Cannot "
                             "be undone.")
        clear_btn.clicked.connect(self._clear_board)

        toolbar.addWidget(zoom_out_btn)
        toolbar.addWidget(zoom_in_btn)
        toolbar.addWidget(clear_btn)

        layout.addLayout(toolbar)
        layout.addWidget(self.canvas, stretch=1)

        self._select_tool("select")
        self._select_color(PALETTE[1])
        self._load_from_project()

    # --- Toolbar actions --------------------------------------------

    def _select_tool(self, tool: str):
        self.canvas.set_tool(tool)
        for key, btn in self.tool_buttons.items():
            btn.setChecked(key == tool)

    def _select_color(self, color: str):
        self.canvas.current_color = color
        for swatch, swatch_color in self.color_buttons:
            border = ACCENT if swatch_color == color else SURFACE
            swatch.setStyleSheet(
                f"background-color: {swatch_color}; border-radius: 12px; "
                f"border: 2px solid {border};")

    def _pick_custom_color(self):
        color = QColorDialog.getColor(QColor(self.canvas.current_color), self,
                                      "Choose a colour")
        if color.isValid():
            self._select_color(color.name())

    def _clear_board(self):
        confirm = QMessageBox.question(
            self, "Clear Board",
            "Remove everything from this sketch board? This cannot be "
            "undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if confirm != QMessageBox.StandardButton.Yes:
            return
        self.canvas.scene_obj.clear()
        self._save_board()

    # --- Persistence --------------------------------------------------

    def _save_board(self):
        self.active_project.sketch_data = json.dumps(self.canvas.to_shapes())
        self.file_manager.save_project(self.active_project)

    def _load_from_project(self):
        try:
            shapes = json.loads(self.active_project.sketch_data or "[]")
        except json.JSONDecodeError:
            shapes = []
        self.canvas.load_shapes(shapes)

    def refresh(self, active_project):
        """
        Re-targets the view at a (possibly updated) project.

        Skips reloading the board while the user has an unfinished
        drawing action in progress, so a save triggered elsewhere in the
        app never wipes out an in-flight stroke or shape.
        """
        self.active_project = active_project
        if self.canvas._drawing_item is not None:
            return
        self._load_from_project()
