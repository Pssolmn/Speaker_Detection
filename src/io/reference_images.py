"""Read reference pixels from folders, local files, URLs, or AniList.

Functions return paths/pixels only. Enrollment and PKL writes belong to
pipeline/reference_enrollment.py and io/character_db.py respectively.
"""

from pathlib import Path
from collections.abc import Iterator

import cv2
import numpy as np
import requests

from src.core.config import IMAGE_EXTENSIONS, REFERENCES_DIR


def iter_reference_images(reference_dir: Path = REFERENCES_DIR) -> Iterator[tuple[str, Path]]:
    reference_dir = Path(reference_dir)
    if not reference_dir.is_dir():
        raise FileNotFoundError(f"Reference directory not found: {reference_dir}")
    for character_dir in sorted(reference_dir.iterdir()):
        if not character_dir.is_dir() or character_dir.name.startswith("."):
            continue
        for image_path in sorted(character_dir.iterdir()):
            if image_path.is_file() and image_path.suffix.lower() in IMAGE_EXTENSIONS:
                yield character_dir.name, image_path


def read_reference_image(file_path: str | Path) -> np.ndarray:
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"Reference image not found: {path}")
    image = cv2.imread(str(path))
    if image is None:
        raise ValueError(f"Failed to decode reference image: {path}")
    return image


def download_reference_image(image_url: str) -> np.ndarray:
    response = requests.get(image_url, timeout=10)
    response.raise_for_status()
    image = cv2.imdecode(np.frombuffer(response.content, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("Downloaded reference could not be decoded as an image.")
    return image


def fetch_anilist_reference(character_name: str, series_name: str | None = None) -> np.ndarray:
    """Keep the existing Character search. series_name is extra search text only.

    This does NOT filter results by an exact media/series ID. A preview/selection
    UI and exact series filtering remain future work; this call does not enroll.
    """
    search_term = f"{character_name} {series_name}" if series_name else character_name
    query = """
    query ($search: String) {
      Character(search: $search) {
        name { full }
        image { large }
      }
    }
    """
    response = requests.post(
        "https://graphql.anilist.co",
        json={"query": query, "variables": {"search": search_term}},
        timeout=10,
    )
    response.raise_for_status()
    payload = response.json()
    character = (payload.get("data") or {}).get("Character")
    image_url = ((character or {}).get("image") or {}).get("large")
    if not image_url:
        raise ValueError(f"No character image found for '{search_term}'.")
    return download_reference_image(image_url)
