"""CCIP สำหรับลักษณะตัวละครอนิเมะ ไม่ใช้สีผมอย่างเดียวและไม่ต้องมีชื่อก่อน.

ใช้ preprocessing และ metric ตาม deepghs/imgutils (MIT), CCIP โดย 7eu7d7.
https://github.com/deepghs/imgutils/blob/main/imgutils/metrics/ccip.py
ค่าระยะของ CCIP ไม่ใช่ cosine distance ทั่วไป จึงโหลด metric model คู่กัน.
"""

import json
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from src.core.config import DATA_DIR
from src.core.runtime import onnx_session
from src.workspace.store import fingerprint

DEFAULT_CCIP_DIR = DATA_DIR / "models" / "ccip"


class CharacterEncoder:
    def __init__(self, directory=DEFAULT_CCIP_DIR):
        directory = Path(directory)
        paths = [directory / name for name in ("model_feat.onnx", "model_metrics.onnx", "metrics.json")]
        for path in paths:
            if not path.is_file():
                raise FileNotFoundError(f"Missing {path.name}; run scripts/setup_workspace_models.py first")
        self.model_key = "ccip:" + fingerprint(paths[0]) + ":" + fingerprint(paths[1])
        self.threshold = float(json.loads(paths[2].read_text())["threshold"])
        self.encoder = onnx_session(paths[0])
        self.metric = onnx_session(paths[1])

    def encode(self, bgr_images):
        if not bgr_images:
            return np.empty((0, 0), np.float32)
        mean = np.array([.48145466, .4578275, .40821073], np.float32)[:, None, None]
        std = np.array([.26862954, .26130258, .27577711], np.float32)[:, None, None]
        tensors = []
        for frame in bgr_images:
            rgb = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            rgb = rgb.resize((384, 384), Image.Resampling.BILINEAR)
            tensor = np.asarray(rgb, dtype=np.float32).transpose(2, 0, 1) / 255
            tensors.append((tensor - mean) / std)
        result = self.encoder.run(None, {self.encoder.get_inputs()[0].name: np.stack(tensors)})[0]
        if not np.isfinite(result).all():
            raise ValueError("CCIP returned nonfinite features")
        return result

    def distances(self, query, references):
        if not len(references):
            return np.empty(0, np.float32)
        # จำกัดครั้งละ 32 reference ไม่สร้างเมทริกซ์ N×N ของทั้งเรื่อง
        distances = []
        for start in range(0, len(references), 32):
            values = np.vstack([query, *references[start:start + 32]]).astype(np.float32)
            matrix = self.metric.run(None, {self.metric.get_inputs()[0].name: values})[0]
            distances.extend(np.maximum(matrix[0, 1:], 0))
        return np.asarray(distances, np.float32)


def character_crop(frame, box):
    """เพิ่มบริเวณผมรอบหน้า แต่ไม่ใช้ทั้งเฟรมซึ่งอาจมีตัวละครหลายคน."""
    x, y, width, height = box
    left, right = max(0, int(x - width * .45)), min(frame.shape[1], int(x + width * 1.45))
    top, bottom = max(0, int(y - height * .65)), min(frame.shape[0], int(y + height * 1.5))
    return frame[top:bottom, left:right].copy()
