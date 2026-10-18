"""ตรวจใบหน้าอนิเมะใน BGR frame และคืนกรอบแบบเดียวกันทั้งโปรเจกต์."""

from __future__ import annotations

from functools import lru_cache
from math import ceil, floor
from numbers import Real
from pathlib import Path
import warnings

import numpy as np
from ultralytics import YOLO

from src.core.config import DATA_DIR
from src.core.models import FaceDetection
from src.core.runtime import torch_device


# weights นี้เป็น YOLO สำหรับ anime face โดยตรง ไม่ใช่ YOLO COCO ที่คืนกรอบทั้งตัว
DEFAULT_FACE_MODEL_PATH = (
    DATA_DIR / "models" / "face_detect_v1.4_n" / "model.pt"
)

# threshold ที่ model card แนะนำสำหรับ face_detect_v1.4_n
DEFAULT_FACE_CONFIDENCE = 0.278


def _validate_confidence(value: object) -> float:
    """ตรวจว่า confidence threshold เป็นตัวเลขระหว่าง 0 ถึง 1"""
    # bool เป็น subclass ของ int จึงต้องปฏิเสธแยกต่างหาก
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError("confidence_threshold must be a number between 0 and 1")

    confidence = float(value)
    if not 0.0 <= confidence <= 1.0:
        raise ValueError("confidence_threshold must be between 0 and 1")
    return confidence


def _validate_frame(frame) -> np.ndarray:
    """ยืนยันว่า input เป็นภาพ BGR แบบที่ video_sampler คืนมา"""
    if not isinstance(frame, np.ndarray):
        raise TypeError("frame must be a NumPy array")
    if frame.size == 0:
        raise ValueError("frame must not be empty")
    if frame.ndim != 3 or frame.shape[2] != 3:
        raise ValueError("frame must have shape (height, width, 3) in BGR order")
    if frame.dtype != np.uint8:
        raise ValueError("frame must contain uint8 BGR pixels")
    return frame


@lru_cache(maxsize=4)
def _load_model(model_path: Path) -> YOLO:
    """โหลดโมเดลหนึ่งครั้งต่อ path แล้วเก็บไว้ใช้ซ้ำหลายเฟรม"""
    resolved_path = model_path.expanduser().resolve()
    if not resolved_path.is_file():
        raise FileNotFoundError(f"Face detector weights not found: {resolved_path}")

    # YOLO จะอ่าน architecture และ weights จากไฟล์ .pt นี้
    model = YOLO(str(resolved_path))
    names = model.names.values() if isinstance(model.names, dict) else model.names
    if model.task != "detect" or not any(str(name).lower() == "face" for name in names):
        raise ValueError("Weights must be a detection model with a face class")
    return model


def _face_class_name(result, class_id: int) -> str | None:
    """อ่านชื่อ class จากผล YOLO โดยรองรับทั้ง dict และ list"""
    names = getattr(result, "names", None)
    if isinstance(names, dict):
        name = names.get(class_id)
        return str(name) if name is not None else None
    if isinstance(names, (list, tuple)) and 0 <= class_id < len(names):
        return str(names[class_id])
    return None


def detect_faces(
    frame,
    model_path: str | Path = DEFAULT_FACE_MODEL_PATH,
    confidence_threshold: float = DEFAULT_FACE_CONFIDENCE,
    *, device: str = "auto",
) -> list[FaceDetection]:
    """ตรวจใบหน้าในหนึ่ง BGR frame.

    Args:
        frame: ภาพ BGR ขนาด ``(height, width, 3)`` จาก OpenCV
        model_path: path ไปยัง anime-face YOLO weights
        confidence_threshold: รับเฉพาะ detection ที่มีคะแนนอย่างน้อยค่านี้

    Returns:
        รายการ ``FaceDetection`` ที่ box เป็น ``(x, y, width, height)``
        ในพิกัดของ frame ที่ส่งเข้ามา; ถ้าไม่พบใบหน้าจะคืน ``[]``
    """
    frame = _validate_frame(frame)
    confidence_threshold = _validate_confidence(confidence_threshold)

    # resolve ก่อนส่งเข้า cache เพื่อให้ path ที่เขียนต่างกันแต่ชี้ไฟล์เดียวกัน
    # ใช้ model object ตัวเดียว ไม่โหลด weights ใหม่ทุกเฟรม
    resolved_model_path = Path(model_path).expanduser().resolve()
    model = _load_model(resolved_model_path)

    # Ultralytics จัดการ resize/normalize/NMS ภายใน predict ให้แล้ว
    results = model.predict(
        source=frame,
        conf=confidence_threshold,
        device=torch_device(device),
        verbose=False,
    )
    if not results:
        return []

    result = results[0]
    boxes = getattr(result, "boxes", None)
    if boxes is None or len(boxes) == 0:
        return []

    # YOLO คืน Tensor จึงย้ายมาที่ CPU แล้วแปลงเป็น list ก่อนใช้งาน
    coordinates = boxes.xyxy.cpu().tolist()
    confidences = boxes.conf.cpu().tolist()
    class_ids = boxes.cls.cpu().tolist()

    frame_height, frame_width = frame.shape[:2]
    detections: list[FaceDetection] = []

    for xyxy, confidence, class_id_value in zip(
        coordinates,
        confidences,
        class_ids,
    ):
        class_id = int(class_id_value)
        class_name = _face_class_name(result, class_id)

        # weights ปัจจุบันมี class เดียวชื่อ face; ถ้าเปลี่ยนเป็น multi-class model
        # จะไม่ส่ง object ชนิดอื่น เช่น person ให้ hair ROI โดยไม่ตั้งใจ
        if class_name is None:
            # class_id ไม่ตรงกับ names ของโมเดลเอง (ผิดปกติ) — ข้ามเฟรมนี้ไป
            # ไม่ให้ detection เดียวที่เพี้ยนทำให้สแกนวิดีโอทั้งไฟล์ล้มกลางทาง
            warnings.warn(f"Skipping detection with unknown class ID {class_id}", stacklevel=2)
            continue
        if class_name.lower() != "face":
            continue

        x1, y1, x2, y2 = (float(value) for value in xyxy)

        # ใช้ floor ที่มุมซ้ายบนและ ceil ที่มุมขวาล่าง เพื่อไม่ตัดขอบหน้า
        # จากนั้น clamp ให้อยู่ภายในภาพที่ส่งเข้ามาเสมอ
        left = max(0, min(frame_width, floor(x1)))
        top = max(0, min(frame_height, floor(y1)))
        right = max(0, min(frame_width, ceil(x2)))
        bottom = max(0, min(frame_height, ceil(y2)))

        width = right - left
        height = bottom - top
        if width <= 0 or height <= 0:
            continue

        detections.append(
            FaceDetection(
                box=(left, top, width, height),
                confidence=float(confidence),
            )
        )

    return detections
