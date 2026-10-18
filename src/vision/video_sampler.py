"""เลือกเฟรมจากวิดีโอในช่วงเวลาของ subtitle segment."""

from __future__ import annotations

from math import floor, isfinite
from numbers import Integral
from pathlib import Path
from typing import Union

import cv2

from src.core.config import MAX_FRAME_WIDTH, MAX_FRAMES_PER_SEGMENT
from src.core.models import FrameSample, SubtitleSegment
from src.core.control import CancelCheck, check_cancel


VideoPath = Union[str, Path]


def _positive_integer(name: str, value: object) -> int:
    """ตรวจค่าที่ต้องเป็นจำนวนเต็มบวก"""
    # bool เป็น subclass ของ int ใน Python จึงต้องกันแยกต่างหาก
    if isinstance(value, bool) or not isinstance(value, Integral) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return int(value)


def _validate_segment(segment: SubtitleSegment) -> tuple[int, int]:
    """ตรวจช่วงเวลาและคืนค่า start/end เป็น millisecond"""
    if not isinstance(segment, SubtitleSegment):
        raise TypeError("segment must be a SubtitleSegment")

    start_ms = segment.start_ms
    end_ms = segment.end_ms

    if isinstance(start_ms, bool) or not isinstance(start_ms, Integral) or start_ms < 0:
        raise ValueError("segment.start_ms must be a non-negative integer")

    if isinstance(end_ms, bool) or not isinstance(end_ms, Integral) or end_ms <= start_ms:
        raise ValueError("segment.end_ms must be an integer greater than start_ms")

    return int(start_ms), int(end_ms)


def _target_times(start_ms: int, end_ms: int, count: int) -> list[int]:
    """เลือกกึ่งกลางช่องเวลาที่แบ่งเท่า ๆ กัน ภายใน [start_ms, end_ms)."""
    duration_ms = end_ms - start_ms

    # เวลาใช้หน่วย integer millisecond จึงไม่สร้างเป้าหมายซ้ำ
    # เช่น ช่วงยาว 1 ms ไม่จำเป็นต้องขอ 5 เวลา
    count = min(count, duration_ms)

    return [
        start_ms + ((2 * index + 1) * duration_ms) // (2 * count)
        for index in range(count)
    ]


def _resize_if_needed(frame, max_width: int):
    """ย่อภาพเมื่อกว้างเกิน max_width โดยรักษาอัตราส่วนเดิม"""
    height, width = frame.shape[:2]
    if width <= max_width:
        return frame

    resized_height = max(1, round(height * max_width / width))
    return cv2.resize(
        frame,
        (max_width, resized_height),
        interpolation=cv2.INTER_AREA,
    )


def sample_segment_frames(
    video_path: VideoPath,
    segment: SubtitleSegment,
    max_frames: int = MAX_FRAMES_PER_SEGMENT,
    max_width: int = MAX_FRAME_WIDTH,
    cancel: CancelCheck = None,
) -> list[FrameSample]:
    """อ่านเฟรมจากวิดีโอภายในช่วงของ subtitle segment.

    ``timestamp_ms`` คือเวลาที่ขออ่านจากวิดีโอ ไม่ใช่การรับประกันว่า decoder
    จะคืนภาพตรง millisecond นั้นแบบพอดีทุกไฟล์
    การแปลงเวลาเป็น frame index สมมติวิดีโอ FPS คงที่ และเลือกเฟรมที่แสดง
    อยู่ ณ เวลาที่ขอ ซึ่งเวลาเริ่มของเฟรมอาจอยู่ก่อน segment.start_ms ได้
    """
    max_frames = _positive_integer("max_frames", max_frames)
    max_width = _positive_integer("max_width", max_width)
    start_ms, end_ms = _validate_segment(segment)
    check_cancel(cancel)

    capture = cv2.VideoCapture(str(video_path))
    try:
        if not capture.isOpened():
            raise OSError(f"Cannot open video: {video_path}")

        fps = float(capture.get(cv2.CAP_PROP_FPS))
        # ไม่ใช้ NaN หรือ infinity คำนวณ frame index
        has_valid_fps = isfinite(fps) and fps > 0

        requested_times = _target_times(start_ms, end_ms, max_frames)

        # หลายเวลาสามารถตกอยู่ใน frame เดียวกัน โดยเฉพาะ segment ที่สั้นมาก
        # จึงตัด frame index ที่ซ้ำก่อน seek เพื่อไม่อ่านภาพเดิมซ้ำ
        targets: list[tuple[int, int | None]] = []
        seen_frame_indices: set[int] = set()

        for timestamp_ms in requested_times:
            if has_valid_fps:
                # เลือกเฟรมที่แสดงอยู่ ณ เวลานี้ ไม่ปัดไปเฟรมอนาคต
                frame_index = floor(timestamp_ms * fps / 1000)
                if frame_index in seen_frame_indices:
                    continue
                seen_frame_indices.add(frame_index)
                targets.append((timestamp_ms, frame_index))
            else:
                # บาง backend รายงาน FPS ไม่ได้ จึง fallback เป็นการ seek ด้วยเวลา
                targets.append((timestamp_ms, None))

        samples: list[FrameSample] = []
        for timestamp_ms, frame_index in targets:
            check_cancel(cancel)
            if frame_index is not None:
                seek_ok = capture.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
            else:
                seek_ok = capture.set(cv2.CAP_PROP_POS_MSEC, timestamp_ms)

            # ห้ามอ่านจากตำแหน่งเดิมแล้วติดป้ายว่าเป็นเวลาที่ขอ
            if not seek_ok:
                raise OSError(
                    f"Cannot seek to requested time {timestamp_ms} ms: {video_path}"
                )

            success, frame = capture.read()
            if not success or frame is None or frame.size == 0:
                # วิดีโออาจสั้นกว่าช่วง subtitle; ข้ามเป้าหมายนี้แล้วไปต่อ
                continue

            samples.append(
                FrameSample(
                    timestamp_ms=timestamp_ms,
                    frame=_resize_if_needed(frame, max_width),
                )
            )

        return samples
    finally:
        capture.release()


def sample_mouth_frames(
    video_path: VideoPath,
    segment: SubtitleSegment,
    sample_fps: float = 8,
    max_seconds: float = 10,
    max_width: int = MAX_FRAME_WIDTH,
    cancel: CancelCheck = None,
) -> list[FrameSample]:
    """อ่านเฟรมถี่จากหน้าต่างแรก ไม่เกิน max_seconds เพื่อวัดการขยับปาก.

    pipeline จะแบ่ง segment ยาวเป็นหลายหน้าต่างเอง และบันทึกเวลาทุกหน้าต่าง
    timestamp ของผลลัพธ์ยังอิงต้นวิดีโอ ไม่เริ่มนับใหม่ที่ศูนย์
    """
    if not isfinite(sample_fps) or not 0 < sample_fps <= 60:
        raise ValueError("sample_fps must be in (0, 60]")
    if not isfinite(max_seconds) or max_seconds < 0.001:
        raise ValueError("max_seconds must be at least 0.001")
    start, end = _validate_segment(segment)
    end = min(end, start + int(max_seconds * 1000))
    window = SubtitleSegment(segment.id, start, end, segment.text, segment.script_character)
    # ceil แบบจำนวนเต็มเพื่อให้ช่วงสั้นยังมีโอกาสได้หนึ่งเฟรม
    from math import ceil
    count = max(1, ceil((end - start) * sample_fps / 1000))
    return sample_segment_frames(video_path, window, count, max_width, cancel)
