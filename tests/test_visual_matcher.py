"""Unit tests for baseline visual candidate ranking."""

import unittest

import numpy as np

from src.vision.visual_matcher import rank_visual_candidates


def make_features(hue: int) -> dict:
    """Create a small, valid feature record without reading project images."""
    histogram = np.zeros((2, 2), dtype=np.float32)
    histogram[hue % 2, (hue // 2) % 2] = 1.0
    return {"dominant_hsv": [hue, 255, 255], "histogram": histogram}


class VisualMatcherTests(unittest.TestCase):
    def setUp(self):
        self.database = {
            "Aqua": [{"features": make_features(100)}],
            "Ruby": [{"features": make_features(0)}],
        }

    def test_exact_reference_ranks_first(self):
        candidates = rank_visual_candidates(make_features(100), self.database)

        self.assertEqual(candidates[0].character_name, "Aqua")
        self.assertEqual(candidates[0].visual_score, 1.0)
        self.assertGreater(candidates[0].visual_score, candidates[1].visual_score)

    def test_missing_query_features_returns_no_candidates(self):
        self.assertEqual(rank_visual_candidates(None, self.database), [])

    def test_top_k_must_be_positive(self):
        with self.assertRaises(ValueError):
            rank_visual_candidates(make_features(100), self.database, top_k=0)

    def test_top_k_selects_references_not_characters(self):
        # Aqua has one exact and one different reference; both characters return.
        self.database["Aqua"].append({"features": make_features(0)})
        best_one = rank_visual_candidates(make_features(100), self.database, top_k=1)
        best_two = rank_visual_candidates(make_features(100), self.database, top_k=2)
        self.assertEqual(len(best_one), 2)
        self.assertEqual(best_one[0].visual_score, 1.0)
        self.assertLess(best_two[0].visual_score, 1.0)

    def test_unevaluated_evidence_remains_none(self):
        candidate = rank_visual_candidates(make_features(100), self.database)[0]
        self.assertIsNone(candidate.final_score)
        self.assertIsNone(candidate.script_score)
