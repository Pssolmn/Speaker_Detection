"""แบบฟอร์มแก้ cue: เก็บ draft เท่านั้น; WorkspaceStore เป็นเจ้าของข้อมูลจริง.

แยก draft จากข้อมูลที่บันทึก เพื่อป้องกันเวลาที่พิมพ์ไม่ครบถูกส่งเข้า AI
หรือข้อความที่กำลังพิมพ์หายเมื่อเปลี่ยนชื่อโปรไฟล์ด้านข้าง.
"""

from dataclasses import replace

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QLabel, QLineEdit, QPlainTextEdit, QPushButton

from src.io.result_export import format_srt_time
from src.io.subtitle_io import time_to_ms
from src.ui.icons import icon


class SubtitleEditor(QWidget):
    apply_requested = pyqtSignal()
    dirty_changed = pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.segment = None
        self._baseline = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 0, 0, 0)
        layout.setSpacing(6)
        self.heading = QLabel("เลือกบรรทัดเพื่อแก้ไข")
        self.heading.setObjectName("eyebrow")
        layout.addWidget(self.heading)
        self.start = QLineEdit()
        self.end = QLineEdit()
        self.script_name = QLineEdit()
        self.script_name.setPlaceholderText("ชื่อในบทต้นฉบับ (ถ้ามี)")
        times = QHBoxLayout()
        for label, edit in (("เข้า", self.start), ("ออก", self.end)):
            column = QVBoxLayout()
            column.setSpacing(3)
            column.addWidget(QLabel(label))
            edit.setPlaceholderText("00:00:00,000")
            edit.setMinimumWidth(110)
            column.addWidget(edit)
            times.addLayout(column)
        layout.addLayout(times)
        layout.addWidget(self.script_name)
        self.text = QPlainTextEdit()
        self.text.setPlaceholderText("บทพูด — แก้ข้อความได้ที่นี่ แล้วกดบันทึกบรรทัด")
        self.text.setMinimumHeight(65)
        layout.addWidget(self.text, 1)
        actions = QHBoxLayout()
        self.apply = QPushButton()
        self.apply.setIcon(icon("save"))
        self.apply.setToolTip("บันทึกบรรทัด (⌘/Ctrl+Enter)")
        self.apply.setAccessibleName("บันทึกบรรทัด")
        self.apply.setObjectName("primary")
        self.apply.setFixedWidth(48)
        self.apply.clicked.connect(self.apply_requested)
        actions.addWidget(self.apply)
        self.hint = QLabel("⌘ / Ctrl + Enter")
        self.hint.setObjectName("muted")
        actions.addWidget(self.hint)
        actions.addStretch()
        layout.addLayout(actions)
        for field in (self.start, self.end, self.script_name):
            field.textChanged.connect(self._changed)
        self.text.textChanged.connect(self._changed)
        self.setEnabled(False)

    def _changed(self):
        self.apply.setEnabled(self.dirty)
        self.dirty_changed.emit(self.dirty)

    def values(self):
        return self.start.text(), self.end.text(), self.text.toPlainText(), self.script_name.text()

    @property
    def dirty(self):
        return self.segment is not None and self.values() != self._baseline

    def load(self, segment, *, force=False):
        # การ refresh ชื่อผู้พูดไม่ควรทับ draft ของ cue ที่เปิดแก้อยู่.
        if not force and segment == self.segment:
            return
        self.segment = segment
        self.setEnabled(segment is not None)
        self.heading.setText(f"แก้บรรทัด #{segment.id}" if segment else "เลือกบรรทัดเพื่อแก้ไข")
        self.start.setText(format_srt_time(segment.start_ms) if segment else "")
        self.end.setText(format_srt_time(segment.end_ms) if segment else "")
        self.text.setPlainText(segment.text if segment else "")
        self.script_name.setText((segment.script_character or "") if segment else "")
        self._baseline = self.values()
        self._changed()

    def updated_segment(self):
        """คืน dataclass ที่ตรวจ start < end แล้ว; ค่าไม่ถูกต้องจะไม่แตะฐานข้อมูล."""
        if self.segment is None:
            raise ValueError("เลือกบรรทัดซับก่อน")
        return replace(self.segment, start_ms=time_to_ms(self.start.text()),
                       end_ms=time_to_ms(self.end.text()), text=self.text.toPlainText(),
                       script_character=self.script_name.text().strip() or None)
