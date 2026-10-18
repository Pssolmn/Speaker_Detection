"""Widget สำหรับ waveform และภาพตัวอย่างพร้อมกรอบหน้า (วาดบน UI thread)."""

import cv2
from PyQt6.QtCore import Qt, QRectF, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QImage, QPainter, QPen
from PyQt6.QtWidgets import QWidget


class WaveformWidget(QWidget):
    position_clicked = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(120)
        self.peaks = []
        self.duration_ms = 0
        self.current_pos_ms = 0
        self.regions = []
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_audio(self, peaks, duration_ms):
        # รับแค่ peaks ที่ worker คำนวณแล้ว ไม่อ่าน WAV ใน paintEvent
        self.peaks, self.duration_ms = peaks, duration_ms
        self.update()

    def set_position(self, position_ms):
        self.current_pos_ms = position_ms
        self.update()

    def set_regions(self, regions):
        self.regions = regions
        self.update()

    def mousePressEvent(self, event):
        if self.duration_ms and event.button() == Qt.MouseButton.LeftButton:
            ratio = max(0, min(1, event.position().x() / max(1, self.width())))
            self.position_clicked.emit(int(ratio * self.duration_ms))

    def paintEvent(self, event):
        painter = QPainter(self)
        width, height = self.width(), self.height()
        painter.fillRect(self.rect(), QColor("#101820"))
        middle = height // 2
        if self.duration_ms:
            for start, end, name, color in self.regions:
                left, right = int(start / self.duration_ms * width), int(end / self.duration_ms * width)
                painter.fillRect(left, 0, max(2, right - left), height, color)
                painter.setPen(QColor("#bbc9d8"))
                painter.setFont(QFont("Arial", 9))
                if right - left >= 30:
                    short_name = painter.fontMetrics().elidedText(name, Qt.TextElideMode.ElideRight, right - left - 6)
                    painter.drawText(left + 3, 15, short_name)
        painter.setPen(QColor("#233445"))
        painter.drawLine(0, middle, width, middle)
        painter.setPen(QColor("#4ed6c0"))
        for index, peak in enumerate(self.peaks):
            x = int(index * width / len(self.peaks))
            amplitude = int(peak * (middle - 15))
            painter.drawLine(x, middle - amplitude, x, middle + amplitude)
        if self.duration_ms:
            x = int(self.current_pos_ms / self.duration_ms * width)
            painter.setPen(QPen(QColor("#ffbf69"), 2))
            painter.drawLine(x, 0, x, height)


class DetectionPreview(QWidget):
    """ภาพนิ่งจากเวลาที่ระบุ พร้อม track/อันดับตัวละคร; ไม่ติดกรอบผิดเวลาบน player"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(320, 200)
        self.image = None
        self.boxes = []
        self.caption = "กด Preview frame หรือวิเคราะห์ช่วงซับเพื่อดูกรอบหน้า"

    def clear(self):
        self.image, self.boxes = None, []
        self.update()

    def set_preview(self, payload):
        rgb = cv2.cvtColor(payload["frame"], cv2.COLOR_BGR2RGB)
        height, width = rgb.shape[:2]
        # copy ให้ QImage เป็นเจ้าของข้อมูลเอง เพราะ ndarray ของ worker จะถูกปล่อย
        self.image = QImage(rgb.data, width, height, rgb.strides[0], QImage.Format.Format_RGB888).copy()
        self.boxes = payload["boxes"]
        self.caption = f"{payload['timestamp_ms'] / 1000:.3f}s · {len(self.boxes)} face(s) · labels = visual similarity"
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#0b1017"))
        painter.setPen(QColor("#becddd"))
        painter.setFont(QFont("Arial", 10))
        painter.drawText(QRectF(12, 6, self.width() - 24, 40), Qt.AlignmentFlag.AlignLeft | Qt.TextFlag.TextWordWrap, self.caption)
        if self.image is None:
            return
        scale = min(self.width() / self.image.width(), max(1, self.height() - 50) / self.image.height())
        left = (self.width() - self.image.width() * scale) / 2
        top = 50 + (self.height() - 50 - self.image.height() * scale) / 2
        painter.drawImage(QRectF(left, top, self.image.width() * scale, self.image.height() * scale), self.image)
        for box in self.boxes:
            x, y, width, height = box["box"]
            rect = QRectF(left + x * scale, top + y * scale, width * scale, height * scale)
            painter.setPen(QPen(QColor("#4ed6c0"), 2))
            painter.drawRect(rect)
            score = box.get("visual_score")
            score_label = f" {score:.2f}" if score is not None else ""
            label = f"#{box['track_id']} ~ {box['name']}{score_label}"
            text_width = min(self.width() - 8, painter.fontMetrics().horizontalAdvance(label) + 10)
            label_x = max(4, min(rect.x(), self.width() - text_width - 4))
            label_y = max(50, rect.y() - 23)
            painter.fillRect(QRectF(label_x, label_y, text_width, 22), QColor("#183a38"))
            painter.drawText(QRectF(label_x + 4, label_y, text_width - 8, 22), Qt.AlignmentFlag.AlignVCenter, label)
