"""Network sources are mocked; tests never download images or enroll characters."""

import unittest
from unittest.mock import Mock, patch

from src.io.reference_images import download_reference_image, fetch_anilist_reference

import cv2
import numpy as np


class ReferenceSourceTests(unittest.TestCase):
    def test_url_decodes_pixels(self):
        expected = np.full((5, 5, 3), [30, 140, 220], dtype=np.uint8)
        success, encoded = cv2.imencode(".png", expected)
        self.assertTrue(success)
        response = Mock(content=encoded.tobytes())
        with patch("src.io.reference_images.requests.get", return_value=response):
            actual = download_reference_image("https://example.invalid/image.png")
        np.testing.assert_array_equal(actual, expected)
        response.raise_for_status.assert_called_once()

    def test_anilist_only_fetches_image(self):
        response = Mock()
        response.json.return_value = {"data": {"Character": {"image": {"large": "https://example.invalid/image.png"}}}}
        expected = np.zeros((5, 5, 3), dtype=np.uint8)
        with patch("src.io.reference_images.requests.post", return_value=response) as post:
            with patch("src.io.reference_images.download_reference_image", return_value=expected) as download:
                actual = fetch_anilist_reference("Aqua")
        self.assertIs(actual, expected)
        self.assertEqual(post.call_args.kwargs["json"]["variables"], {"search": "Aqua"})
        download.assert_called_once_with("https://example.invalid/image.png")

    def test_empty_api_result_is_reported(self):
        response = Mock()
        response.json.return_value = {"data": None, "errors": [{"message": "Not found"}]}
        with patch("src.io.reference_images.requests.post", return_value=response):
            with self.assertRaises(ValueError):
                fetch_anilist_reference("Missing")
