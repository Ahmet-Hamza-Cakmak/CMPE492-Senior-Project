"""A lightweight top-down schematic of the editable track."""

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

from ..simulation.walls import WALL_THICKNESS, wall_segments


class TrackPreview(QWidget):
    def __init__(self):
        super().__init__()
        self.scenario = None
        self.setMinimumSize(340, 180)

    def set_scenario(self, scenario):
        self.scenario = scenario
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("#edf3ef"))
        painter.setPen(QPen(QColor("#dce6df"), 1))
        for x in range(0, self.width(), 28):
            painter.drawLine(x, 0, x, self.height())
        for y in range(0, self.height(), 28):
            painter.drawLine(0, y, self.width(), y)
        if self.scenario is None:
            painter.setPen(QColor("#617773"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Enter valid parameters to preview")
            return
        points = self.scenario.points()
        xs, ys = zip(*points)
        scale = min((self.width() - 80) / (max(xs) - min(xs) + self.scenario.width),
                    (self.height() - 80) / (max(ys) - min(ys) + self.scenario.width))
        cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2

        def screen(point):
            return QPointF(self.width() / 2 + (point[0] - cx) * scale,
                           self.height() / 2 - (point[1] - cy) * scale)

        route = QPainterPath(screen(points[0]))
        for point in points[1:]:
            route.lineTo(screen(point))
        for color, width in (("#c6d3ca", self.scenario.width * scale + 2),
                             ("#ffffff", self.scenario.width * scale),
                             ("#2d4540", max(1.5, self.scenario.line_width * scale))):
            pen = QPen(QColor(color), width)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            painter.drawPath(route)
        wall_pen = QPen(QColor("#71858a"), max(2, WALL_THICKNESS * scale))
        wall_pen.setCapStyle(Qt.PenCapStyle.SquareCap)
        painter.setPen(wall_pen)
        for start, end in wall_segments(self.scenario):
            painter.drawLine(screen(start), screen(end))
        markers = ((points[0], "START / LAP", "#176b56"),) if self.scenario.closed else (
            (points[0], "START", "#176b56"), (points[-1], "FINISH", "#af6434"))
        for point, label, color in markers:
            position = screen(point)
            painter.setPen(QPen(QColor("white"), 2))
            painter.setBrush(QColor(color))
            painter.drawEllipse(position, 6, 6)
            painter.setPen(QColor(color))
            painter.drawText(position + QPointF(10, -12), label)
