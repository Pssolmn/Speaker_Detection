"""Coordinate still-image identity matching, without claiming speaker identity.

VisualIdentifier owns one loaded database and composes the vision functions.
The future speaker pipeline can reuse it without loading PKL per frame.
"""

from pathlib import Path

from src.core.config import DATABASE_PATH
from src.core.models import Candidate, CharacterDatabase
from src.io.character_db import load_character_database, validate_character_database
from src.vision.hair_roi import crop_hair_roi
from src.vision.hair_features import extract_hair_features
from src.vision.visual_matcher import rank_visual_candidates


class VisualIdentifier:
    def __init__(self, database: CharacterDatabase, top_k: int = 3):
        if isinstance(top_k, bool) or not isinstance(top_k, int) or top_k < 1:
            raise ValueError("top_k must be a positive integer")
        self.database = validate_character_database(database)
        self.top_k = top_k

    @classmethod
    def from_database(cls, db_path: Path = DATABASE_PATH, top_k: int = 3):
        """Read PKL once; reuse the returned identifier for many images."""
        return cls(load_character_database(db_path), top_k=top_k)

    def identify_portrait(self, image, bbox=None, hair_mask=None) -> list[Candidate]:
        """Select hair once, then rank. Whole frames require a face box or mask."""
        candidates, _ = self.identify_portrait_with_reason(image, bbox, hair_mask)
        return candidates

    def identify_portrait_with_reason(self, image, bbox=None, hair_mask=None):
        """คืน (candidates, reason) สำหรับ pipeline ที่ต้องแยก ROI เสียกับไม่มี feature.

        API เดิมยังคืน list เหมือนเดิม; เพิ่มเมธอดนี้เพื่อเก็บหลักฐานโดยไม่ crop ซ้ำ
        """
        try:
            hair_roi = crop_hair_roi(image, bbox=bbox, hair_mask=hair_mask)
        except ValueError:
            return [], "invalid_hair_roi"
        candidates = self.identify_hair_roi(hair_roi)
        return candidates, None if candidates else "no_usable_colour_features"

    def identify_hair_roi(self, hair_roi) -> list[Candidate]:
        """An already cropped hair image: extract directly, with NO second crop."""
        features = extract_hair_features(hair_roi)
        return rank_visual_candidates(features, self.database, top_k=self.top_k)
