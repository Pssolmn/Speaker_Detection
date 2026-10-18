"""ทำงานหนักใน QThread แล้วส่งผลผ่าน signal; ห้ามแก้ widget ใน run()."""

from pathlib import Path

import cv2
from PyQt6.QtCore import QThread, pyqtSignal

from src.core import config
from src.core.control import AnalysisCancelled, check_cancel
from src.core.models import SubtitleSegment
from src.pipeline.video_analysis import analyze_segments, prepare_audio
from src.pipeline.visual_identification import VisualIdentifier
from src.vision.face_detect import detect_faces
from src.vision.video_sampler import sample_segment_frames


class AnalysisWorker(QThread):
    progress = pyqtSignal(int, int, str)
    result_ready = pyqtSignal(object)
    preview_ready = pyqtSignal(object)
    audio_ready = pyqtSignal(object)
    completed = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, mode, video_path, *, segments=(), database_path=config.DATABASE_PATH,
                 model_path=None, audio=None, wav_path=None, timestamp_ms=0, parent=None):
        super().__init__(parent)
        self.mode, self.video_path = mode, str(video_path)
        self.segments = list(segments)
        self.database_path, self.model_path = Path(database_path), model_path
        self.audio, self.wav_path = audio, wav_path
        self.timestamp_ms = timestamp_ms

    def run(self):
        """requestInterruption ไม่ฆ่า thread; check_cancel ตรวจระหว่างงานย่อยแทน"""
        cancel = self.isInterruptionRequested
        try:
            cv2.setNumThreads(config.CV_THREADS)
            check_cancel(cancel)
            if self.mode == "prepare":
                self.progress.emit(0, 0, "Preparing waveform / RMS energy…")
                audio = prepare_audio(self.video_path, self.wav_path, cancel)
                check_cancel(cancel)
                self.audio_ready.emit(audio)
            else:
                identifier = VisualIdentifier.from_database(self.database_path)
                if not Path(self.model_path).is_file():
                    raise FileNotFoundError(f"Anime-face weights not found: {self.model_path}")
                if self.mode == "preview":
                    self._preview(identifier, cancel)
                else:
                    analyze_segments(self.video_path, self.segments, identifier, self.audio,
                                     model_path=self.model_path, cancel=cancel,
                                     on_result=self.result_ready.emit, on_preview=self.preview_ready.emit,
                                     on_progress=self.progress.emit)
            self.completed.emit("Completed")
        except AnalysisCancelled:
            self.completed.emit("Cancelled — completed results retained")
        except Exception as error:
            self.failed.emit(f"{type(error).__name__}: {error}")

    def _preview(self, identifier, cancel):
        self.progress.emit(0, 0, "Detecting faces in the selected frame…")
        segment = SubtitleSegment(0, self.timestamp_ms, self.timestamp_ms + 1, "preview")
        samples = sample_segment_frames(self.video_path, segment, max_frames=1, cancel=cancel)
        if not samples:
            raise OSError("No readable frame at the selected position")
        sample = samples[0]
        detections = detect_faces(sample.frame, model_path=self.model_path)
        boxes = []
        for index, detection in enumerate(detections, start=1):
            check_cancel(cancel)
            candidates = identifier.identify_portrait(sample.frame, bbox=detection.box)
            top = candidates[0] if candidates else None
            boxes.append({"track_id": index, "box": detection.box,
                          "name": top.character_name if top else "UNKNOWN",
                          "visual_score": top.visual_score if top else None,
                          "active_speaker_score": None})
        self.preview_ready.emit({"segment_id": None, "timestamp_ms": sample.timestamp_ms,
                                 "frame": sample.frame, "boxes": boxes})
