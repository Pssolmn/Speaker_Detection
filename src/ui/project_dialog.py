"""สร้างโปรเจกต์แบบมีขั้นตอน: ชื่อ → ที่เก็บ → วิดีโอ/ซับ (เลือกภายหลังได้)."""

from pathlib import Path
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLineEdit, QLabel, QToolButton, QFileDialog, QDialogButtonBox, QMessageBox
from src.ui.icons import icon


class NewProjectDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("สร้างโปรเจกต์")
        self.resize(570, 330)
        layout = QVBoxLayout(self)
        heading = QLabel("ชื่อโปรเจกต์และตำแหน่งจัดเก็บ")
        heading.setObjectName("brand")
        layout.addWidget(heading)
        self.name, self.location, self.video, self.subtitle = (QLineEdit() for _ in range(4))
        self.name.setPlaceholderText("เช่น Oshi no Ko — Season 3")
        self.location.setPlaceholderText("เลือกโฟลเดอร์แม่ โปรแกรมจะสร้างโฟลเดอร์โปรเจกต์ด้านใน")
        self.video.setPlaceholderText("เลือกตอนนี้ หรือเพิ่มภายหลังจาก File > นำเข้าวิดีโอ")
        self.subtitle.setPlaceholderText("SRT ของวิดีโอข้างต้น (ไม่จำเป็นต้องมี)")
        form = QFormLayout()
        form.addRow("ชื่อ", self.name)
        for label, field, kind in (("เก็บไว้ที่", self.location, "folder"), ("วิดีโอ", self.video, "video"), ("ซับ", self.subtitle, "subtitle")):
            row = QHBoxLayout()
            row.addWidget(field)
            button = QToolButton()
            button.setIcon(icon("folder"))
            button.setToolTip("เลือก" + label)
            button.setAccessibleName("เลือก" + label)
            button.clicked.connect(lambda checked=False, field=field, kind=kind: self.browse(field, kind))
            row.addWidget(button)
            form.addRow(label, row)
        layout.addLayout(form)
        note = QLabel("ไม่คัดลอกหรือเขียนทับวิดีโอต้นฉบับ · นำเข้าซับหลังเลือกวิดีโอ\nโปรเจกต์ที่สร้างจะปรากฏใน Home และใช้ข้อมูลเดียวกันทั้งสองหน้าทำงาน")
        note.setWordWrap(True)
        note.setObjectName("muted")
        layout.addWidget(note)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("สร้างโปรเจกต์")
        buttons.accepted.connect(self.validate)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def browse(self, field, kind):
        if kind == "folder":
            path = QFileDialog.getExistingDirectory(self, "เลือกโฟลเดอร์แม่")
        else:
            pattern = "Video (*.mp4 *.mkv *.mov *.avi *.webm)" if kind == "video" else "SRT (*.srt)"
            path, _ = QFileDialog.getOpenFileName(self, "เลือกไฟล์", "", pattern)
        if path:
            field.setText(path)

    def values(self):
        name = self.name.text().strip()
        if not name or name in {".", ".."} or Path(name).name != name or any(char in name for char in "\\\x00"):
            raise ValueError("ตั้งชื่อโปรเจกต์เป็นชื่อโฟลเดอร์ ไม่ใส่ / หรือ \\")
        if not self.location.text().strip() or not Path(self.location.text()).expanduser().is_dir():
            raise ValueError("เลือกโฟลเดอร์แม่ที่มีอยู่ก่อน")
        video, subtitle = self.video.text().strip(), self.subtitle.text().strip()
        if subtitle and not video:
            raise ValueError("เลือกวิดีโอสำหรับซับนี้ก่อน หรือเว้นทั้งสองช่องเพื่อนำเข้าภายหลัง")
        for value in (video, subtitle):
            if value and not Path(value).expanduser().is_file():
                raise ValueError(f"ไม่พบไฟล์: {value}")
        return Path(self.location.text()).expanduser() / name, video or None, subtitle or None

    def validate(self):
        try:
            self.values()
        except ValueError as error:
            QMessageBox.warning(self, "ตรวจข้อมูลโปรเจกต์", str(error))
            return
        self.accept()
