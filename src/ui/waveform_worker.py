"""เตรียม waveform เบา ๆ นอก UI thread; ไม่ใช่การจำแนกผู้พูดหรือสแกน AI."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory

from PyQt6.QtCore import QThread, pyqtSignal

from src.audio.audio_extract import extract_audio
from src.audio.vad import waveform_peaks
from src.core.control import AnalysisCancelled, check_cancel


class WaveformWorker(QThread):
    ready = pyqtSignal(str, object)
    failed = pyqtSignal(str, str)

    def __init__(self, media_id, source, cache_dir, parent=None):
        super().__init__(parent)
        self.media_id, self.source, self.cache_dir = media_id, source, Path(cache_dir)

    def run(self):
        try:
            check_cancel(self.isInterruptionRequested)
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            cache = self.cache_dir / f"{self.media_id}-v1.json"
            if cache.is_file():
                try:
                    payload = json.loads(cache.read_text(encoding="utf-8"))
                    if (not isinstance(payload["peaks"], list) or len(payload["peaks"]) > 2000
                            or not isinstance(payload["duration_ms"], int) or payload["duration_ms"] <= 0
                            or any(not isinstance(value, (int, float)) or not 0 <= value <= 1
                                   for value in payload["peaks"])):
                        raise ValueError("Invalid waveform cache")
                    self.ready.emit(self.media_id, payload)
                    return
                except (ValueError, KeyError, TypeError):
                    pass  # cache ที่เสียสร้างใหม่ได้ ไม่แตะเสียงต้นฉบับ/ผล AI
            with TemporaryDirectory(prefix="waveform-", dir=self.cache_dir) as scratch:
                wav = extract_audio(self.source, Path(scratch) / "mono.wav", sample_rate=8000,
                                    cancel=self.isInterruptionRequested)
                peaks, duration = waveform_peaks(wav)
                check_cancel(self.isInterruptionRequested)
                payload = {"peaks": peaks, "duration_ms": duration}
                partial = Path(scratch) / "peaks.json"
                partial.write_text(json.dumps(payload), encoding="utf-8")
                partial.replace(cache)  # atomic: ไม่โหลด cache ครึ่งไฟล์หลังยกเลิก
            self.ready.emit(self.media_id, payload)
        except AnalysisCancelled:
            pass
        except Exception as error:
            self.failed.emit(self.media_id, str(error))
