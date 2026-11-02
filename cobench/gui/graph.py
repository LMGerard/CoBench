# SPDX-License-Identifier: LGPL-2.1-or-later
"""Window showing which part uses which, coloured by lock state."""

import os

from ..i18n import tr
from .qt import Qt, QtCore, QtGui, QtWidgets

NODE_W = 150
NODE_H = 34
GAP_X = 30
GAP_Y = 70


def layers(graph):
    """Rows of parts: assemblies at the top, the parts they use below.

    The row of a part is the length of the longest chain of users above it,
    so a part is always drawn below every file that uses it (cycles cut).
    """
    users = {part: [] for part in graph}
    for owner, targets in graph.items():
        for target in targets:
            users.setdefault(target, []).append(owner)
    depth = {}

    def visit(part, stack):
        if part in depth:
            return depth[part]
        stack = stack | {part}
        above = [visit(u, stack) for u in users.get(part, []) if u not in stack]
        depth[part] = 1 + max(above) if above else 0
        return depth[part]

    for part in users:
        visit(part, frozenset())
    rows = {}
    for part, row in depth.items():
        rows.setdefault(row, []).append(part)
    return [sorted(rows[r], key=lambda p: os.path.basename(p).lower()) for r in sorted(rows)]


class _Node(QtWidgets.QGraphicsRectItem):
    def __init__(self, dialog, path, color, text, tip):
        super().__init__(0, 0, NODE_W, NODE_H)
        self.dialog = dialog
        self.path = path
        self.setBrush(QtGui.QBrush(color.lighter(170)))
        pen = QtGui.QPen(color)
        pen.setWidth(3)
        self.setPen(pen)
        self.setToolTip(tip)
        self.setFlag(QtWidgets.QGraphicsItem.ItemIsSelectable, True)
        self.setCursor(Qt.PointingHandCursor)
        label = QtWidgets.QGraphicsSimpleTextItem(text, self)
        metrics = QtGui.QFontMetrics(label.font())
        label.setText(metrics.elidedText(text, Qt.ElideMiddle, NODE_W - 10))
        box = label.boundingRect()
        label.setPos((NODE_W - box.width()) / 2, (NODE_H - box.height()) / 2)

    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        self.dialog.part_selected.emit(self.path)

    def mouseDoubleClickEvent(self, event):
        self.dialog.part_activated.emit(self.path)


class GraphDialog(QtWidgets.QDialog):
    part_selected = QtCore.Signal(str)
    part_activated = QtCore.Signal(str)

    def __init__(self, session, graph, parent=None):
        super().__init__(parent)
        from .panel import COLORS, status_text
        self.setWindowTitle(tr("Links between parts"))
        self.resize(900, 600)
        layout = QtWidgets.QVBoxLayout(self)
        hint = QtWidgets.QLabel(tr("An arrow goes from a file to the parts it uses. "
                                   "Click to select, double-click to edit."))
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.scene = QtWidgets.QGraphicsScene(self)
        self.view = QtWidgets.QGraphicsView(self.scene)
        self.view.setRenderHint(QtGui.QPainter.Antialiasing)
        self.view.setDragMode(QtWidgets.QGraphicsView.ScrollHandDrag)
        layout.addWidget(self.view, 1)
        self.only_linked = QtWidgets.QCheckBox(tr("Hide parts without links"))
        self.only_linked.setChecked(True)
        self.only_linked.toggled.connect(lambda _on: self._draw())
        layout.addWidget(self.only_linked)
        self.session = session
        self.graph = graph
        self._colors = COLORS
        self._status_text = status_text
        self.nodes = {}
        self._draw()

    def _draw(self):
        self.scene.clear()
        self.nodes = {}
        graph = self.graph
        if self.only_linked.isChecked():
            linked = {p for p, targets in graph.items() if targets}
            linked |= {t for targets in graph.values() for t in targets}
            graph = {p: [t for t in targets if t in linked] for p, targets in graph.items() if p in linked}
        rows = layers(graph)
        width = max([len(r) for r in rows] + [1]) * (NODE_W + GAP_X)
        for row_index, row in enumerate(rows):
            offset = (width - len(row) * (NODE_W + GAP_X)) / 2
            for column, path in enumerate(row):
                state = self.session.state(path)
                tip = "%s\n%s" % (self.session.project.rel(path), self._status_text(state))
                name = os.path.splitext(os.path.basename(path))[0]
                node = _Node(self, path, self._colors[state.status], name, tip)
                node.setPos(offset + column * (NODE_W + GAP_X), row_index * (NODE_H + GAP_Y))
                node.setZValue(1)
                self.scene.addItem(node)
                self.nodes[path] = node
        pen = QtGui.QPen(QtGui.QColor(120, 120, 120))
        pen.setWidthF(1.5)
        for owner, targets in graph.items():
            for target in targets:
                if owner in self.nodes and target in self.nodes:
                    self._arrow(self.nodes[owner], self.nodes[target], pen)
        if not rows:
            self.scene.addSimpleText(tr("No links between the parts of this project."))
        self.view.setSceneRect(self.scene.itemsBoundingRect().adjusted(-20, -20, 20, 20))

    def _arrow(self, start, end, pen):
        a = start.sceneBoundingRect()
        b = end.sceneBoundingRect()
        if b.top() > a.bottom():
            p1 = QtCore.QPointF(a.center().x(), a.bottom())
            p2 = QtCore.QPointF(b.center().x(), b.top())
        else:  # same row or upwards (cycle): side to side
            p1 = QtCore.QPointF(a.right() if b.center().x() > a.center().x() else a.left(), a.center().y())
            p2 = QtCore.QPointF(b.left() if b.center().x() > a.center().x() else b.right(), b.center().y())
        line = QtCore.QLineF(p1, p2)
        self.scene.addLine(line, pen)
        angle = line.angle()
        head = QtGui.QPolygonF([p2])
        for spread in (25, -25):
            tip = QtCore.QLineF(p2, p2 + QtCore.QPointF(10, 0))
            tip.setAngle(angle + 180 + spread)
            head.append(tip.p2())
        self.scene.addPolygon(head, pen, QtGui.QBrush(pen.color()))
