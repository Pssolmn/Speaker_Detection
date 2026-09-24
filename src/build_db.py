"""Build and update the reusable visual-reference database from data/references/<character>/.

Supports:
1. Batch scanning from data/references/ (Original functionality)
2. Interactive frame enrollment from video via OpenCV ROI selector
"""

from pathlib import Path
import pickle
import sys
import time
import cv2

# เรียกใช้ค่าคงที่กลางจาก config.py จุดเดียวทั้งหมด
from src.core.config import (
    REFERENCES_DIR,
    DATABASE_PATH,
    IMAGE_EXTENSIONS,
)

try:
    from .extractor import extract_character_features
except ImportError:
    from extractor import extract_character_features

def iter_reference_images(reference_dir=REFERENCES_DIR):
    """Yield a character name and every supported image below its directory."""
    if not reference_dir.is_dir():
        raise FileNotFoundError(f"Reference directory does not exist: {reference_dir}")

    for character_dir in sorted(reference_dir.iterdir()):
        if not character_dir.is_dir() or character_dir.name.startswith("."):
            continue
        for image_path in sorted(character_dir.iterdir()):
            if image_path.suffix.lower() in IMAGE_EXTENSIONS:
                yield character_dir.name, image_path

                