"""Integration/regression tests using tiny generated images, never user data."""

from pathlib import Path
import pickle
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from src.core import config
from src.io.character_db import load_character_database, save_character_database
from src.pipeline.reference_enrollment import build_character_database, add_character_reference
from src.pipeline.visual_identification import VisualIdentifier
from src.vision.hair_roi import crop_hair_roi
from src.vision.hair_features import extract_hair_features
from src.vision.color_similarity import compare_color_features

import cv2
import numpy as np


class ReferenceWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.refs = self.root / "references"
        self.db_path = self.root / "character_db.pkl"
        self.aqua = np.full((40, 30, 3), [30, 140, 220], dtype=np.uint8)
        self.ruby = np.full((40, 30, 3), [100, 30, 210], dtype=np.uint8)
        for name, image in (("Aqua", self.aqua), ("Ruby", self.ruby)):
            folder = self.refs / name
            folder.mkdir(parents=True)
            self.assertTrue(cv2.imwrite(str(folder / "portrait.png"), image))

    def test_build_load_and_identify_share_the_same_features(self):
        built = build_character_database(self.refs, self.db_path)
        loaded = load_character_database(self.db_path)
        self.assertEqual(set(loaded), {"Aqua", "Ruby"})
        self.assertEqual(loaded["Aqua"][0]["filename"], "Aqua/portrait.png")
        np.testing.assert_array_equal(
            built["Aqua"][0]["features"]["histogram"], loaded["Aqua"][0]["features"]["histogram"],
        )
        identifier = VisualIdentifier.from_database(self.db_path)
        # The database should never be reloaded while processing images.
        with patch("src.pipeline.visual_identification.load_character_database", side_effect=AssertionError("reload")):
            for name, image in (("Aqua", self.aqua), ("Ruby", self.ruby)):
                result = identifier.identify_portrait(image)
                self.assertEqual(result[0].character_name, name)
                self.assertEqual(result[0].visual_score, 1.0)
                self.assertIsNone(result[0].final_score)
                self.assertIsNone(result[0].active_speaker_score)

    def test_legacy_dictionary_pickle_loads_without_migration(self):
        # Construct the old on-disk schema directly, without the new writer.
        features = extract_hair_features(crop_hair_roi(self.aqua))
        old_database = {"Aqua": [{"filename": "Aqua/001.jpg", "features": features}]}
        self.db_path.write_bytes(pickle.dumps(old_database))
        before = self.db_path.read_bytes()
        result = VisualIdentifier.from_database(self.db_path).identify_portrait(self.aqua)
        self.assertEqual(result[0].visual_score, 1.0)
        self.assertEqual(self.db_path.read_bytes(), before)

    def test_already_cropped_hair_is_not_cropped_again(self):
        hair = self.aqua.copy()
        hair[18:] = self.ruby[18:]
        full_features = extract_hair_features(hair)
        db = {"Mixed hair": [{"filename": "mixed.png", "features": full_features}]}
        identifier = VisualIdentifier(db)
        self.assertEqual(identifier.identify_hair_roi(hair)[0].visual_score, 1.0)
        self.assertLess(identifier.identify_portrait(hair)[0].visual_score, 1.0)

    def test_baseline_feature_values_survive_reorganisation(self):
        features = extract_hair_features(crop_hair_roi(self.aqua))
        np.testing.assert_allclose(features["dominant_hsv"], [17.0, 220.0, 220.0])
        self.assertEqual(features["histogram"].shape, (30, 32))
        self.assertAlmostEqual(float(features["histogram"].sum()), 1.0)
        self.assertIsNone(extract_hair_features(None))

    def test_hair_mask_excludes_pixels_inside_its_bounding_rectangle(self):
        image = self.ruby.copy()
        mask = np.zeros(image.shape[:2], dtype=np.uint8)
        mask[0, 0] = mask[-1, -1] = 1
        image[mask > 0] = self.aqua[0, 0]
        features = extract_hair_features(crop_hair_roi(image, hair_mask=mask))
        expected = extract_hair_features(self.aqua)
        self.assertEqual(compare_color_features(features, expected)["score"], 1.0)

    def test_outside_or_empty_face_box_is_rejected(self):
        for box in ((-100, 10, 5, 5), (500, 500, 5, 5), (0, 0, 0, 3)):
            with self.subTest(box=box), self.assertRaises(ValueError):
                crop_hair_roi(self.aqua, bbox=box)

    def test_colour_weights_are_read_from_config(self):
        a = {"dominant_hsv": [17, 220, 220], "histogram": np.array([[1, 0]], dtype=np.float32)}
        b = {"dominant_hsv": [17, 220, 220], "histogram": np.array([[0, 1]], dtype=np.float32)}
        self.assertEqual(compare_color_features(a, b)["score"], 0.3)
        with patch.object(config, "WEIGHT_HISTOGRAM", 0.8), patch.object(config, "WEIGHT_DOMINANT_COLOR", 0.2):
            self.assertEqual(compare_color_features(a, b)["score"], 0.2)

    def test_incremental_enrollment_preserves_existing_characters(self):
        build_character_database(self.refs, self.db_path)
        saved = add_character_reference("Aqua", self.aqua, self.refs, self.db_path)
        self.assertTrue(saved.is_file())
        loaded = load_character_database(self.db_path)
        self.assertEqual(len(loaded["Aqua"]), 2)
        self.assertEqual(len(loaded["Ruby"]), 1)

    def test_corrupt_database_is_not_replaced_during_enrollment(self):
        self.db_path.write_bytes(b"not a pickle")
        before_images = set(self.refs.rglob("*.png"))
        with self.assertRaises(ValueError):
            add_character_reference("Aqua", self.aqua, self.refs, self.db_path)
        self.assertEqual(self.db_path.read_bytes(), b"not a pickle")
        self.assertEqual(set(self.refs.rglob("*.png")), before_images)

    def test_empty_rebuild_preserves_previous_database(self):
        build_character_database(self.refs, self.db_path)
        before = self.db_path.read_bytes()
        empty_folder = self.root / "empty"
        empty_folder.mkdir()
        with self.assertRaises(ValueError):
            build_character_database(empty_folder, self.db_path)
        self.assertEqual(self.db_path.read_bytes(), before)

    def test_failed_serialization_preserves_database_and_cleans_new_image(self):
        build_character_database(self.refs, self.db_path)
        before = self.db_path.read_bytes()
        before_images = set(self.refs.rglob("*.png"))
        with patch("src.io.character_db.pickle.dump", side_effect=OSError("disk error")):
            with self.assertRaises(OSError):
                add_character_reference("Aqua", self.aqua, self.refs, self.db_path)
        self.assertEqual(self.db_path.read_bytes(), before)
        self.assertEqual(set(self.refs.rglob("*.png")), before_images)
        self.assertEqual(list(self.root.glob(".character_db.pkl.*")), [])

    def test_missing_feature_keys_are_rejected_before_save(self):
        with self.assertRaises(ValueError):
            save_character_database({"Aqua": [{"filename": "test.png", "features": {}}]}, self.db_path)
        self.assertFalse(self.db_path.exists())

    def test_failed_image_write_does_not_update_database(self):
        build_character_database(self.refs, self.db_path)
        before = self.db_path.read_bytes()
        with patch("src.pipeline.reference_enrollment.cv2.imwrite", return_value=False):
            with self.assertRaises(OSError):
                add_character_reference("Aqua", self.aqua, self.refs, self.db_path)
        self.assertEqual(self.db_path.read_bytes(), before)
