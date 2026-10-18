"""Obsidian-like graph interaction on Qt: drag nodes, pan, zoom, hover neighbours.

This module owns only display positions. It never writes profiles or links.
The force timer sleeps after settling and whenever the dashboard is hidden.
"""
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QPen, QBrush, QPainter, QFont
from PyQt6.QtWidgets import QGraphicsView, QGraphicsScene, QGraphicsEllipseItem, QGraphicsItem, QMenu
from src.ui.icons import icon
from src.workspace.graph import build_graph, ForceLayout


class ClusterNode(QGraphicsEllipseItem):
    def __init__(self, number, data, view):
        radius = 10 if data["hub"] else 5
        super().__init__(-radius, -radius, radius * 2, radius * 2)
        self.number, self.payload, self.view = number, data, view
        self.color = QColor(data["color"])
        self.setBrush(QBrush(self.color))
        self.setPen(QPen(self.color.lighter(130), .8))
        self.setToolTip(data["text"])
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsFocusable)
        # Keep names and hit targets readable when fitting a whole episode.
        # Only positions/edges scale with the camera, never the text size.
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations)
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setZValue(3)
        self.label = view.scene().addSimpleText(data["label"])
        self.label.setParentItem(self)
        self.label.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        font = QFont()
        font.setPixelSize(13 if data["hub"] else 11)
        self.label.setFont(font)
        self.label.setBrush(QColor("#c5c6d5"))
        self.label.setPos(-self.label.boundingRect().width() / 2, radius + 5)
        self.label.setVisible(data["hub"])

    def hoverEnterEvent(self, event):
        self.setScale(1.25)
        self.label.show()
        self.view.highlight(self.number)
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self.setScale(1.)
        self.label.setVisible(self.payload["hub"] or self.view.transform().m11() > 1.6)
        self.view.highlight(self.view.selected_number)
        super().hoverLeaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.view.select_node(self.number)
            self.view.layout.pinned.add(self.number)
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        super().mouseMoveEvent(event)
        self.view.layout.positions[self.number] = [self.pos().x(), self.pos().y()]
        self.view.update_edges()
        self.view.wake()

    def mouseReleaseEvent(self, event):
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.view.layout.positions[self.number] = [self.pos().x(), self.pos().y()]
        self.view.wake()
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        self.view.activated.emit(self.payload)
        event.accept()

    def contextMenuEvent(self, event):
        menu = QMenu()
        inspect = menu.addAction(icon("search"), "เปิดบรรทัด / กลุ่ม")
        unpin = menu.addAction("ปล่อยจุดให้เคลื่อนตามแรง")
        color = menu.addAction(icon("image"), "เปลี่ยนสีตัวละคร/กลุ่ม…") if self.payload.get("profile_id") else None
        choice = menu.exec(event.screenPos())
        if choice == inspect:
            self.view.activated.emit(self.payload)
        elif choice == unpin:
            self.view.layout.pinned.discard(self.number)
            self.view.wake()
        elif color is not None and choice == color:
            self.view.color_requested.emit(self.payload["profile_id"])
        event.accept()


class ClusterView(QGraphicsView):
    selected = pyqtSignal(object)
    activated = pyqtSignal(object)
    color_requested = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.setScene(QGraphicsScene(self))
        self.scene().setItemIndexMethod(QGraphicsScene.ItemIndexMethod.NoIndex)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setBackgroundBrush(QColor("#111218"))
        self.setFrameShape(QGraphicsView.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setMinimumSize(350, 260)
        self.setAccessibleName("กราฟความสัมพันธ์ของบทพูด ลากจุด/เลื่อน/ซูม; Enter เปิดจุดที่เลือก")
        self.hubs, self.nodes, self.edge_items = {}, [], []
        self.data, self.layout = None, None
        self.selected_number = None
        self.threshold, self.include_empty = .65, False
        self.query, self.local_only, self.animate = "", False, True
        self.timer = QTimer(self)
        self.timer.setInterval(33)
        self.timer.timeout.connect(self.tick)
        self.ticks = 0
        self.user_view = False

    def clear_graph(self):
        self.timer.stop()
        self.scene().clear()
        self.hubs, self.nodes, self.edge_items = {}, [], []
        self.data, self.layout, self.selected_number = None, None, None

    def populate(self, store, segments, results):
        old = {node.payload["key"]: node.pos() for node in self.nodes}
        selected_key = self.nodes[self.selected_number].payload["key"] if self.selected_number is not None else None
        old_pins = {self.nodes[i].payload["key"] for i in self.layout.pinned} if self.layout else set()
        self.clear_graph()
        self.data = build_graph(store, segments, results, threshold=self.threshold, include_empty=self.include_empty)
        self.layout = ForceLayout(self.data)
        for number, data in enumerate(self.data["nodes"]):
            if data["key"] in old:
                p = old[data["key"]]
                self.layout.positions[number] = [p.x(), p.y()]
            if data["key"] in old_pins:
                self.layout.pinned.add(number)
            if data["key"] == selected_key:
                self.selected_number = number
        if not old:
            # Large episodes settle over subsequent timer ticks rather than
            # blocking the first paint with a long synchronous simulation.
            for _ in range(12 if len(self.data["nodes"]) > 200 else 65):
                self.layout.step()
        for a, b, kind, score in self.data["edges"]:
            pen = QPen(QColor("#606477"), 1.)
            pen.setCosmetic(True)  # thin but legible at every zoom level
            if kind == "similarity":
                pen.setStyle(Qt.PenStyle.DotLine)
            line = self.scene().addLine(0, 0, 0, 0, pen)
            line.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
            line.setZValue(0)
            line.setToolTip("สมาชิกในกลุ่ม" if kind == "membership" else f"ความคล้ายเวกเตอร์เสียง {score:.3f} (ไม่ใช่โอกาสถูก)")
            self.edge_items.append(line)
        for number, data in enumerate(self.data["nodes"]):
            node = ClusterNode(number, data, self)
            self.scene().addItem(node)
            node.setPos(*self.layout.positions[number])
            self.nodes.append(node)
        self.hubs = {key: self.nodes[value] for key, value in self.data["hubs"].items()}
        if not self.nodes:
            message = self.scene().addSimpleText("นำเข้าซับเพื่อดูเครือข่ายบทพูดจริงของตอนนี้")
            message.setBrush(QColor("#9294a8"))
        self.update_edges()
        self.highlight(self.selected_number)
        if not old:
            self.fit()
        self.wake()
        return self.data["cue_count"]

    def update_edges(self):
        if not self.data:
            return
        for line, (a, b, _, _) in zip(self.edge_items, self.data["edges"]):
            p, q = self.nodes[a].pos(), self.nodes[b].pos()
            line.setLine(p.x(), p.y(), q.x(), q.y())

    def wake(self):
        self.ticks = 0
        if self.animate and self.isVisible() and self.layout and self.nodes:
            self.timer.start(50 if len(self.nodes) > 600 else 33)

    def tick(self):
        if not self.isVisible() or not self.animate or not self.layout:
            self.timer.stop()
            return
        speed = self.layout.step()
        for node, point in zip(self.nodes, self.layout.positions):
            node.setPos(*point)
        self.update_edges()
        self.ticks += 1
        if self.ticks >= 180 or (self.ticks > 25 and speed < .08):
            self.timer.stop()

    def set_animation(self, enabled):
        self.animate = enabled
        self.wake() if enabled else self.timer.stop()

    def showEvent(self, event):
        super().showEvent(event)
        if not self.user_view:
            self.fit()
        self.wake()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "user_view") and not self.user_view:
            self.fit()

    def mousePressEvent(self, event):
        item = self.itemAt(event.position().toPoint())
        while item is not None and not isinstance(item, ClusterNode):
            item = item.parentItem()
        if item is None:
            self.user_view = True
            if event.button() == Qt.MouseButton.LeftButton:
                self.selected_number = None
                self.highlight()
        super().mousePressEvent(event)

    def hideEvent(self, event):
        self.timer.stop()
        super().hideEvent(event)

    def select_node(self, number):
        self.selected_number = number
        self.selected.emit(self.nodes[number].payload)
        self.highlight(number)

    def highlight(self, number=None):
        neighbours = {number} if number is not None else set()
        if self.data and number is not None:
            for a, b, _, _ in self.data["edges"]:
                if a == number or b == number:
                    neighbours.update((a, b))
        for index, node in enumerate(self.nodes):
            matches = not self.query or self.query in node.payload["text"].casefold()
            local = not self.local_only or number is None or index in neighbours
            node.setVisible(local)
            node.setOpacity(1. if matches and (number is None or index in neighbours) else .18)
        if self.data:
            for line, (a, b, _, _) in zip(self.edge_items, self.data["edges"]):
                line.setVisible(self.nodes[a].isVisible() and self.nodes[b].isVisible())
                line.setOpacity(.8 if number is None or number in {a, b} else .12)

    def set_filter(self, text):
        self.query = text.strip().casefold()
        self.highlight(self.selected_number)

    def set_local(self, enabled):
        self.local_only = enabled
        self.highlight(self.selected_number)

    def reset_layout(self):
        if self.data:
            forces = {key: getattr(self.layout, key) for key in ("repulsion", "attraction", "gravity")}
            self.layout = ForceLayout(self.data)
            for key, value in forces.items():
                setattr(self.layout, key, value)
            for _ in range(12 if len(self.nodes) > 200 else 65):
                self.layout.step()
            for node, point in zip(self.nodes, self.layout.positions):
                node.setPos(*point)
            self.update_edges()
            self.fit()
            self.wake()

    def fit(self):
        self.user_view = False
        bounds = self.scene().itemsBoundingRect().adjusted(-60, -70, 60, 70)
        self.setSceneRect(bounds.adjusted(-400, -400, 400, 400))
        self.fitInView(bounds, Qt.AspectRatioMode.KeepAspectRatio)

    def wheelEvent(self, event):
        self.zoom(1.15 if event.angleDelta().y() > 0 else 1 / 1.15)
        event.accept()

    def zoom(self, factor):
        if .12 <= self.transform().m11() * factor <= 6:
            self.user_view = True
            self.scale(factor, factor)
            for node in self.nodes:
                node.label.setVisible(node.payload["hub"] or self.transform().m11() > 1.6)

    def keyPressEvent(self, event):
        if event.key() in {Qt.Key.Key_Plus, Qt.Key.Key_Equal}:
            self.zoom(1.15)
        elif event.key() == Qt.Key.Key_Minus:
            self.zoom(1 / 1.15)
        elif event.key() == Qt.Key.Key_Home:
            self.fit()
        elif event.key() in {Qt.Key.Key_Return, Qt.Key.Key_Enter} and self.selected_number is not None:
            self.activated.emit(self.nodes[self.selected_number].payload)
        elif event.key() == Qt.Key.Key_Escape:
            self.selected_number = None
            self.highlight()
        else:
            super().keyPressEvent(event)
