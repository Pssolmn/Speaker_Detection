"""วัดการเปลี่ยนภาพบริเวณปากของ track เดียวกัน ระหว่างช่วงเสียงมีพลังงาน.

ใช้กรอบหน้าประมาณตำแหน่งปาก จึงยังคลาดเคลื่อนได้เมื่อหน้าหันข้าง/ถูกบัง
คืนคะแนน absolute 0–1; ไม่บังคับให้คนหนึ่งชนะเมื่อทุกคนนิ่ง
"""

import cv2
import numpy as np

from src.audio.vad import speech_overlap_ratio
from src.core.models import FaceTrack, FrameSample, SubtitleSegment


def _face_gray(frame, box):
    """ตัดและปรับขนาดหน้าให้เท่ากัน ช่วยลด motion จากการย้ายตำแหน่งกรอบ"""
    x, y, width, height = box
    if width < 16 or height < 16 or x < 0 or y < 0:
        return None
    if x + width > frame.shape[1] or y + height > frame.shape[0]:
        return None
    crop = frame[y:y + height, x:x + width]
    return cv2.resize(cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY), (64, 64)).astype(np.float32) / 255


def mouth_motion_series(samples, track, *, localized=False):
    """คืน [start_ms, end_ms, motion] ต่อคู่เฟรม ไม่เหมารวมทั้ง track ว่าพูด.

    นี่ยังเป็น image-motion heuristic ไม่ใช่โมเดล lip-sync ที่ calibrate แล้ว.
    ผู้เรียกต้องนำเวลาไปเทียบ speech turn จริง และยอมไม่ตอบเมื่อหลักฐานไม่พอ.
    """
    pairs = []
    for previous, current in zip(track.observations, track.observations[1:]):
        a, b = samples[previous.sample_index], samples[current.sample_index]
        if not 0 < b.timestamp_ms - a.timestamp_ms <= 300:
            continue
        size_ratio = current.box[2] * current.box[3] / max(1, previous.box[2] * previous.box[3])
        if not 0.7 <= size_ratio <= 1.4:
            continue
        old, new = _face_gray(a.frame, previous.box), _face_gray(b.frame, current.box)
        if old is None or new is None:
            continue
        # ใช้หน้าส่วนบนชดเชยการขยับกล้อง/หัว ก่อนดูการเปลี่ยนแปลงเฉพาะปาก.
        shift, response = cv2.phaseCorrelate(old[:32], new[:32])
        if response > .2 and abs(shift[0]) <= 4 and abs(shift[1]) <= 4:
            new = cv2.warpAffine(new, np.float32([[1, 0, -shift[0]], [0, 1, -shift[1]]]),
                                 (64, 64), borderMode=cv2.BORDER_REPLICATE)
        delta = new - old
        delta -= np.median(delta)
        difference = np.abs(delta)
        mouth, control = difference[36:56, 16:48], difference[4:30, 8:56]
        if localized:
            # ปากอนิเมะเป็นเส้นเล็ก การเฉลี่ยทั้ง ROI จะเจือจางจนแทบเป็นศูนย์.
            # เทียบพิกเซลที่เปลี่ยนมากสุด 20% ทั้งปากและส่วนควบคุมเท่ากัน
            # จึงไม่เพียงลด threshold เพื่อให้ใบหน้าใดก็ได้ผ่าน.
            def local_change(region):
                values = region.ravel()
                count = max(1, values.size // 5)
                return float(np.partition(values, -count)[-count:].mean())
            mouth_change, control_change = local_change(mouth), local_change(control)
        else:
            mouth_change, control_change = float(mouth.mean()), float(control.mean())
        corrected = max(0., mouth_change - control_change - .01)
        pairs.append([a.timestamp_ms, b.timestamp_ms, min(1., corrected / .12)])
    return pairs


def score_active_speakers(
    samples: list[FrameSample],
    tracks: list[FaceTrack],
    speech_ranges,
) -> dict[int, float | None]:
    """samples/tracks ชุดเดียวกัน + ช่วงเสียง → track_id: คะแนน หรือ None.

    ต้องมีอย่างน้อยสองคู่เฟรมที่ใช้ได้; None คือประเมินไม่ได้ ส่วน 0 คือนิ่ง
    ไม่มีข้อมูลเสียงจะไม่ตีความ frame difference ว่าเป็นการพูด
    """
    scores = {}
    for track in tracks:
        changes = []
        if speech_ranges is not None:
            # localized=True: ปากอนิเมะเป็นเส้นเล็ก เฉลี่ยทั้ง ROI แล้วคะแนนจะเจือจางจนแทบเป็นศูนย์
            for start, end, motion in mouth_motion_series(samples, track, localized=True):
                interval = SubtitleSegment(0, start, end, "")
                if speech_overlap_ratio(interval, speech_ranges) < 0.5:
                    continue
                changes.append(motion)
        scores[track.track_id] = float(np.mean(changes)) if len(changes) >= 2 else None
    return scores
