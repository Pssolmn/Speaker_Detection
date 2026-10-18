"""หน้าต่างตรวจผล: เลือกวิดีโอ/ซับ → worker วิเคราะห์ → ตรวจชื่อ → Export.

อ่านไฟล์นี้เพื่อดูการต่อระบบ ส่วนสูตรภาพ/เสียงอยู่ใน vision/audio/pipeline
widget เปลี่ยนค่าเฉพาะบน UI thread; worker ส่งผลผ่าน Qt signal
"""

import json
import sys
from collections import OrderedDict
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

import cv2
from PyQt6.QtCore import Qt, QSignalBlocker, QUrl
from PyQt6.QtGui import QAction, QColor
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QTableWidget, QTableWidgetItem, QPushButton, QLabel, QFileDialog,
    QHeaderView, QMessageBox, QAbstractItemView, QProgressBar, QTextEdit,
    QTabWidget, QSlider, QLineEdit,
)
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtMultimediaWidgets import QVideoWidget

from src.core import config
from src.core.models import AttributionResult
from src.audio.vad import segments_from_speech_ranges
from src.io.result_export import (
    effective_character, export_labelled_srt, export_results_json,
    format_srt_time, load_results_json,
)
from src.io.subtitle_io import parse_srt
from src.ui.widgets import DetectionPreview, WaveformWidget
from src.ui.table_safety import replace_table_rows
from src.ui.worker import AnalysisWorker
from src.vision.face_detect import DEFAULT_FACE_MODEL_PATH


class SubtitleEditStudio(QMainWindow):
    """เก็บสถานะ session แยกจาก widget เพื่อ export และทดสอบได้โดยตรง."""

    HEADERS = ["ID", "Start", "End", "Script", "Detected", "Manual", "Score", "Status", "Text"]
    MANUAL_COLUMN = 5

    def __init__(self):
        super().__init__()
        from src.ui.mac_accessibility import install_guard
        try:
            self.accessibility_status = install_guard()
        except Exception as error:
            # เครื่องที่ไม่มี Xcode Command Line Tools หรือ Qt ABI ไม่ตรงต้องยังเปิดแอปได้
            self.accessibility_status = f"guard-failed: {error}"
        self.setWindowTitle("Anime Speaker Studio — review workspace")
        self.resize(1440, 920)
        self.video_path = None
        self.subtitle_path = None
        self.segments = []
        self.results = {}
        self.audio = None
        self.worker = None
        self._dirty = False
        self._closing = False
        # WAV เป็นไฟล์ชั่วคราวของ session; ไม่ทับ waveform/input ของผู้ใช้
        self._temporary = TemporaryDirectory(prefix="speaker-detection-")
        self._previews = OrderedDict()  # จำกัดภาพ cache ไม่ให้โตตามจำนวนซับ
        self.player = QMediaPlayer(self)
        self.audio_output = QAudioOutput(self)
        self.player.setAudioOutput(self.audio_output)
        self.init_ui()
        self.init_events()
        self._set_busy(False)

    def init_ui(self):
        self.setStyleSheet("""
            QMainWindow, QWidget { background: #151e29; color: #e3ebf4; font-size: 12px; }
            QPushButton { background: #263a4d; border: 1px solid #3a5269; border-radius: 5px; padding: 8px 12px; }
            QPushButton:hover { background: #33516a; }
            QPushButton:disabled { color: #697c8c; background: #1c2936; }
            QLineEdit, QTextEdit, QTableWidget { background: #101923; border: 1px solid #2c4053; selection-background-color: #28566b; }
            QHeaderView::section { background: #223345; padding: 7px; border: 0; }
            QTabBar::tab { padding: 8px 18px; background: #223345; }
            QTabBar::tab:selected { background: #33516a; }
            QProgressBar { border: 1px solid #30465b; border-radius: 4px; text-align: center; }
            QProgressBar::chunk { background: #258a80; }
        """)
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        title = QLabel("ANIME SPEAKER STUDIO")
        title.setStyleSheet("font-size: 22px; font-weight: 700; color: #62dbc5; padding: 4px 0;")
        layout.addWidget(title)
        layout.addWidget(QLabel("1 Open video   →   2 Import SRT   →   3 Preview / Analyze   →   4 Review Manual names   →   5 Export"))

        toolbar = QHBoxLayout()
        self.btn_workspace = QPushButton("Project workspace")
        self.btn_workspace.clicked.connect(self.open_project_workspace)
        toolbar.addWidget(self.btn_workspace)
        self.btn_open = QPushButton("Open video")
        self.btn_import = QPushButton("Import SRT / JSON")
        self.btn_preview = QPushButton("Preview frame")
        self.btn_selected = QPushButton("Analyze selected")
        self.btn_analyze = QPushButton("Analyze all")
        self.btn_cancel = QPushButton("Cancel")
        self.btn_export_json = QPushButton("Export JSON")
        self.btn_export_srt = QPushButton("Export SRT")
        for button in (self.btn_open, self.btn_import, self.btn_preview, self.btn_selected,
                       self.btn_analyze, self.btn_cancel, self.btn_export_json, self.btn_export_srt):
            toolbar.addWidget(button)
        toolbar.addStretch()
        layout.addLayout(toolbar)

        settings = QHBoxLayout()
        settings.addWidget(QLabel("Reference DB"))
        self.database_edit = QLineEdit(str(config.DATABASE_PATH))
        self.btn_database = QPushButton("Browse…")
        settings.addWidget(self.database_edit, 1)
        settings.addWidget(self.btn_database)
        settings.addWidget(QLabel("Anime weights"))
        self.model_edit = QLineEdit(str(DEFAULT_FACE_MODEL_PATH))
        self.btn_model = QPushButton("Browse…")
        settings.addWidget(self.model_edit, 1)
        settings.addWidget(self.btn_model)
        layout.addLayout(settings)
        self.media_label = QLabel("ยังไม่ได้เลือกวิดีโอ")
        self.media_label.setWordWrap(True)
        layout.addWidget(self.media_label)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.sub_table = QTableWidget(0, len(self.HEADERS))
        self.sub_table.setHorizontalHeaderLabels(self.HEADERS)
        self.sub_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.sub_table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.sub_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.sub_table.horizontalHeader().setStretchLastSection(True)
        for index, width in enumerate((40, 100, 100, 78, 94, 94, 52, 106, 240)):
            self.sub_table.setColumnWidth(index, width)
        self.sub_table.verticalHeader().setDefaultSectionSize(42)
        splitter.addWidget(self.sub_table)

        self.tabs = QTabWidget()
        player_page = QWidget()
        player_layout = QVBoxLayout(player_page)
        self.video_widget = QVideoWidget()
        self.video_widget.setMinimumSize(320, 200)
        self.player.setVideoOutput(self.video_widget)
        player_layout.addWidget(self.video_widget, 1)
        controls = QHBoxLayout()
        self.btn_play = QPushButton("Play")
        self.lbl_timecode = QLabel("00:00:00,000")
        controls.addWidget(self.btn_play)
        self.seek_slider = QSlider(Qt.Orientation.Horizontal)
        controls.addWidget(self.seek_slider, 1)
        controls.addWidget(self.lbl_timecode)
        player_layout.addLayout(controls)
        self.tabs.addTab(player_page, "Video")
        self.preview_widget = DetectionPreview()
        self.tabs.addTab(self.preview_widget, "Detection preview")
        self.details = QTextEdit()
        self.details.setReadOnly(True)
        self.details.setPlainText("เลือกบรรทัดที่วิเคราะห์แล้วเพื่อดูอันดับตัวละครและเหตุผล")
        self.tabs.addTab(self.details, "Evidence")
        splitter.addWidget(self.tabs)
        splitter.setSizes([870, 530])
        layout.addWidget(splitter, 1)

        self.audio_label = QLabel("Audio: ยังไม่ได้ตรวจ · RMS energy อาจรวมเพลง/เอฟเฟกต์")
        layout.addWidget(self.audio_label)
        self.waveform_widget = WaveformWidget()
        self.waveform_widget.setMaximumHeight(160)
        layout.addWidget(self.waveform_widget)
        bottom = QHBoxLayout()
        self.progress_bar = QProgressBar()
        self.progress_bar.setMaximumWidth(250)
        bottom.addWidget(self.progress_bar)
        self.progress_label = QLabel("Ready — คะแนนเป็นความคล้าย/หลักฐาน ไม่ใช่ความน่าจะเป็น")
        self.progress_label.setWordWrap(True)
        bottom.addWidget(self.progress_label, 1)
        layout.addLayout(bottom)

        menu = self.menuBar().addMenu("File")
        self.open_action = QAction("Open video…", self)
        self.open_action.setShortcut("Ctrl+O")
        self.open_action.triggered.connect(self.open_video_file)
        menu.addAction(self.open_action)
        self.import_action = QAction("Import SRT / analysis JSON…", self)
        self.import_action.triggered.connect(self.import_speech_ranges)
        menu.addAction(self.import_action)
        tools_menu = self.menuBar().addMenu("Tools")
        self.audio_ranges_action = QAction("Create segments from audio energy…", self)
        self.audio_ranges_action.triggered.connect(self.use_audio_ranges)
        tools_menu.addAction(self.audio_ranges_action)
        self.retry_audio_action = QAction("Prepare audio again", self)
        self.retry_audio_action.triggered.connect(self.retry_audio)
        tools_menu.addAction(self.retry_audio_action)

    def init_events(self):
        self.btn_open.clicked.connect(self.open_video_file)
        self.btn_import.clicked.connect(self.import_speech_ranges)
        self.btn_preview.clicked.connect(self.preview_frame)
        self.btn_selected.clicked.connect(lambda: self.run_speaker_attribution(selected_only=True))
        self.btn_analyze.clicked.connect(lambda: self.run_speaker_attribution(selected_only=False))
        self.btn_cancel.clicked.connect(self.cancel_analysis)
        self.btn_export_json.clicked.connect(lambda: self.export_results("json"))
        self.btn_export_srt.clicked.connect(lambda: self.export_results("srt"))
        self.btn_database.clicked.connect(lambda: self.choose_file(self.database_edit, "PKL (*.pkl)"))
        self.btn_model.clicked.connect(lambda: self.choose_file(self.model_edit, "Weights (*.pt)"))
        self.btn_play.clicked.connect(self.toggle_play)
        self.player.positionChanged.connect(self.on_player_position_changed)
        self.player.durationChanged.connect(self.on_player_duration_changed)
        self.player.errorOccurred.connect(lambda error, message: self.progress_label.setText(message))
        self.player.playbackStateChanged.connect(
            lambda state: self.btn_play.setText("Pause" if state == QMediaPlayer.PlaybackState.PlayingState else "Play"))
        self.waveform_widget.position_clicked.connect(self.player.setPosition)
        self.seek_slider.sliderMoved.connect(self.player.setPosition)
        self.sub_table.itemSelectionChanged.connect(self.on_table_row_selected)
        self.sub_table.itemChanged.connect(self.on_item_changed)

    def choose_file(self, edit, pattern):
        path, _ = QFileDialog.getOpenFileName(self, "Select file", edit.text(), pattern)
        if path:
            edit.setText(path)

    def _is_busy(self):
        return self.worker is not None

    def _set_busy(self, busy):
        self.btn_workspace.setEnabled(not busy)
        for widget in (self.btn_open, self.btn_import, self.database_edit, self.model_edit,
                       self.btn_database, self.btn_model):
            widget.setEnabled(not busy)
        self.open_action.setEnabled(not busy)
        self.import_action.setEnabled(not busy)
        self.audio_ranges_action.setEnabled(not busy and self.audio is not None and self.audio["ranges"] is not None)
        self.retry_audio_action.setEnabled(not busy and bool(self.video_path))
        self.btn_preview.setEnabled(not busy and bool(self.video_path))
        can_analyze = not busy and bool(self.video_path) and bool(self.segments)
        self.btn_selected.setEnabled(can_analyze)
        self.btn_analyze.setEnabled(can_analyze)
        self.btn_cancel.setEnabled(busy)
        self.btn_export_json.setEnabled(bool(self.segments))
        self.btn_export_srt.setEnabled(bool(self.segments))
        self.btn_play.setEnabled(bool(self.video_path))

    def open_project_workspace(self):
        """ส่ง session เดิมเข้าหน้ารวมอย่างชัดเจน ไม่สร้าง state คู่ที่แอบ sync กัน."""
        from src.ui.workspace_window import WorkspaceWindow
        if getattr(self, "project_window", None) is not None and self.project_window.isVisible():
            self.project_window.raise_()
            self.project_window.activateWindow()
            return
        root = None
        if self.video_path:
            root = QFileDialog.getExistingDirectory(self,
                "เลือก Workspace ปลายทาง หรือโฟลเดอร์ว่างใหม่ — ส่งซับและชื่อแก้มือเข้าไป")
            if not root:
                return
        window = WorkspaceWindow()  # ไม่เป็น child ที่ถูกทำลายระหว่าง worker ยังรัน
        try:
            if root:
                window.load_workspace(root, create=not (Path(root) / "workspace.sqlite3").exists())
                window.start_job("legacy", self.video_path, segments=[replace(item) for item in self.segments],
                    manual_labels={key: value.manual_character for key, value in self.results.items() if value.manual_character})
        except Exception as error:
            window.close()
            QMessageBox.warning(self, "ย้ายเข้า Workspace ไม่สำเร็จ", str(error))
            return
        self.player.pause()
        self.project_window = window
        window.show()
        self.progress_label.setText("ทำงานต่อในหน้ารวมได้เลย · เก็บ session เดิมไว้ · ผล AI แบบ reference เก่าไม่ถูกยืนยันอัตโนมัติ")

    def open_video_file(self):
        if self._is_busy():
            return
        path, _ = QFileDialog.getOpenFileName(self, "Open video", str(config.INPUT_VIDEOS_DIR),
                                             "Video (*.mp4 *.mkv *.avi *.mov *.webm)")
        if path and self._confirm_discard():
            self.load_video(path)

    def load_video(self, path):
        """จุดเข้าโหลดวิดีโอที่เรียกจาก tests ได้โดยไม่เปิด file dialog."""
        if self._is_busy():
            return
        self.video_path = str(Path(path).resolve())
        self.subtitle_path = None
        self.audio = None
        self._previews.clear()
        self.preview_widget.clear()
        self.set_segments([])
        self.media_label.setText(self.video_path)
        self.player.setSource(QUrl.fromLocalFile(self.video_path))
        self.waveform_widget.set_audio([], 0)
        self.audio_label.setText("Audio: กำลังเตรียม waveform และช่วงพลังงาน…")
        worker = AnalysisWorker("prepare", self.video_path,
                                wav_path=Path(self._temporary.name) / "analysis.wav", parent=self)
        self.start_worker(worker)

    def import_speech_ranges(self):
        if self._is_busy():
            return
        path, _ = QFileDialog.getOpenFileName(self, "Import subtitles / session", str(config.INPUT_SUBTITLES_DIR),
                                             "Subtitles / analysis (*.srt *.json)")
        if not path or not self._confirm_discard():
            return
        try:
            self.load_subtitles(path)
        except (OSError, ValueError, TypeError) as error:
            QMessageBox.warning(self, "Import failed", str(error))

    def use_audio_ranges(self):
        if self._is_busy() or self.audio is None or not self._confirm_discard():
            return
        try:
            segments = segments_from_speech_ranges(self.audio["ranges"])
            if not segments:
                raise ValueError("No audio energy ranges found")
            self.subtitle_path = None
            self._previews.clear()
            self.preview_widget.clear()
            self.set_segments(segments)
            self._dirty = True
            self.progress_label.setText("Created energy segments without transcript; music/noise may be included")
        except ValueError as error:
            QMessageBox.information(self, "Audio segments", str(error))

    def retry_audio(self):
        if not self._is_busy() and self.video_path:
            self.audio = None
            self.start_worker(AnalysisWorker("prepare", self.video_path,
                              wav_path=Path(self._temporary.name) / "analysis.wav", parent=self))

    def load_subtitles(self, path):
        """SRT เป็นต้นฉบับ; JSON ใช้คืน session รวมชื่อแก้มือและหลักฐาน."""
        path = Path(path)
        if path.suffix.lower() == ".json":
            segments, results = load_results_json(path)
        else:
            segments, results = parse_srt(path), []
        if not segments:
            raise ValueError("No subtitle segments found")
        if len({segment.id for segment in segments}) != len(segments):
            raise ValueError("Subtitle IDs must be unique")
        self.subtitle_path = path.resolve()
        self._previews.clear()
        self.preview_widget.clear()
        self.set_segments(segments, results)
        self.media_label.setText(f"{self.video_path or 'No video'}   |   {path.name} · {len(segments)} segments")

    def set_segments(self, segments, results=()):
        self.segments = list(segments)
        self.results = {result.segment_id: result for result in results}
        self._row_by_id = {segment.id: row for row, segment in enumerate(self.segments)}
        with QSignalBlocker(self.sub_table):
            replace_table_rows(self.sub_table, len(self.segments))
            for row, segment in enumerate(self.segments):
                self._render_row(row, segment)
        self._dirty = False
        self.details.clear()
        self.refresh_regions()
        self._set_busy(self._is_busy())

    def _render_row(self, row, segment):
        result = self.results.get(segment.id, AttributionResult(segment.id))
        values = [str(segment.id), format_srt_time(segment.start_ms), format_srt_time(segment.end_ms),
                  segment.script_character or "", result.detected_character if result.status != "UNPROCESSED" else "",
                  result.manual_character or "", f"{result.confidence:.3f}" if result.status != "UNPROCESSED" else "",
                  result.status, segment.text]
        with QSignalBlocker(self.sub_table):
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setToolTip(value)
                if column != self.MANUAL_COLUMN:
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                else:
                    item.setToolTip("ชื่อที่คุณยืนยันเอง; Run ใหม่จะไม่เขียนทับช่องนี้")
                if column == 7:
                    color = "#ffbf69" if result.status in {"UNKNOWN", "SCRIPT_CONFLICT", "ERROR"} else "#62dbc5"
                    item.setForeground(QColor(color))
                self.sub_table.setItem(row, column, item)
            self.sub_table.resizeRowToContents(row)

    def on_item_changed(self, item):
        if item.column() != self.MANUAL_COLUMN:
            return
        segment = self.segments[item.row()]
        result = self.results.get(segment.id, AttributionResult(segment.id))
        self.results[segment.id] = replace(result, manual_character=item.text().strip() or None)
        self._dirty = True
        self.refresh_regions()

    def run_speaker_attribution(self, selected_only=False):
        if self._is_busy() or not self.video_path or not self.segments:
            return
        segments = self.segments
        if selected_only:
            rows = sorted(index.row() for index in self.sub_table.selectionModel().selectedRows())
            if not rows:
                QMessageBox.information(self, "Select a subtitle", "เลือกอย่างน้อยหนึ่งบรรทัดก่อน Analyze selected")
                return
            segments = [self.segments[row] for row in rows]
        self.player.pause()
        worker = AnalysisWorker("analyze", self.video_path, segments=segments, audio=self.audio,
                                database_path=self.database_edit.text(), model_path=self.model_edit.text(), parent=self)
        self.start_worker(worker)

    def preview_frame(self):
        if self._is_busy() or not self.video_path:
            return
        self.player.pause()
        timestamp = max(0, self.player.position())
        if self.player.duration() > 0:
            timestamp = min(timestamp, self.player.duration() - 1)
        worker = AnalysisWorker("preview", self.video_path, timestamp_ms=timestamp,
                                database_path=self.database_edit.text(), model_path=self.model_edit.text(), parent=self)
        self.start_worker(worker)

    def start_worker(self, worker):
        self.worker = worker
        self._set_busy(True)
        self.progress_bar.setRange(0, 0)
        worker.progress.connect(self.on_progress)
        worker.audio_ready.connect(self.on_audio_ready)
        worker.result_ready.connect(self.on_result_ready)
        worker.preview_ready.connect(self.on_preview_ready)
        worker.completed.connect(self.progress_label.setText)
        worker.failed.connect(self.on_worker_failed)
        worker.finished.connect(self.on_worker_finished)
        worker.start()

    def on_progress(self, completed, total, message):
        self.progress_bar.setRange(0, total)
        self.progress_bar.setValue(completed)
        self.progress_label.setText(message)

    def on_audio_ready(self, audio):
        self.audio = audio
        duration = self.player.duration() or audio["duration_ms"]
        self.waveform_widget.set_audio(audio["peaks"], duration)
        label = audio["warning"] or f"RMS energy: {len(audio['ranges'])} ranges · อาจรวมเพลง/เอฟเฟกต์"
        self.audio_label.setText(label)

    def on_result_ready(self, result):
        if result.segment_id not in self._row_by_id:
            return
        previous = self.results.get(result.segment_id)
        # อ่านชื่อแก้มือล่าสุดบน UI thread แม้ผู้ใช้แก้ระหว่าง worker กำลังวิ่ง
        if previous is not None:
            result = replace(result, manual_character=previous.manual_character)
        self.results[result.segment_id] = result
        row = self._row_by_id[result.segment_id]
        self._render_row(row, self.segments[row])
        self._dirty = True
        self.refresh_regions()
        self.show_evidence(result.segment_id)

    def on_preview_ready(self, payload):
        self.preview_widget.set_preview(payload)
        self.tabs.setCurrentWidget(self.preview_widget)
        segment_id = payload.get("segment_id")
        if segment_id is not None:
            self._previews[segment_id] = payload
            self._previews.move_to_end(segment_id)
            while len(self._previews) > 16:
                self._previews.popitem(last=False)

    def on_worker_failed(self, message):
        self.progress_label.setText(f"Error: {message}")
        if not self._closing:
            QMessageBox.warning(self, "Analysis failed", message)

    def on_worker_finished(self):
        worker = self.worker
        self.worker = None
        cancelled = worker.isInterruptionRequested() if worker is not None else False
        if worker is not None and worker.mode == "prepare" and self.audio is None:
            self.audio_label.setText("Audio unavailable — ใช้ Tools → Prepare audio again เพื่อลองใหม่")
        if worker is not None:
            worker.deleteLater()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0 if cancelled else 100)
        self._set_busy(False)
        if self._closing:
            self._closing = False
            self.close()

    def cancel_analysis(self):
        if self.worker is not None:
            self.worker.requestInterruption()
            self.btn_cancel.setEnabled(False)
            self.progress_label.setText("Cancelling after the current operation…")

    def on_table_row_selected(self):
        rows = self.sub_table.selectionModel().selectedRows()
        if not rows:
            return
        segment = self.segments[rows[0].row()]
        self.player.setPosition(segment.start_ms)
        self.show_evidence(segment.id)
        if segment.id in self._previews:
            self.preview_widget.set_preview(self._previews[segment.id])

    def show_evidence(self, segment_id):
        result = self.results.get(segment_id)
        if result is None:
            self.details.setPlainText("ยังไม่ได้วิเคราะห์บรรทัดนี้")
            return
        candidates = "\n".join(
            f"track {candidate.track_id} · {candidate.character_name}: visual={candidate.visual_score:.3f}, "
            f"motion={candidate.active_speaker_score}, combined={candidate.final_score}"
            for candidate in result.candidates[:20])
        # boxes เก็บใน JSON เต็ม; หน้ารายละเอียดตัดออกให้เหตุผลและคะแนนอ่านง่าย
        evidence = {key: value for key, value in result.evidence.items() if key != "frames"}
        self.details.setPlainText(f"{result.status} · {result.detected_character}\n\n{candidates}\n\n"
                                  + json.dumps(evidence, ensure_ascii=False, indent=2))

    def refresh_regions(self):
        regions = []
        for segment in self.segments:
            result = self.results.get(segment.id, AttributionResult(segment.id))
            name = effective_character(segment, result) or "unreviewed"
            color = QColor(40, 135, 120, 35) if result.manual_character else QColor(70, 100, 145, 30)
            regions.append((segment.start_ms, segment.end_ms, name, color))
        self.waveform_widget.set_regions(regions)

    def export_results(self, kind):
        if not self.segments:
            return False
        suffix = ".analysis.json" if kind == "json" else ".labelled.srt"
        stem = self.subtitle_path.stem if self.subtitle_path else "analysis"
        path, _ = QFileDialog.getSaveFileName(self, "Export reviewed results",
                                             str(config.OUTPUT_DIR / (stem + suffix)),
                                             "JSON (*.json)" if kind == "json" else "SRT (*.srt)")
        if not path:
            return False
        try:
            inputs = [self.video_path, self.subtitle_path, self.database_edit.text(), self.model_edit.text()]
            if Path(path).resolve() in {Path(value).resolve() for value in inputs if value}:
                raise ValueError("Choose an output different from video/subtitle/reference/model inputs")
            exporter = export_results_json if kind == "json" else export_labelled_srt
            target = exporter(self.segments, self.results.values(), path, source_path=self.subtitle_path)
            self.progress_label.setText(f"Saved: {target}")
            # SRT ไม่เก็บ evidence/session; จึงยังถือว่ามีงานค้างจนกว่าจะบันทึก JSON
            if kind == "json":
                self._dirty = False
            return True
        except (OSError, ValueError, TypeError) as error:
            QMessageBox.warning(self, "Export failed", str(error))
            return False

    def _confirm_discard(self):
        if not self._dirty:
            return True
        answer = QMessageBox.question(
            self, "Unsaved review", "มีผลตรวจหรือชื่อแก้มือที่ยังไม่ได้บันทึก ต้องการบันทึก JSON ก่อนหรือไม่?",
            QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save)
        if answer == QMessageBox.StandardButton.Save:
            return self.export_results("json")
        return answer == QMessageBox.StandardButton.Discard

    def toggle_play(self):
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else:
            self.tabs.setCurrentIndex(0)
            self.player.play()

    def on_player_position_changed(self, position_ms):
        self.lbl_timecode.setText(format_srt_time(position_ms))
        self.waveform_widget.set_position(position_ms)
        with QSignalBlocker(self.seek_slider):
            self.seek_slider.setValue(position_ms)

    def on_player_duration_changed(self, duration_ms):
        self.seek_slider.setRange(0, max(0, duration_ms))
        self.waveform_widget.duration_ms = duration_ms
        self.waveform_widget.update()

    def closeEvent(self, event):
        if self._is_busy():
            self._closing = True
            self.cancel_analysis()
            event.ignore()  # รอ finished ก่อนทำลาย QThread/ลบ WAV ที่กำลังใช้
            return
        if not self._confirm_discard():
            event.ignore()
            return
        self.player.stop()
        self._temporary.cleanup()
        event.accept()


def main():
    """ทั้ง src.main และ src.workspace_app เปิด studio เดียวกันเป็นค่าเริ่มต้น.

    --legacy-reference เก็บโหมด PKL/สีผมเดิมไว้เพื่อเปิดงานเก่าโดยไม่ลบทิ้ง.
    """
    if "--legacy-reference" not in sys.argv:
        from src.workspace_app import main as workspace_main
        return workspace_main()
    cv2.setNumThreads(config.CV_THREADS)
    app = QApplication(sys.argv)
    window = SubtitleEditStudio()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
