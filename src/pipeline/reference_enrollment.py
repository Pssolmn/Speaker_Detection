"""Coordinate reference image -> hair ROI -> features -> stored database.

This enrollment workflow is independent of future speaker attribution.
CLI and a future import dialog can both call these functions.
"""

from pathlib import Path
from uuid import uuid4
import warnings

import cv2

from src.core.config import DATABASE_PATH, REFERENCES_DIR
from src.core.models import CharacterDatabase
from src.io.character_db import load_character_database, save_character_database
from src.io.reference_images import iter_reference_images, read_reference_image
from src.vision.hair_features import extract_hair_features
from src.vision.hair_roi import crop_hair_roi


def build_character_database(
    reference_dir: Path = REFERENCES_DIR, output_db_path: Path = DATABASE_PATH,
) -> CharacterDatabase:
    """Batch rebuild from single-character portraits; preserve old DB on failure."""
    reference_dir = Path(reference_dir)
    database: CharacterDatabase = {}
    for character_name, image_path in iter_reference_images(reference_dir):
        try:
            portrait = read_reference_image(image_path)
            features = extract_hair_features(crop_hair_roi(portrait))
        except (ValueError, OSError) as error:
            warnings.warn(f"Skipping {image_path}: {error}", stacklevel=2)
            continue
        if features is None:
            warnings.warn(f"Skipping {image_path}: no usable hair pixels.", stacklevel=2)
            continue
        database.setdefault(character_name, []).append({
            "filename": str(image_path.relative_to(reference_dir)),
            "features": features,
        })
    if not database:
        raise ValueError("No usable reference images; the existing database was not replaced.")
    save_character_database(database, output_db_path)
    return database


def add_character_reference(
    character_name: str, portrait, reference_dir: Path = REFERENCES_DIR,
    output_db_path: Path = DATABASE_PATH,
) -> Path:
    """Enroll a head portrait, returning its saved path; raise on failure.

    Store the original portrait so batch rebuilds reproduce the same features.
    A corrupt existing database is never silently discarded.
    """
    character_name = character_name.strip()
    if (not character_name or character_name.startswith(".")
            or any(c in character_name for c in ("/", "\\", "\0"))):
        raise ValueError("Character name must be one non-hidden directory name.")
    reference_dir, output_db_path = Path(reference_dir), Path(output_db_path)
    features = extract_hair_features(crop_hair_roi(portrait))
    if features is None:
        raise ValueError("Reference portrait contains no usable hair pixels.")
    database = load_character_database(output_db_path) if output_db_path.exists() else {}
    character_dir = reference_dir / character_name
    character_dir.mkdir(parents=True, exist_ok=True)
    image_path = character_dir / f"capture_{uuid4().hex}.png"
    try:
        if not cv2.imwrite(str(image_path), portrait):
            raise OSError(f"Failed to write reference image: {image_path}")
        database.setdefault(character_name, []).append({
            "filename": str(image_path.relative_to(reference_dir)), "features": features,
        })
        save_character_database(database, output_db_path)
    except Exception:
        # Only remove the new, uniquely named image from this failed enrollment.
        image_path.unlink(missing_ok=True)
        raise
    return image_path
