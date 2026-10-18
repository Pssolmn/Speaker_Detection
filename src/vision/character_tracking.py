"""ติดตามกล่องใบหน้าด้วย IoU แบบหนึ่งต่อหนึ่ง ภายใน subtitle segment.

เหมาะกับเฟรมที่อยู่ใกล้กัน; ปิด track เมื่อห่างเกินกำหนดหรือพบฉากตัด
ตัวนี้ยังไม่มี appearance embedding จึงอาจสลับ ID เมื่อคนเดินตัดกัน
"""

import cv2
import numpy as np

from src.core import config
from src.core.models import FaceDetection, FaceTrack, FrameSample, TrackObservation


def calculate_iou(box_a, box_b) -> float:
    """(x, y, width, height) สองกล่อง → พื้นที่ซ้อน / พื้นที่รวม ในช่วง 0–1"""
    ax, ay, aw, ah = box_a
    bx, by, bw, bh = box_b
    intersection = max(0, min(ax + aw, bx + bw) - max(ax, bx)) * max(
        0, min(ay + ah, by + bh) - max(ay, by)
    )
    union = aw * ah + bw * bh - intersection
    return float(intersection / union) if union > 0 else 0.0


def is_scene_cut(previous, current, threshold=config.SCENE_CUT_THRESHOLD) -> bool:
    """เปรียบเทียบภาพย่อเพื่อจับฉากเปลี่ยนมาก ๆ; เป็น heuristic ไม่ใช่ตัวตัดฉากสมบูรณ์"""
    if previous.shape != current.shape:
        return True
    a = cv2.resize(previous, (32, 18)).astype(np.float32) / 255.0
    b = cv2.resize(current, (32, 18)).astype(np.float32) / 255.0
    return bool(np.mean(np.abs(a - b)) >= threshold)


def track_faces(
    samples: list[FrameSample],
    detections_by_frame: list[list[FaceDetection]],
    iou_threshold: float = config.TRACK_IOU_THRESHOLD,
    max_gap_ms: int = config.TRACK_MAX_GAP_MS,
    scene_cut_threshold: float = config.SCENE_CUT_THRESHOLD,
) -> list[FaceTrack]:
    """samples[i] + detections_by_frame[i] → tracks ที่อ้าง index ของ samples เดิม.

    เรียงคู่ที่ IoU สูงสุดก่อน แล้วใช้แต่ละ detection/track ได้ครั้งเดียวต่อเฟรม
    ID เริ่มที่ 1 ทุกครั้งที่เรียก; ผู้คุม pipeline จะจัด ID ใหม่เมื่อต่อหลายหน้าต่าง
    """
    if len(samples) != len(detections_by_frame):
        raise ValueError("samples and detections_by_frame must have the same length")
    if not 0 < iou_threshold <= 1 or not 0 < scene_cut_threshold <= 1:
        raise ValueError("IoU and scene-cut thresholds must be in (0, 1]")
    if max_gap_ms <= 0:
        raise ValueError("max_gap_ms must be positive")
    if any(a.timestamp_ms >= b.timestamp_ms for a, b in zip(samples, samples[1:])):
        raise ValueError("samples must have strictly increasing timestamps")

    tracks: list[FaceTrack] = []
    active: list[FaceTrack] = []
    for index, (sample, detections) in enumerate(zip(samples, detections_by_frame)):
        if index and is_scene_cut(samples[index - 1].frame, sample.frame, scene_cut_threshold):
            active = []
        active = [track for track in active if sample.timestamp_ms -
                  samples[track.observations[-1].sample_index].timestamp_ms <= max_gap_ms]

        pairs = []
        for track in active:
            for detection_index, detection in enumerate(detections):
                overlap = calculate_iou(track.observations[-1].box, detection.box)
                if overlap >= iou_threshold:
                    pairs.append((overlap, track.track_id, detection_index, track))
        used_tracks, used_detections = set(), set()
        for _, track_id, detection_index, track in sorted(
            pairs, key=lambda pair: (-pair[0], pair[1], pair[2])
        ):
            if track_id in used_tracks or detection_index in used_detections:
                continue
            track.observations.append(TrackObservation(index, detections[detection_index].box))
            used_tracks.add(track_id)
            used_detections.add(detection_index)

        for detection_index, detection in enumerate(detections):
            if detection_index not in used_detections:
                track = FaceTrack(len(tracks) + 1, [TrackObservation(index, detection.box)])
                tracks.append(track)
                active.append(track)
    return tracks
