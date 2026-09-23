"""Build the reusable visual-reference database from data/references/<character>/.

This baseline database stores only hair-colour features. It is useful later as
one input to visual_matcher.py, not as proof that the character is speaking.
"""

from pathlib import Path
import pickle

import cv2

try:
    # Supports `python -m src.build_db` from the project root.
    from .extractor import extract_character_features
except ImportError:
    # Supports the existing direct command: `python src/build_db.py`.
    from extractor import extract_character_features


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REFERENCE_DIR = PROJECT_ROOT / "data" / "references"
OUTPUT_DB_PATH = PROJECT_ROOT / "data" / "character_db.pkl"
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}


def iter_reference_images(reference_dir=REFERENCE_DIR):
    """Yield a character name and every supported image below its directory."""
    if not reference_dir.is_dir():
        raise FileNotFoundError(f"Reference directory does not exist: {reference_dir}")

    for character_dir in sorted(reference_dir.iterdir()):
        if not character_dir.is_dir() or character_dir.name.startswith("."):
            continue
        for image_path in sorted(character_dir.iterdir()):
            if image_path.suffix.lower() in IMAGE_EXTENSIONS:
                yield character_dir.name, image_path


def build_character_database(reference_dir=REFERENCE_DIR, output_db_path=OUTPUT_DB_PATH):
    """Create and save a mapping of character name to all usable reference features."""
    database = {}

    # Legacy flat-folder naming was intentionally retired because it broke names containing underscores.
    # character_name = filename.split("_")[0]
    for character_name, image_path in iter_reference_images(reference_dir):
        image = cv2.imread(str(image_path))
        if image is None:
            print(f"ข้ามไฟล์ที่อ่านไม่ได้: {image_path}")
            continue

        features = extract_character_features(image)
        if features is None:
            print(f"ข้ามไฟล์ที่สกัดลักษณะผมไม่ได้: {image_path}")
            continue

        database.setdefault(character_name, []).append({
            "filename": str(image_path.relative_to(reference_dir)),
            "features": features,
        })
        print(f"บันทึกข้อมูลสำเร็จ: {character_name} จากไฟล์ {image_path.name}")

    output_db_path.parent.mkdir(parents=True, exist_ok=True)
    with output_db_path.open("wb") as file_handle:
        pickle.dump(database, file_handle)

    print(f"\nสร้างฐานข้อมูลตัวละครเสร็จสมบูรณ์ -> บันทึกที่ {output_db_path}")
    return database


if __name__ == "__main__":
    build_character_database()
