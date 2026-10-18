"""Read/write the reference PKL schema; no image processing or API calls here."""

import pickle
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import cast

import numpy as np

from src.core.config import DATABASE_PATH
from src.core.models import CharacterDatabase


def validate_character_database(database: object) -> CharacterDatabase:
    """Check the existing dictionary schema without converting or rebuilding it."""
    if not isinstance(database, dict) or not database:
        raise ValueError("Character database must be a nonempty dictionary.")
    for name, references in database.items():
        if not isinstance(name, str) or not name.strip():
            raise ValueError("Every character must have a nonempty string name.")
        if not isinstance(references, list) or not references:
            raise ValueError(f"Character '{name}' must have at least one reference.")
        for reference in references:
            if not isinstance(reference, dict) or not isinstance(reference.get("filename"), str):
                raise ValueError(f"Invalid reference record for '{name}'.")
            features = reference.get("features")
            if not isinstance(features, dict):
                raise ValueError(f"Missing features for '{name}'.")
            try:
                hsv = np.asarray(features["dominant_hsv"], dtype=np.float32)
                hist = np.asarray(features["histogram"], dtype=np.float32)
            except (KeyError, TypeError, ValueError) as error:
                raise ValueError(f"Invalid colour features for '{name}'.") from error
            if (hsv.shape != (3,) or not np.isfinite(hsv).all()
                    or np.any(hsv < 0) or hsv[0] >= 180 or np.any(hsv[1:] > 255)):
                raise ValueError(f"Invalid HSV centre for '{name}'.")
            if (hist.ndim != 2 or hist.size == 0 or not np.isfinite(hist).all()
                    or np.any(hist < 0) or hist.sum() <= 0):
                raise ValueError(f"Invalid histogram for '{name}'.")
    return cast(CharacterDatabase, database)


def load_character_database(db_path: Path = DATABASE_PATH) -> CharacterDatabase:
    """Load a trusted local PKL file. Existing reference files need no migration."""
    db_path = Path(db_path)
    if not db_path.exists():
        raise FileNotFoundError(
            f"Character database not found: {db_path}\nRun python -m src.build_db first."
        )
    try:
        with db_path.open("rb") as handle:
            database = pickle.load(handle)
    except Exception as error:
        raise ValueError(f"Failed to load character database: {db_path}: {error}") from error
    return validate_character_database(database)


def save_character_database(database: CharacterDatabase, db_path: Path = DATABASE_PATH) -> None:
    """Validate, then atomically replace the destination with the same PKL schema."""
    validate_character_database(database)
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = None
    try:
        with NamedTemporaryFile(mode="wb", dir=db_path.parent, prefix=f".{db_path.name}.", delete=False) as handle:
            temporary_path = Path(handle.name)
            pickle.dump(database, handle)
        temporary_path.replace(db_path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def has_character(character_name: str, db: CharacterDatabase | None = None) -> bool:
    if db is None:
        try:
            db = load_character_database()
        except FileNotFoundError:
            return False
    target_name = character_name.strip().lower()
    return any(name.lower() == target_name for name in db)
