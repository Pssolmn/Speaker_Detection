"""Compare TWO precomputed colour-feature sets. Formerly src/matcher.py.

No image loading or feature extraction happens here. visual_matcher uses these
small comparisons to rank many characters and reference images.
"""

import cv2
import numpy as np

from src.core import config
from src.core.models import ColorSimilarity, VisualFeatures


def calculate_histogram_similarity(hist_a, hist_b):
    """Histogram intersection after L1 normalization, in [0, 1]."""
    if hist_a is None or hist_b is None:
        return 0.0
    hist_a = np.asarray(hist_a, dtype=np.float32)
    hist_b = np.asarray(hist_b, dtype=np.float32)
    if hist_a.shape != hist_b.shape:
        raise ValueError("Histograms must use the same shape and bin settings.")
    total_a = float(hist_a.sum())
    total_b = float(hist_b.sum())
    if total_a <= 0 or total_b <= 0:
        return 0.0
    similarity = cv2.compareHist(hist_a / total_a, hist_b / total_b, cv2.HISTCMP_INTERSECT)
    return float(np.clip(similarity, 0.0, 1.0))


def calculate_dominant_color_similarity(hsv_a, hsv_b):
    """Compare HSV centres using circular hue distance (OpenCV hue scale)."""
    if hsv_a is None or hsv_b is None:
        return 0.0
    hsv_a = np.asarray(hsv_a, dtype=np.float32)
    hsv_b = np.asarray(hsv_b, dtype=np.float32)
    h_dist = abs(hsv_a[0] - hsv_b[0])
    h_dist = min(h_dist, 180.0 - h_dist) / 90.0
    s_dist = abs(hsv_a[1] - hsv_b[1]) / 255.0
    v_dist = abs(hsv_a[2] - hsv_b[2]) / 255.0
    distance = 0.7 * h_dist + 0.2 * s_dist + 0.1 * v_dist
    return float(np.clip(1.0 - distance, 0.0, 1.0))


def compare_color_features(
    features_a: VisualFeatures | None, features_b: VisualFeatures | None,
) -> ColorSimilarity:
    """Return pairwise score/components, using the active weights in config."""
    if features_a is None or features_b is None:
        return {"score": 0.0, "hist_score": 0.0, "color_score": 0.0}
    histogram_weight = config.WEIGHT_HISTOGRAM
    color_weight = config.WEIGHT_DOMINANT_COLOR
    if min(histogram_weight, color_weight) < 0 or not np.isclose(histogram_weight + color_weight, 1.0):
        raise ValueError("Colour comparison weights must be nonnegative and sum to 1.")
    hist_score = calculate_histogram_similarity(features_a["histogram"], features_b["histogram"])
    color_score = calculate_dominant_color_similarity(features_a["dominant_hsv"], features_b["dominant_hsv"])
    return {
        "score": round(histogram_weight * hist_score + color_weight * color_score, 4),
        "hist_score": round(hist_score, 4),
        "color_score": round(color_score, 4),
    }
