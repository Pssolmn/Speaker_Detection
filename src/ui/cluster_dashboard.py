"""Dashboard ของกลุ่มตามซับ: จุดเล็ก = cue จริง, จุดใหญ่ = ตัวตน/กลุ่มเสียง.

ตำแหน่งใช้แรงดึง/ผลักจาก membership และเพื่อนบ้านเสียงคล้าย ไม่ใช่คะแนน AI.
วาดด้วย Qt โดยตรง ไม่เพิ่มเว็บ/โมเดล/dependency และไม่ใช้สีเป็นหลักฐาน AI.
"""
from collections import defaultdict

from PyQt6.QtCore import Qt, QSignalBlocker, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QSplitter, QLineEdit, QSlider,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView, QWidgetAction,
    QPushButton, QToolButton, QMenu, QDialog, QComboBox, QCheckBox, QDialogButtonBox, QColorDialog,
)
from src.ui.icons import icon
from src.ui.table_safety import replace_table_rows
from src.workspace.appearance import profile_color, canonical_profile, PALETTES, palette
from src.workspace.attribution import suggest_links


from src.ui.force_graph import ClusterView


class ClusterDashboard(QWidget):
    cue_requested = pyqtSignal(int)
    profile_requested = pyqtSignal(str)
    color_requested = pyqtSignal(str)
    pair_requested = pyqtSignal(str, str)
    review_requested = pyqtSignal(object)
    palette_requested = pyqtSignal()
    analyze_requested = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.store, self.rows = None, []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 0)
        top = QHBoxLayout()
        self.summary = QLabel("ภาพรวมการจัดกลุ่ม")
        self.summary.setObjectName("brand")
        top.addWidget(self.summary, 1)
        self.palette_button = QToolButton()
        self.palette_button.setIcon(icon("image"))
        self.palette_button.setToolTip("ชุดสีเริ่มต้น / เพิ่มสี Custom")
        self.palette_button.setAccessibleName("ชุดสีเริ่มต้น / เพิ่มสี Custom")
        self.palette_button.clicked.connect(self.palette_requested)
        top.addWidget(self.palette_button)
        self.analyze_button = QPushButton(icon("scan"), "ตรวจคู่ภาพ–เสียง")
        self.analyze_button.clicked.connect(self.analyze_requested)
        top.addWidget(self.analyze_button)
        layout.addLayout(top)
        split = QSplitter(Qt.Orientation.Horizontal)
        graph_panel = QWidget()
        graph_layout = QVBoxLayout(graph_panel)
        graph_layout.setContentsMargins(0, 0, 8, 0)
        self.graph = ClusterView()
        self.graph.selected.connect(self.select_node)
        self.graph.activated.connect(self.activate_node)
        self.graph.color_requested.connect(self.color_requested)
        graph_tools = QHBoxLayout()
        self.graph_search = QLineEdit()
        self.graph_search.setPlaceholderText("ค้นหาชื่อ / บทในกราฟ…")
        self.graph_search.textChanged.connect(self.graph.set_filter)
        graph_tools.addWidget(self.graph_search, 1)
        self.local_graph = QCheckBox("รอบจุดที่เลือก")
        self.local_graph.toggled.connect(self.graph.set_local)
        graph_tools.addWidget(self.local_graph)
        for symbol, title, callback in (("scan", "จัดกราฟให้พอดี (Home)", self.graph.fit),
                ("undo", "คืนตำแหน่งและปล่อยจุดที่ลากไว้", self.graph.reset_layout)):
            button = QToolButton()
            button.setIcon(icon(symbol))
            button.setToolTip(title)
            button.setAccessibleName(title)
            button.clicked.connect(callback)
            graph_tools.addWidget(button)
        self.graph_settings = QToolButton()
        self.graph_settings.setIcon(icon("settings"))
        self.graph_settings.setToolTip("แรงดึง / แรงผลัก / เส้นความคล้าย")
        self.graph_settings.setAccessibleName(self.graph_settings.toolTip())
        self.graph_settings.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.graph_settings.setMenu(self.build_graph_settings())
        graph_tools.addWidget(self.graph_settings)
        graph_layout.addLayout(graph_tools)
        graph_layout.addWidget(self.graph, 1)
        self.graph_note = QLabel("จุดเล็ก = บรรทัดซับ · จุดใหญ่ = กลุ่ม · ตำแหน่งไม่ใช่ระยะ embedding")
        self.graph_note.setWordWrap(True)
        self.graph_note.setObjectName("muted")
        graph_layout.addWidget(self.graph_note)
        self.selection = QLabel("ลากจุดจัดตำแหน่ง · ลากพื้นหลังเลื่อน · หมุนล้อซูม · ดับเบิลคลิกเปิดบท")
        self.selection.setWordWrap(True)
        self.selection.setFixedHeight(52)
        self.selection.setTextFormat(Qt.TextFormat.PlainText)
        graph_layout.addWidget(self.selection)
        split.addWidget(graph_panel)
        side = QWidget()
        side.setMinimumWidth(360)
        right = QVBoxLayout(side)
        right.setContentsMargins(8, 0, 0, 0)
        right.addWidget(QLabel("คู่เสียง → ตัวละคร · รอคุณตรวจยืนยัน"))
        self.pairs = QTableWidget(0, 3)
        self.pairs.setHorizontalHeaderLabels(["กลุ่มเสียง", "ตัวละคร", "คะแนน"])
        self.pairs.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.pairs.verticalHeader().hide()
        self.pairs.setShowGrid(False)
        self.pairs.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.pairs.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.pairs.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.pairs.itemSelectionChanged.connect(self.select_pair)
        self.pairs.cellDoubleClicked.connect(lambda *_: self.review())
        right.addWidget(self.pairs, 1)
        self.details = QLabel("เลือกกลุ่มเสียงเพื่อดูเหตุผล ไม่ผูกจากใบหน้าบนจออย่างเดียว")
        self.details.setWordWrap(True)
        self.details.setTextFormat(Qt.TextFormat.PlainText)
        right.addWidget(self.details)
        self.review_button = QPushButton(icon("play"), "ดู / ฟังหลักฐาน")
        self.review_button.clicked.connect(self.review)
        right.addWidget(self.review_button)
        self.confirm_button = QPushButton(icon("link"), "ยืนยันคู่เสียง–ตัวละคร")
        self.confirm_button.setObjectName("primary")
        self.confirm_button.clicked.connect(self.confirm)
        right.addWidget(self.confirm_button)
        self.manual_button = QPushButton("เลือกตัวละครเอง…")
        self.manual_button.clicked.connect(lambda: self.pair_requested.emit(self.current()["voice_id"], "") if self.current() else None)
        right.addWidget(self.manual_button)
        note = QLabel("คะแนน 0–100 เป็นหลักฐานประกอบ ไม่ใช่ % ความถูกต้อง\nผูกแล้วใช้ชื่อ/สีตัวละครเดียวกันทุกตอน · เสียงนอกจอไม่ถูกบังคับให้เลือกใบหน้า")
        note.setObjectName("muted")
        note.setWordWrap(True)
        right.addWidget(note)
        split.addWidget(side)
        split.setSizes([800, 420])
        layout.addWidget(split, 1)
        self.set_busy(False)

    def build_graph_settings(self):
        menu, panel = QMenu(self), QWidget()
        layout = QVBoxLayout(panel)
        self.graph_motion = QCheckBox("เคลื่อนไหวตามแรง (หยุดเองเมื่อนิ่ง)")
        self.graph_motion.setChecked(True)
        self.graph_motion.toggled.connect(self.graph.set_animation)
        layout.addWidget(self.graph_motion)
        self.empty_groups = QCheckBox("แสดงกลุ่มที่ยังไม่มีบทในตอนนี้")
        self.empty_groups.toggled.connect(self.rebuild_graph)
        layout.addWidget(self.empty_groups)
        self.force_sliders = {}
        for key, title in (("repulsion", "แรงผลัก"), ("attraction", "แรงดึงเส้น"), ("gravity", "แรงรวมศูนย์")):
            layout.addWidget(QLabel(title))
            slider = QSlider(Qt.Orientation.Horizontal)
            slider.setRange(20, 250)
            slider.setValue(100)
            slider.valueChanged.connect(lambda value, key=key: self.set_force(key, value / 100))
            layout.addWidget(slider)
            self.force_sliders[key] = slider
        self.similarity_label = QLabel("เส้นเสียงคล้าย ≥ 0.65 (ไม่ใช่ความมั่นใจ)")
        layout.addWidget(self.similarity_label)
        self.similarity = QSlider(Qt.Orientation.Horizontal)
        self.similarity.setRange(40, 95)
        self.similarity.setValue(65)
        self.similarity.valueChanged.connect(self.similarity_changed)
        self.similarity.sliderReleased.connect(self.rebuild_graph)
        layout.addWidget(self.similarity)
        item = QWidgetAction(menu)
        item.setDefaultWidget(panel)
        menu.addAction(item)
        return menu

    def similarity_changed(self, value):
        self.similarity_label.setText(f"เส้นเสียงคล้าย ≥ {value / 100:.2f} (ไม่ใช่ความมั่นใจ)")
        # Keyboard and accessibility changes do not emit sliderReleased.
        if not self.similarity.isSliderDown():
            self.rebuild_graph()

    def set_force(self, key, value):
        if self.graph.layout:
            setattr(self.graph.layout, key, value)
            self.graph.wake()

    def rebuild_graph(self):
        if not self.store:
            return
        self.graph.threshold = self.similarity.value() / 100
        self.graph.include_empty = self.empty_groups.isChecked()
        rendered = self.graph.populate(self.store, self._graph_segments, self._graph_results)
        for key, slider in self.force_sliders.items():
            self.set_force(key, slider.value() / 100)
        self.graph_note.setText(f"{rendered}/{len(self._graph_segments)} บท · เส้นทึบ = สมาชิก · เส้นประ = เสียงคล้าย\n"
            "ตำแหน่งจากแรงดึง–ผลัก ไม่ใช่คะแนน AI · ลากจุดไม่เปลี่ยนกลุ่ม · แสดงไม่เกิน 500 บท")

    def current(self):
        index = self.pairs.currentRow()
        return self.rows[index] if 0 <= index < len(self.rows) else None

    def clear(self):
        self.store, self.rows = None, []
        replace_table_rows(self.pairs, 0)
        self.graph.clear_graph()
        self._graph_segments, self._graph_results = [], []
        self.summary.setText("ภาพรวมการจัดกลุ่ม")
        self.selection.setText("เลือกโปรเจกต์จาก Home")
        self.select_pair()

    def select_node(self, data):
        text = data.get("text") or "ดับเบิลคลิกเปิดกลุ่ม · คลิกขวาเปลี่ยนสี"
        lines = text.splitlines()
        if len(lines) > 1:
            preview = self.selection.fontMetrics().elidedText(" ".join(lines[1:]),
                Qt.TextElideMode.ElideRight, max(150, self.selection.width() - 4))
            text = lines[0] + "\n" + preview
        self.selection.setText(text)
        self.selection.setToolTip(data.get("text", ""))

    def activate_node(self, data):
        if "cue_id" in data:
            self.cue_requested.emit(data["cue_id"])
        elif data.get("profile_id"):
            self.profile_requested.emit(data["profile_id"])

    def select_pair(self):
        item = self.current()
        if not item:
            self.details.setText("ยังไม่มีกลุ่มเสียง — สแกนเสียงหรือภาพและเสียงก่อน")
        else:
            self.details.setText(("ผูกแล้วโดยผู้ใช้\n" if item.get("linked") else "ยังไม่ผูก\n") +
                "\n".join(item.get("reasons", ["ยังไม่มีภาพปากที่ตรงกับช่วงเสียงมากพอ กดตรวจคู่ หรือเลือกเองหลังตรวจ"])) +
                (f"\nความมั่นใจเชิงหลักฐาน: {item['level']} · {item['score'] * 100:.0f}/100" if "score" in item else ""))
        self.set_busy(getattr(self, "busy", False))

    def set_busy(self, busy):
        self.busy = busy
        item = self.current()
        self.analyze_button.setEnabled(not busy and self.store is not None)
        self.palette_button.setEnabled(not busy and self.store is not None)
        self.review_button.setEnabled(bool(item and item.get("examples")))
        self.confirm_button.setEnabled(bool(not busy and item and item.get("visual_id") and not item.get("linked")))
        self.manual_button.setEnabled(bool(not busy and item))

    def review(self):
        item = self.current()
        if item and item.get("examples"):
            self.review_requested.emit(item)

    def confirm(self):
        item = self.current()
        if item and item.get("visual_id"):
            self.pair_requested.emit(item["voice_id"], item["visual_id"])

    def refresh(self, store, segments, results):
        self.store = store
        self.selection.setText("ลากจุดจัดตำแหน่ง · ลากพื้นหลังเลื่อน · หมุนล้อซูม · ดับเบิลคลิกเปิดบท")
        selected = self.current()
        selected_id = selected["voice_id"] if selected else None
        profiles = {item["id"]: item for item in store.profiles()}
        candidates = suggest_links(store)
        links = defaultdict(list)
        for link in store.rows("SELECT * FROM links"):
            links[link["voice_id"]].append(link["visual_id"])
        self.rows = []
        for voice in store.profiles("voice"):
            if not voice["count"]:
                continue
            choices = [item for item in candidates if item["voice_id"] == voice["id"]]
            item = dict(choices[0]) if choices else {"voice_id": voice["id"], "visual_id": None}
            if len(links[voice["id"]]) == 1:
                target = links[voice["id"]][0]
                item = dict(next((candidate for candidate in choices if candidate["visual_id"] == target),
                            {"voice_id": voice["id"], "visual_id": target}))
                item["linked"] = True
                if choices and choices[0]["visual_id"] != target:
                    item["reasons"] = ["หลักฐานใหม่เสนอคนละตัวละครกับคู่ที่ยืนยัน โปรดตรวจ; ระบบไม่เปลี่ยนคู่เอง"]
            self.rows.append(item)
        with QSignalBlocker(self.pairs):
            replace_table_rows(self.pairs, len(self.rows))
            selected_row = 0
            for index, item in enumerate(self.rows):
                if item["voice_id"] == selected_id:
                    selected_row = index
                # Resolve the shared name on every refresh; do not leave the old
                # anonymous voice name visible after a confirmed character rename.
                voice_name = profiles[canonical_profile(store, item["voice_id"])]["name"]
                score_label = (f"{item['score']*100:.0f}/100 · {item['level']}" if "score" in item else "—")
                if item.get("evidence_kind") == "subtitle":
                    score_label = "ซับ · " + score_label
                values = [voice_name,
                          profiles[item["visual_id"]]["name"] if item.get("visual_id") else "ยังไม่ทราบ",
                          "✓ ผูกแล้ว" if item.get("linked") else score_label]
                for column, value in enumerate(values):
                    cell = QTableWidgetItem(value)
                    cell.setToolTip(f"{value}\nกลุ่มเสียง {item['voice_id'][:8]} · ชื่อเดิม: {profiles[item['voice_id']]['name']}"
                                    if column == 0 else value)
                    cell.setForeground(QColor(profile_color(store, item["voice_id"])))
                    self.pairs.setItem(index, column, cell)
            if self.rows:
                self.pairs.selectRow(selected_row)
        self.select_pair()
        self._graph_segments, self._graph_results = segments, results
        self.rebuild_graph()
        linked = sum(bool(item.get("linked")) for item in self.rows)
        self.summary.setText(f"{len(segments)} บรรทัด · {len(self.rows)} กลุ่มเสียง · ผูกแล้ว {linked}")


class PaletteDialog(QDialog):
    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.setWindowTitle("ชุดสีของโปรเจกต์")
        self.colors = palette(store)
        self.initial_colors = list(self.colors)
        layout = QVBoxLayout(self)
        self.presets = QComboBox()
        self.presets.addItems(["ชุดปัจจุบัน", *PALETTES])
        self.presets.currentTextChanged.connect(self.change_preset)
        layout.addWidget(self.presets)
        self.swatches = QGridLayout()
        layout.addLayout(self.swatches)
        add = QPushButton("เพิ่มสี Custom…")
        add.clicked.connect(self.add_color)
        layout.addWidget(add)
        self.recolor = QCheckBox("ใช้ชุดนี้กับกลุ่มเดิมด้วย (แทนสี Custom เดิม; ย้อนกลับได้)")
        layout.addWidget(self.recolor)
        layout.addWidget(QLabel("ไม่เลือกช่องนี้ = ใช้กับกลุ่มใหม่เท่านั้น · คลิกสีเพื่อแก้"))
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.redraw()

    def change_preset(self, name):
        self.colors = list(PALETTES[name]) if name in PALETTES else list(self.initial_colors)
        self.redraw()

    def redraw(self):
        while self.swatches.count():
            self.swatches.takeAt(0).widget().deleteLater()
        for index, color in enumerate(self.colors):
            button = QPushButton()
            button.setFixedSize(28, 28)
            button.setStyleSheet(f"background: {color}; border: 1px solid #aab6ca;")
            button.setToolTip(color)
            button.setAccessibleName("สี " + color)
            button.clicked.connect(lambda checked=False, index=index: self.edit_color(index))
            self.swatches.addWidget(button, index // 8, index % 8)

    def edit_color(self, index):
        color = QColorDialog.getColor(QColor(self.colors[index]), self, "เลือกสี")
        if color.isValid():
            self.colors[index] = color.name().upper()
            self.redraw()

    def add_color(self):
        if len(self.colors) >= 64:
            return
        color = QColorDialog.getColor(parent=self, title="เพิ่มสีในชุด")
        if color.isValid() and color.name().upper() not in self.colors:
            self.colors.append(color.name().upper())
            self.redraw()
