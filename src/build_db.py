"""Build and update the visual-reference database (Data/Backend Layer)."""

from pathlib import Path
import pickle
import time
from typing import Generator, Tuple, Dict, Any, Optional
import cv2
import numpy as np

from src.core.config import (
    REFERENCES_DIR,
    DATABASE_PATH,
    IMAGE_EXTENSIONS,
)

try:
    from .extractor import extract_character_features
except ImportError:
    from extractor import extract_character_features


def iter_reference_images(
    reference_dir: Path = REFERENCES_DIR
) -> Generator[Tuple[str, Path], None, None]:
    """Yield a character name and every supported image below its directory."""
    if not reference_dir.is_dir():
        raise FileNotFoundError(f"Reference directory does not exist: {reference_dir}")

    for character_dir in sorted(reference_dir.iterdir()):
        if not character_dir.is_dir() or character_dir.name.startswith("."):
            continue
        for image_path in sorted(character_dir.iterdir()):
            if image_path.suffix.lower() in IMAGE_EXTENSIONS:
                yield character_dir.name, image_path


def build_character_database(
    reference_dir: Path = REFERENCES_DIR, 
    output_db_path: Path = DATABASE_PATH
) -> Dict[str, Any]:
    """สร้างฐานข้อมูลทั้งหมดจากโฟลเดอร์ data/references/ (Batch Mode)"""
    database: Dict[str, Any] = {}

    for character_name, image_path in iter_reference_images(reference_dir):
        image: Optional[np.ndarray] = cv2.imread(str(image_path))
        if image is None:
            continue

        features = extract_character_features(image)
        if features is None:
            continue

        database.setdefault(character_name, []).append({
            "filename": str(image_path.relative_to(reference_dir)),
            "features": features,
        })

    output_db_path.parent.mkdir(parents=True, exist_ok=True)
    with output_db_path.open("wb") as file_handle:
        pickle.dump(database, file_handle)

    return database


def add_character_reference(
    character_name: str, 
    cropped_image: np.ndarray, 
    reference_dir: Path = REFERENCES_DIR, 
    output_db_path: Path = DATABASE_PATH
) -> bool:
    """
    ฟังก์ชัน Backend สำหรับให้ UI (main.py) เรียกใช้:
    รับชื่อและภาพที่ครอปมาจากหน้าจอ UI -> สกัดฟีเจอร์ -> บันทึกลงฐานข้อมูลทันที
    """
    character_name = character_name.strip()
    if not character_name or cropped_image is None or cropped_image.size == 0:
        return False

    # 1. สกัดฟีเจอร์สีผม
    features = extract_character_features(cropped_image)
    if features is None:
        return False

    # 2. บันทึกรูปภาพลงโฟลเดอร์ references
    char_dir: Path = reference_dir / character_name
    char_dir.mkdir(parents=True, exist_ok=True)
    
    filename = f"capture_{int(time.time() * 1000)}.png"
    img_save_path = char_dir / filename
    cv2.imwrite(str(img_save_path), cropped_image)

    # 3. โหลดและอัปเดตไฟล์ .pkl
    database: Dict[str, Any] = {}
    if output_db_path.exists():
        with output_db_path.open("rb") as f:
            try:
                database = pickle.load(f)
            except Exception:
                database = {}

    rel_path = str(img_save_path.relative_to(reference_dir))
    database.setdefault(character_name, []).append({
        "filename": rel_path,
        "features": features,
    })

    output_db_path.parent.mkdir(parents=True, exist_ok=True)
    with output_db_path.open("wb") as file_handle:
        pickle.dump(database, file_handle)

    return True


if __name__ == "__main__":
    # เมื่อรันตรงๆ จาก Terminal ให้ทำหน้าที่สร้างฐานข้อมูลแบบสแกนโฟลเดอร์ปกติ
    build_character_database()