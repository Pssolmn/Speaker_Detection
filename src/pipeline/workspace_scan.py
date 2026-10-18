"""สแกนภาพทั้งวิดีโอแบบอ่านตามเวลา ไม่พึ่งซับ/ภาพอ้างอิงภายนอก.

เก็บผลเป็นหน้าต่างสั้นและ checkpoint; resume จะอ่าน decoder ไล่ถึงตำแหน่งเดิม
เพื่อรักษา timestamp แต่ไม่รันโมเดลซ้ำส่วนที่เสร็จแล้ว.
"""

from dataclasses import dataclass
import json
import math
from numbers import Integral
from pathlib import Path
import time

import cv2
import numpy as np

from src.core.control import check_cancel, AnalysisCancelled
from src.core.models import FrameSample
from src.vision.active_speaker import score_active_speakers
from src.vision.character_embedding import CharacterEncoder, character_crop
from src.vision.character_tracking import track_faces
from src.vision.face_detect import detect_faces, DEFAULT_FACE_MODEL_PATH
from src.workspace.clustering import cluster_observations
from src.workspace.store import cache_key, fingerprint


@dataclass(frozen=True)
class ScanSettings:
    sample_fps: float = 4.0
    max_width: int = 640
    window_ms: int = 8000
    device: str = "auto"

    def __post_init__(self):
        if not math.isfinite(self.sample_fps) or not 0 < self.sample_fps <= 12:
            raise ValueError("Sampling FPS must be in (0,12]")
        if any(isinstance(value, bool) or not isinstance(value, Integral) for value in (self.max_width, self.window_ms)):
            raise ValueError("Width/window must be integers")
        if not 160 <= self.max_width <= 1920 or not 1000 <= self.window_ms <= 30000:
            raise ValueError("Invalid scan dimensions/window")
        if self.device not in {"auto", "cpu", "mps", "cuda"}:
            raise ValueError("Invalid device")


def iter_video_windows(path, settings, *, start_ms=0, cancel=None):
    """Yield (window_start, window_end, samples, estimated_duration).

ใช้ POS_MSEC จาก decoder ก่อน แล้วค่อย fallback เป็น FPS คงที่เมื่อไม่มี PTS.
grab ทุกเฟรม แต่ retrieve/resize เฉพาะที่เลือก; memory จำกัดหนึ่งหน้าต่าง.
"""
    capture = cv2.VideoCapture(str(path))
    try:
        if not capture.isOpened():
            raise OSError(f"Cannot open video: {path}")
        fps = float(capture.get(cv2.CAP_PROP_FPS))
        if not math.isfinite(fps) or fps <= 0:
            raise ValueError("Video decoder did not report a usable FPS")
        count = capture.get(cv2.CAP_PROP_FRAME_COUNT)
        duration = round(count / fps * 1000) if math.isfinite(count) and count > 0 else 0
        step = 1000 / settings.sample_fps
        frame_index, previous_ms = 0, -1.0
        next_sample = math.ceil(start_ms / step) * step
        samples, window_start = [], start_ms
        while capture.grab():
            check_cancel(cancel)
            pts = float(capture.get(cv2.CAP_PROP_POS_MSEC))
            timestamp = pts if math.isfinite(pts) and pts > previous_ms else frame_index / fps * 1000
            frame_index += 1
            previous_ms = max(timestamp, previous_ms)
            if timestamp < next_sample:
                continue
            if timestamp >= window_start + settings.window_ms and samples:
                end = window_start + settings.window_ms
                yield window_start, end, samples, duration
                samples = []
                window_start = end
                while timestamp >= window_start + settings.window_ms:
                    window_start += settings.window_ms
            ok, frame = capture.retrieve()
            if not ok or frame is None:
                raise OSError(f"Cannot decode video frame around {timestamp:.0f} ms")
            if frame.shape[1] > settings.max_width:
                scale = settings.max_width / frame.shape[1]
                frame = cv2.resize(frame, (settings.max_width, max(1, round(frame.shape[0] * scale))), interpolation=cv2.INTER_AREA)
            samples.append(FrameSample(round(timestamp), frame))
            # ยึด grid ของทั้งเรื่อง ไม่บวกจากเฟรมที่ decode ได้ (จะสะสม drift)
            # resume จึงเลือกเฟรมเดียวกับการสแกนรวดเดียว
            next_sample = (math.floor(timestamp / step) + 1) * step
        if samples:
            end = max(samples[-1].timestamp_ms + 1, round(frame_index / fps * 1000))
            yield window_start, end, samples, max(duration, end)
    finally:
        capture.release()


def scan_visual(store, media_id, *, settings=None, encoder=None, detector=None,
                model_path=DEFAULT_FACE_MODEL_PATH, cancel=None, progress=None):
    settings = settings or ScanSettings()
    encoder = encoder or CharacterEncoder()
    detector = detector or (lambda frame: detect_faces(frame, model_path=model_path, device=settings.device))
    run_settings = {"version": 2, "fps": settings.sample_fps, "width": settings.max_width,
                    "window_ms": settings.window_ms, "encoder": encoder.model_key,
                    "detector": fingerprint(model_path), "threshold": encoder.threshold}
    voice_run = store.db.execute("SELECT r.* FROM runs r JOIN meta m ON m.value=r.key "
                                "WHERE m.key=? AND r.state='complete'", (f"active:{media_id}:voice",)).fetchone()
    existing = store.db.execute("SELECT r.settings FROM runs r JOIN meta m ON m.value=r.key WHERE m.key=?",
                               (f"active:{media_id}:visual",)).fetchone()
    # รอบเก่าคง cache key/กลุ่มที่ตรวจแล้วไว้; รอบใหม่เมื่อมีเสียงให้ดูเฉพาะ speech windows.
    previous = json.loads(existing[0]) if existing else None
    focus = previous.get("speech_run") if previous else voice_run["key"] if voice_run else None
    speech_ranges = None
    if focus:
        run_settings["speech_run"] = focus
        speech_ranges = [(item["start_ms"], item["end_ms"]) for item in store.rows(
            "SELECT start_ms,end_ms FROM observations WHERE run_key=? AND kind='voice'", (focus,))]
    run = store.begin_run(media_id, "visual", run_settings, cancel)
    if run["state"] == "complete":
        if progress:
            progress(1, 1, "Visual scan already cached")
        return run["key"]
    started, cursor = time.monotonic(), run["cursor_ms"]
    try:
        for start, end, samples, duration in iter_video_windows(store.media_path(media_id), settings,
                                                               start_ms=cursor, cancel=cancel):
            if speech_ranges is not None:
                samples = [sample for sample in samples if any(a - 250 <= sample.timestamp_ms < b + 250
                                                              for a, b in speech_ranges)]
            detections = []
            for sample in samples:
                check_cancel(cancel)
                detections.append(detector(sample.frame))
            tracks = track_faces(samples, detections, max_gap_ms=max(750, round(2000 / settings.sample_fps)))
            # นี่เป็น mouth-motion evidence เท่านั้น ยังไม่ใช่ข้อยืนยันว่าใครพูด
            motion = score_active_speakers(samples, tracks, speech_ranges if speech_ranges is not None else [(start, end)])
            pending_previews = []
            for track in tracks:
                check_cancel(cancel)
                valid = [item for item in track.observations if min(item.box[2:]) >= 24]
                if not valid:
                    continue
                chosen = [valid[i] for i in np.unique(np.linspace(0, len(valid) - 1, min(3, len(valid)), dtype=int))]
                crops = [character_crop(samples[item.sample_index].frame, item.box) for item in chosen]
                vectors = encoder.encode(crops)
                # เฉลี่ยเวกเตอร์ที่ normalized แล้ว คืนสเกลเดิมตาม CCIP merge contract
                norms = np.linalg.norm(vectors, axis=1)
                if np.any(norms <= 0):
                    continue
                mean = np.mean(vectors / norms[:, None], axis=0)
                feature = mean / max(np.linalg.norm(mean), 1e-8) * norms.mean()
                first_ms = samples[track.observations[0].sample_index].timestamp_ms
                last_ms = min(end, samples[track.observations[-1].sample_index].timestamp_ms + round(1000 / settings.sample_fps))
                identifier = cache_key(run["key"], start, track.track_id)
                pending_previews.append((identifier, crops[len(crops) // 2]))
                evidence = {"observations": len(track.observations), "motion": motion.get(track.track_id),
                            "low_quality": len(valid) < 2, "window_start_ms": start,
                            "boxes": [{"time_ms": samples[item.sample_index].timestamp_ms, "box": item.box}
                                      for item in track.observations],
                            "speech_focused": speech_ranges is not None,
                            "preview_policy": "At most four thumbnails per visual profile; original video retains all evidence",
                            "note": "Appearance only; not proof of speaking. Sampled coverage, not every frame."}
                store.put_observation(identifier=identifier, media_id=media_id, run_key=run["key"], kind="visual",
                                      start_ms=first_ms, end_ms=max(first_ms + 1, last_ms), model_key=encoder.model_key,
                                      features=feature, evidence=evidence)
            # เก็บกลุ่มและ cursor ก่อนเริ่มหน้าต่างถัดไป; ไม่ต้องรอทั้งเรื่องเสร็จ
            cluster_observations(store, "visual", encoder.distances, encoder.threshold, cancel=cancel)
            for identifier, crop in pending_previews:
                check_cancel(cancel)
                row = store.db.execute("SELECT o.preview,m.profile_id FROM observations o JOIN memberships m ON m.observation_id=o.id WHERE o.id=?", (identifier,)).fetchone()
                if row["preview"]:
                    continue
                count = store.db.execute("SELECT COUNT(*) FROM observations o JOIN memberships m ON m.observation_id=o.id "
                    "WHERE o.kind='visual' AND o.preview IS NOT NULL AND m.profile_id IS ?", (row["profile_id"],)).fetchone()[0]
                if count >= (4 if row["profile_id"] else 32):
                    continue
                # เก็บภาพเล็กเฉพาะตัวแทน ไม่แคปซ้ำทุก track ลงดิสก์; ดูเต็มจากวิดีโอได้เสมอ.
                if max(crop.shape[:2]) > 256:
                    scale = 256 / max(crop.shape[:2])
                    crop = cv2.resize(crop, (max(1, round(crop.shape[1] * scale)), max(1, round(crop.shape[0] * scale))))
                preview = f"evidence/{identifier}.jpg"
                if not cv2.imwrite(str(store.root / preview), crop, [cv2.IMWRITE_JPEG_QUALITY, 80]):
                    raise OSError("Could not save character preview")
                with store.db:
                    store.db.execute("UPDATE observations SET preview=? WHERE id=?", (preview, identifier))
            cursor = end
            store.checkpoint(run["key"], cursor)
            if progress:
                progress(cursor, max(duration, cursor), f"Visual {cursor/1000:.1f}s · elapsed {time.monotonic()-started:.1f}s")
        store.checkpoint(run["key"], cursor, "complete")
    except AnalysisCancelled:
        store.checkpoint(run["key"], cursor, "cancelled")
        raise
    except Exception:
        store.checkpoint(run["key"], cursor, "error")
        raise
    return run["key"]
