"""คุมงานหนึ่ง subtitle: เฟรม → หน้า → track → สี/ปาก → คำตอบพร้อมเหตุผล.

ใช้ dense samples ชุดเดียวกันทั้งตัวตนและ motion ป้องกันจับปากคนหนึ่งกับชื่ออีกคน
ช่วงยาวแบ่งเป็นหน้าต่างเพื่อคืนหน่วยความจำและตรวจ Cancel ได้สม่ำเสมอ
"""

from dataclasses import asdict
from statistics import median
import re
from pathlib import Path

import numpy as np

from src.audio.vad import speech_overlap_ratio
from src.core import config
from src.core.control import AnalysisCancelled, CancelCheck, check_cancel
from src.core.models import AttributionResult, Candidate, SubtitleSegment, TrackEvidence
from src.pipeline.confidence_scoring import decide_attribution
from src.vision.active_speaker import score_active_speakers
from src.vision.character_tracking import track_faces
from src.vision.face_detect import DEFAULT_FACE_MODEL_PATH, DEFAULT_FACE_CONFIDENCE, detect_faces
from src.vision.video_sampler import sample_mouth_frames


def is_non_dialogue(text: str) -> bool:
    """ข้ามซับเพลง/เอฟเฟกต์ที่ทำเครื่องหมายชัดเจน; ไม่เดาชนิดข้อความทั่วไป"""
    text = re.sub(r"<[^>]+>", "", text).strip()
    return bool(text) and (text.startswith(("♪", "♫")) or
                           all(re.fullmatch(r"\[[^\]]+\]|\([^\)]+\)", line.strip())
                               for line in text.splitlines() if line.strip()))


def collect_visual_candidates(samples, tracks, identifier, cancel: CancelCheck = None) -> list[TrackEvidence]:
    """รวม median ของคะแนนต่อชื่อภายใน track; เลือกไม่เกิน 5 ภาพต่อ track.

    เวลาใน sample_times_ms นับเฉพาะเฟรมที่สกัด feature ได้จริง
    ถ้าไม่มี feature ยังคง track และ notes ไว้ ไม่แปลงเป็นไม่พบหน้า
    """
    collected = []
    for track in tracks:
        values: dict[str, list[float]] = {}
        evidence = TrackEvidence(track.track_id)
        count = min(config.MAX_FRAMES_PER_SEGMENT, len(track.observations))
        indices = np.linspace(0, len(track.observations) - 1, count, dtype=int) if count else []
        for index in indices:
            check_cancel(cancel)
            observation = track.observations[index]
            sample = samples[observation.sample_index]
            candidates, reason = identifier.identify_portrait_with_reason(sample.frame, bbox=observation.box)
            if reason:
                evidence.notes.append(f"{sample.timestamp_ms}: {reason}")
            if candidates:
                evidence.sample_times_ms.append(sample.timestamp_ms)
            for candidate in candidates:
                values.setdefault(candidate.character_name, []).append(candidate.visual_score)
        evidence.candidates = sorted(
            [Candidate(name, float(median(scores)), track_id=track.track_id) for name, scores in values.items()],
            key=lambda candidate: candidate.visual_score, reverse=True,
        )
        collected.append(evidence)
    return collected


def attribute_segment(
    video_path, segment: SubtitleSegment, identifier, speech_ranges=None,
    *, model_path=DEFAULT_FACE_MODEL_PATH, cancel: CancelCheck = None,
    on_preview=None, on_progress=None,
) -> AttributionResult:
    """คืน AttributionResult ทุกกรณีรวม error; Cancel จะ raise เพื่อหยุด runner.

    on_preview รับ dict ที่มี frame ชั่วคราวสำหรับ GUI; JSON evidence ไม่เก็บภาพ
    speech_ranges=None คือเสียงไม่ทราบ, [] คือวิเคราะห์แล้วไม่มีช่วงพลังงาน
    """
    check_cancel(cancel)
    overlap = None if speech_ranges is None else speech_overlap_ratio(segment, speech_ranges)
    evidence = {
        "video_path": str(Path(video_path).resolve()),
        "detector": {"model_path": str(Path(model_path).resolve()), "confidence_threshold": DEFAULT_FACE_CONFIDENCE},
        "sampling": {"fps": config.MOUTH_SAMPLE_FPS, "max_window_seconds": config.MAX_SECONDS_PER_SEGMENT,
                     "max_width": config.MAX_FRAME_WIDTH, "identity_frames_per_track": config.MAX_FRAMES_PER_SEGMENT},
        "audio_method": "rms_energy" if speech_ranges is not None else "unavailable",
        "audio_overlap_ratio": overlap,
        "warnings": ["Energy VAD may include music/noise; motion and colour scores are uncalibrated."],
        "windows": [], "tracks": [], "frames": [],
    }
    if is_non_dialogue(segment.text) and not segment.script_character:
        evidence["reason"] = "explicit_music_or_sound_effect_caption"
        return AttributionResult(segment.id, config.UNKNOWN_SPEAKER, 0.0, "NON_DIALOGUE", evidence)
    if overlap == 0 and segment.text.strip():
        evidence["warnings"].append("dialogue_without_detected_audio_energy")
    if not segment.text.strip() and not segment.script_character and not overlap:
        # ยังไม่มี VAD จะติด NO_CUE แทนการกล่าวว่าเงียบแน่นอน
        status = "NO_CUE" if speech_ranges is None else "NO_SPEECH"
        evidence["reason"] = "no_dialogue_or_audio_cue"
        return AttributionResult(segment.id, config.UNKNOWN_SPEAKER, 0.0, status, evidence)

    all_tracks = []
    next_track_id = 1
    try:
        window_ms = int(config.MAX_SECONDS_PER_SEGMENT * 1000)
        for start in range(segment.start_ms, segment.end_ms, window_ms):
            check_cancel(cancel)
            end = min(start + window_ms, segment.end_ms)
            window = SubtitleSegment(segment.id, start, end, segment.text, segment.script_character)
            if on_progress:
                on_progress(f"Segment {segment.id}: {start / 1000:.1f}–{end / 1000:.1f}s")
            samples = sample_mouth_frames(video_path, window, config.MOUTH_SAMPLE_FPS,
                                          config.MAX_SECONDS_PER_SEGMENT, cancel=cancel)
            if not samples:
                raise OSError(f"No readable frames between {start} and {end} ms")
            detections_by_frame = []
            for sample in samples:
                check_cancel(cancel)
                detections_by_frame.append(detect_faces(sample.frame, model_path=model_path))
            tracks = track_faces(samples, detections_by_frame)
            # แต่ละหน้าต่างเริ่ม tracking ใหม่ จึงจัดหมายเลขไม่ให้ชนกับหน้าต่างก่อน
            for track in tracks:
                track.track_id = next_track_id
                next_track_id += 1
            collected = collect_visual_candidates(samples, tracks, identifier, cancel)
            motion = score_active_speakers(samples, tracks, speech_ranges)
            for item in collected:
                item.active_speaker_score = motion[item.track_id]
                if item.active_speaker_score is None:
                    item.notes.append("mouth_motion_unavailable_or_insufficient_pairs")
            all_tracks.extend(collected)
            evidence["windows"].append({"start_ms": start, "end_ms": end, "sample_count": len(samples)})
            by_id = {item.track_id: item for item in collected}
            frame_evidence = []
            for index, sample in enumerate(samples):
                boxes = []
                for track in tracks:
                    for observation in track.observations:
                        if observation.sample_index == index:
                            item = by_id[track.track_id]
                            top = item.candidates[0] if item.candidates else None
                            boxes.append({"track_id": track.track_id, "box": list(observation.box),
                                          "name": top.character_name if top else "UNKNOWN",
                                          "visual_score": top.visual_score if top else None,
                                          "active_speaker_score": item.active_speaker_score})
                frame_evidence.append({"timestamp_ms": sample.timestamp_ms, "boxes": boxes})
            evidence["frames"].extend(frame_evidence)
            if on_preview:
                preview_index = max(range(len(samples)), key=lambda i: len(frame_evidence[i]["boxes"]))
                on_preview({"segment_id": segment.id, "frame": samples[preview_index].frame,
                            **frame_evidence[preview_index]})
            # ปล่อยภาพก่อนเริ่มหน้าต่างใหม่; evidence เก็บเฉพาะตัวเลข/ข้อความ
            del samples
        check_cancel(cancel)
        evidence["tracks"] = [asdict(track) for track in all_tracks]
        return decide_attribution(segment, all_tracks, evidence)
    except AnalysisCancelled:
        raise
    except Exception as error:
        # มี error แม้แค่หน้าต่างเดียวก็ไม่อ้างว่าอ่าน/ตรวจครบแล้วไม่เจอคน
        evidence["reason"] = "analysis_error"
        evidence["error"] = f"{type(error).__name__}: {error}"
        evidence["tracks"] = [asdict(track) for track in all_tracks]
        return AttributionResult(segment.id, segment.script_character or config.UNKNOWN_SPEAKER,
                                 0.0, "ERROR", evidence)
