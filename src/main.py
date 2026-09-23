"""Legacy PyQt UI retained for future integration with the speaker-attribution pipeline.

The media player, table, waveform, and time-seeking behaviour are reusable.  The
old fake subtitle import and fake character naming are deliberately disabled so
the UI cannot claim an analysis result that was never calculated.
"""

import sys
import os
import subprocess
import numpy as np
from scipy.io import wavfile

from PyQt6.QtCore import Qt, QUrl, QTime, pyqtSignal
# from PyQt6.QtCore import QTimer  # Disabled: no current UI feature schedules timer callbacks.
from PyQt6.QtGui import QPainter, QColor, QPen, QFont, QAction
# from PyQt6.QtGui import QBrush, QIcon  # Disabled: neither class is used by this UI.
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QSplitter, QTableWidget, QTableWidgetItem, QPushButton, QLabel,
    QFileDialog, QHeaderView, QMessageBox, QAbstractItemView
)
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtMultimediaWidgets import QVideoWidget

import cv2
# from extractor import extract_character_features  # Disabled: the old UI passed an entire frame, not one character ROI.
# from matcher import compare_character_features  # Disabled: matching moves to vision/visual_matcher.py.

# =====================================================================
# 1. Custom Waveform Widget (สไตล์ Subtitle Edit / Adobe Audition)
# =====================================================================
class WaveformWidget(QWidget):
    position_clicked = pyqtSignal(int)  # ส่งค่า millisecond เมื่อผู้ใช้คลิก

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(150)
        self.setStyleSheet("background-color: #121212;")
        self.peaks = None
        self.duration_ms = 0
        self.current_pos_ms = 0
        self.regions = []  # เก็บรายการ [start_ms, end_ms, character, color]
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def load_audio(self, wav_path, duration_ms):
        """อ่านไฟล์เสียงและคำนวณ Min/Max Peaks แบบ Downsampling เพื่อให้วาดกราฟเร็ว"""
        self.duration_ms = duration_ms
        try:
            sample_rate, data = wavfile.read(wav_path)
            if data.ndim > 1:
                data = data[:, 0]  # ใช้ช่อง Mono
            
            # Limit to at most 2,000 buckets while still rendering very short clips.
            num_buckets = min(2000, len(data))
            samples_per_bucket = len(data) // num_buckets
            if samples_per_bucket > 0:
                trimmed_len = num_buckets * samples_per_bucket
                reshaped = data[:trimmed_len].reshape((num_buckets, samples_per_bucket))
                self.peaks = np.max(np.abs(reshaped), axis=1)
                max_val = np.max(self.peaks) if np.max(self.peaks) > 0 else 1
                self.peaks = self.peaks / max_val
            else:
                self.peaks = None
        except Exception as e:
            print(f"Error loading waveform: {e}")
            self.peaks = None
        self.update()

    def set_position(self, pos_ms):
        self.current_pos_ms = pos_ms
        self.update()

    def set_regions(self, regions):
        self.regions = regions
        self.update()

    def mousePressEvent(self, event):
        if self.duration_ms > 0 and event.button() == Qt.MouseButton.LeftButton:
            x_ratio = event.pos().x() / max(1, self.width())
            target_ms = int(x_ratio * self.duration_ms)
            self.position_clicked.emit(target_ms)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        w, h = self.width(), self.height()
        mid_y = h // 2

        # 1. วาดพื้นหลังและตารางเวลา
        painter.fillRect(0, 0, w, h, QColor("#141414"))
        painter.setPen(QColor("#252525"))
        painter.drawLine(0, mid_y, w, mid_y)

        # 2. วาดบล็อกช่วงเวลาตัวละคร (Subtitle / Character Regions)
        if self.duration_ms > 0:
            for start_ms, end_ms, char_name, color in self.regions:
                rx1 = int((start_ms / self.duration_ms) * w)
                rx2 = int((end_ms / self.duration_ms) * w)
                rw = max(2, rx2 - rx1)
                painter.fillRect(rx1, 0, rw, h, color)
                painter.setPen(QColor("#E0E0E0"))
                painter.setFont(QFont("Monospace", 8))
                painter.drawText(rx1 + 4, 15, char_name)

        # 3. วาดคลื่นเสียง (Waveform) สีฟ้า Cyan
        if self.peaks is not None and len(self.peaks) > 0:
            painter.setPen(QColor("#00E5FF"))
            bucket_width = w / len(self.peaks)
            for i, peak in enumerate(self.peaks):
                bx = int(i * bucket_width)
                bar_h = int(peak * (mid_y - 10))
                painter.drawLine(bx, mid_y - bar_h, bx, mid_y + bar_h)

        # 4. วาดเส้น Playhead Time Pin (สีแดง สไตล์ Subtitle Edit / Audition)
        if self.duration_ms > 0:
            playhead_x = int((self.current_pos_ms / self.duration_ms) * w)
            painter.setPen(QPen(QColor("#FF3333"), 2))
            painter.drawLine(playhead_x, 0, playhead_x, h)


# =====================================================================
# 2. Main Window: Subtitle Edit Layout
# =====================================================================
class SubtitleEditStudio(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Subtitle Edit - Anime Character Identification Studio")
        self.resize(1280, 800)
        self.setStyleSheet("""
            QMainWindow { background-color: #1E1E1E; color: #FFFFFF; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }
            QTableWidget { background-color: #252526; color: #CCCCCC; gridline-color: #333333; border: none; selection-background-color: #094771; }
            QHeaderView::section { background-color: #2D2D2D; color: #AAAAAA; padding: 4px; border: 1px solid #1E1E1E; font-weight: bold; }
            QPushButton { background-color: #333333; color: #FFFFFF; border: 1px solid #444444; border-radius: 4px; padding: 6px 14px; font-weight: bold; }
            QPushButton:hover { background-color: #444444; }
            QPushButton:pressed { background-color: #007ACC; }
        """)

        self.video_path = None
        self.current_fps = 24.0
        self.audio_wav_path = None

        # ตั้งค่า Media Player ของ PyQt6 (AVFoundation บน Mac)
        self.player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.player.setAudioOutput(self.audio_output)

        self.init_ui()
        self.init_events()

    def init_ui(self):
        # ---------------- Menu Bar ----------------
        menubar = self.menuBar()
        file_menu = menubar.addMenu("File")
        
        open_video_act = QAction("Open Video...", self)
        open_video_act.setShortcut("Ctrl+O")
        open_video_act.triggered.connect(self.open_video_file)
        file_menu.addAction(open_video_act)

        import_sub_act = QAction("Import Subtitle / Speech Ranges (SRT/JSON)...", self)
        import_sub_act.triggered.connect(self.import_speech_ranges)
        file_menu.addAction(import_sub_act)

        tools_menu = menubar.addMenu("Tools")
        recognize_act = QAction("Run Speaker Attribution (not implemented)...", self)
        recognize_act.triggered.connect(self.run_speaker_attribution)
        tools_menu.addAction(recognize_act)

        # ---------------- Central Splitter Layout ----------------
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(6)

        v_splitter = QSplitter(Qt.Orientation.Vertical)

        # ส่วนบน: แนวนอน (ซ้าย = ตารางซับ, ขวา = มอนิเตอร์วิดีโอ)
        h_splitter = QSplitter(Qt.Orientation.Horizontal)

        # 1. ตาราง Subtitle Grid (ด้านซ้าย)
        self.sub_table = QTableWidget(0, 6)
        self.sub_table.setHorizontalHeaderLabels(["#", "Start Time", "End Time", "Duration", "Character", "Text"])
        self.sub_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.sub_table.horizontalHeader().setStretchLastSection(True)
        self.sub_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.sub_table.setAlternatingRowColors(True)
        h_splitter.addWidget(self.sub_table)

        # 2. มอนิเตอร์วิดีโอ (ด้านขวา)
        video_panel = QWidget()
        v_box = QVBoxLayout(video_panel)
        v_box.setContentsMargins(0, 0, 0, 0)
        
        self.video_widget = QVideoWidget()
        self.video_widget.setStyleSheet("background-color: #000000; border-radius: 4px;")
        self.player.setVideoOutput(self.video_widget)
        v_box.addWidget(self.video_widget, stretch=1)

        # แถบควบคุมใต้จอวิดีโอ
        ctrl_box = QHBoxLayout()
        self.btn_play = QPushButton("▶ Play")
        self.btn_play.clicked.connect(self.toggle_play)
        self.lbl_timecode = QLabel("00:00:00:00")
        self.lbl_timecode.setStyleSheet("font-size: 16px; font-weight: bold; color: #00FF66; padding: 0 10px;")
        
        ctrl_box.addWidget(self.btn_play)
        ctrl_box.addWidget(self.lbl_timecode)
        ctrl_box.addStretch()
        v_box.addLayout(ctrl_box)

        h_splitter.addWidget(video_panel)
        h_splitter.setStretchFactor(0, 6)  # สัดส่วนตาราง 60%
        h_splitter.setStretchFactor(1, 4)  # สัดส่วนวิดีโอ 40%
        v_splitter.addWidget(h_splitter)

        # 3. แถบด้านล่าง: Waveform Display
        waveform_container = QWidget()
        wave_layout = QVBoxLayout(waveform_container)
        wave_layout.setContentsMargins(0, 4, 0, 0)
        
        wave_header = QHBoxLayout()
        wave_header.addWidget(QLabel("🎛️ Audio Timeline Waveform"))
        self.btn_analyze = QPushButton("⚡ Run Speaker Attribution (not implemented)")
        self.btn_analyze.clicked.connect(self.run_speaker_attribution)
        wave_header.addStretch()
        wave_header.addWidget(self.btn_analyze)
        wave_layout.addLayout(wave_header)

        self.waveform_widget = WaveformWidget()
        wave_layout.addWidget(self.waveform_widget)

        v_splitter.addWidget(waveform_container)
        v_splitter.setStretchFactor(0, 7)
        v_splitter.setStretchFactor(1, 3)

        main_layout.addWidget(v_splitter)

    def init_events(self):
        # ซิงก์ตำแหน่งวิดีโอกับ Waveform
        self.player.positionChanged.connect(self.on_player_position_changed)
        self.player.durationChanged.connect(self.on_player_duration_changed)
        self.waveform_widget.position_clicked.connect(self.seek_to_position)
        self.sub_table.itemSelectionChanged.connect(self.on_table_row_selected)

    # ---------------- Media Management ----------------
    def open_video_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "เลือกไฟล์วิดีโอ", "data/input/videos", "Video Files (*.mp4 *.mkv *.avi *.mov)"
        )
        if not file_path:
            return

        self.video_path = file_path
        self.player.setSource(QUrl.fromLocalFile(file_path))

        # ตรวจสอบ FPS จาก OpenCV
        cap = cv2.VideoCapture(file_path)
        self.current_fps = cap.get(cv2.CAP_PROP_FPS) or 24.0
        cap.release()

        # The waveform feature is reusable; VAD will later use src/audio/audio_extract.py.
        self.extract_waveform_fast(file_path)
        self.btn_play.setText("▶ Play")

    def extract_waveform_fast(self, video_path):
        """Extract a temporary mono WAV for the waveform and report FFmpeg failures."""
        output_dir = os.path.abspath(os.path.join("data", "output"))
        os.makedirs(output_dir, exist_ok=True)
        temp_wav = os.path.join(output_dir, "temp_desktop_audio.wav")
        cmd = [
            "ffmpeg", "-y", "-i", video_path,
            "-vn", "-ac", "1", "-ar", "8000",
            temp_wav
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            self.audio_wav_path = None
            error_line = result.stderr.strip().splitlines()[-1] if result.stderr.strip() else "ไม่ทราบสาเหตุ"
            QMessageBox.warning(self, "อ่านเสียงไม่สำเร็จ", f"FFmpeg ไม่สามารถสกัดเสียงได้: {error_line}")
            return
        self.audio_wav_path = temp_wav

    def on_player_duration_changed(self, duration_ms):
        if self.audio_wav_path and os.path.exists(self.audio_wav_path):
            self.waveform_widget.load_audio(self.audio_wav_path, duration_ms)

    def on_player_position_changed(self, pos_ms):
        self.waveform_widget.set_position(pos_ms)
        # คำนวณ SMPTE Timecode: HH:MM:SS:FF
        total_seconds = pos_ms / 1000.0
        total_frames = int(total_seconds * self.current_fps)
        hrs = int(total_seconds // 3600)
        mins = int((total_seconds % 3600) // 60)
        secs = int(total_seconds % 60)
        frames = int(total_frames % self.current_fps)
        self.lbl_timecode.setText(f"{hrs:02d}:{mins:02d}:{secs:02d}:{frames:02d}")

    def toggle_play(self):
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
            self.btn_play.setText("▶ Play")
        else:
            self.player.play()
            self.btn_play.setText("⏸ Pause")

    def seek_to_position(self, pos_ms):
        """กระโดดไปตามพิกัดที่คลิกบน Waveform แบบ Zero-Latency"""
        self.player.setPosition(pos_ms)

    # ---------------- Workflow Decoupling ----------------
    def import_speech_ranges(self):
        """Reserved for a real SRT/JSON parser in src/io/subtitle_io.py."""

        # Disabled legacy sample data: it made the Import action look successful without reading a file.
        # if not self.video_path:
        #     QMessageBox.warning(self, "แจ้งเตือน", "กรุณาเปิดไฟล์วิดีโอก่อนนำเข้าช่วงบทพูด")
        #     return
        # sample_intervals = [
        #     {"start": 1000, "end": 4000, "char": "Unknown", "text": "สวัสดีครับทุกคน"},
        #     {"start": 5500, "end": 8500, "char": "Unknown", "text": "วันนี้เราจะมาคุยเรื่องงานกัน"},
        #     {"start": 10000, "end": 14000, "char": "Unknown", "text": "เตรียมตัวให้พร้อมสำหรับการทดสอบ"},
        # ]
        # self.sub_table.setRowCount(0)
        # regions = []
        # palette = [QColor(255, 82, 82, 90), QColor(105, 240, 174, 90), QColor(255, 215, 64, 90)]
        # for i, item in enumerate(sample_intervals):
        #     self.sub_table.insertRow(i)
        #     dur = (item["end"] - item["start"]) / 1000.0
        #     self.sub_table.setItem(i, 0, QTableWidgetItem(str(i + 1)))
        #     self.sub_table.setItem(i, 1, QTableWidgetItem(self.format_ms(item["start"])))
        #     self.sub_table.setItem(i, 2, QTableWidgetItem(self.format_ms(item["end"])))
        #     self.sub_table.setItem(i, 3, QTableWidgetItem(f"{dur:.2f}s"))
        #     self.sub_table.setItem(i, 4, QTableWidgetItem(item["char"]))
        #     self.sub_table.setItem(i, 5, QTableWidgetItem(item["text"]))
        #     color = palette[i % len(palette)]
        #     regions.append((item["start"], item["end"], f"Line {i + 1}", color))
        # self.waveform_widget.set_regions(regions)
        # QMessageBox.information(self, "สำเร็จ", f"นำเข้าช่วงเวลาบทพูดเรียบร้อยแล้ว {len(sample_intervals)} บรรทัด")

        QMessageBox.information(
            self,
            "ยังไม่ได้ติดตั้ง Import",
            "ให้เขียน parser ใน src/io/subtitle_io.py แล้วเชื่อมเข้าปุ่มนี้; ตอนนี้โปรแกรมจะไม่สร้างซับไตเติลตัวอย่างปลอม",
        )

    def run_speaker_attribution(self):
        """Reserved for the real multi-frame audio-visual attribution pipeline."""
        if not self.video_path or self.sub_table.rowCount() == 0:
            QMessageBox.warning(self, "แจ้งเตือน", "ต้องเปิดวิดีโอและมีรายการในตารางซับไตเติลก่อนประมวลผล")
            return

        # Disabled legacy implementation: it sampled only the first frame of each line.
        # cap = cv2.VideoCapture(self.video_path)
        # for row in range(self.sub_table.rowCount()):
        #     start_str = self.sub_table.item(row, 1).text()
        #     start_ms = self.parse_ms(start_str)
        #     target_frame = int((start_ms / 1000.0) * self.current_fps)
        #     cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)
        #     ret, frame = cap.read()
        #     if ret:
        #         features = extract_character_features(frame)
        #         if features:
        #             char_name = f"Character_{row + 1:02d}"
        #             self.sub_table.setItem(row, 4, QTableWidgetItem(char_name))
        # cap.release()

        # TODO: Call pipeline/speaker_attribution.py after subtitle import, tracking, VAD, and scoring exist.
        QMessageBox.information(
            self,
            "ยังไม่ได้ติดตั้ง Speaker Attribution",
            "โค้ดเดิมถูกปิด เพราะตั้งชื่อ Character_XX โดยไม่เปรียบเทียบฐานข้อมูลหรือยืนยันจากเสียง",
        )

    def on_table_row_selected(self):
        """คลิกบรรทัดในตาราง -> วิดีโอกระโดดไปที่เวลาเริ่มต้นของประโยคนั้นทันที"""
        selected_rows = self.sub_table.selectionModel().selectedRows()
        if selected_rows:
            row = selected_rows[0].row()
            start_str = self.sub_table.item(row, 1).text()
            self.player.setPosition(self.parse_ms(start_str))

    # Helper Format Time
    def format_ms(self, ms):
        t = QTime(0, 0, 0).addMSecs(ms)
        return t.toString("hh:mm:ss.zzz")

    def parse_ms(self, time_str):
        t = QTime.fromString(time_str, "hh:mm:ss.zzz")
        return (t.hour() * 3600 + t.minute() * 60 + t.second()) * 1000 + t.msec()

# =====================================================================
# Main Application Entry Point
# =====================================================================
if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = SubtitleEditStudio()
    window.show()
    sys.exit(app.exec())
