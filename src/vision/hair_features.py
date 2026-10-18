"""Extract colour features from an ALREADY selected BGR hair ROI.

Migrated from extractor.py. This module never crops the input again and does not
load images, read databases, or decide a character. Hair shape is future work.
"""

import cv2
import numpy as np
from sklearn.cluster import KMeans

from src.core.models import VisualFeatures


def filter_lineart_and_background(hsv_roi):
    """Keep the original baseline's dark/near-white pixel filtering."""
    v_channel = hsv_roi[:, :, 2]
    s_channel = hsv_roi[:, :, 1]
    return (v_channel >= 40) & ~((s_channel < 25) & (v_channel > 230))


def extract_dominant_hair_color(hsv_roi, mask, k=3):
    """Return the largest KMeans cluster's HSV centre, or None for no pixels."""
    valid_pixels = hsv_roi[mask]
    if len(valid_pixels) == 0:
        return None
    distinct_colours = len(np.unique(valid_pixels, axis=0))
    kmeans = KMeans(
        n_clusters=min(k, len(valid_pixels), distinct_colours),
        random_state=42,
        n_init=5,
    )
    kmeans.fit(valid_pixels)
    count = np.bincount(kmeans.labels_)
    return kmeans.cluster_centers_[np.argmax(count)]


def extract_color_histogram(hsv_roi, mask, h_bins=30, s_bins=32):
    """Return an L1-normalized H/S histogram (same bins as existing PKL files)."""
    if not np.any(mask):
        return None
    histogram = cv2.calcHist(
        [hsv_roi], [0, 1], mask.astype(np.uint8) * 255,
        [h_bins, s_bins], [0, 180, 0, 256],
    )
    return cv2.normalize(histogram, None, alpha=1.0, beta=0.0, norm_type=cv2.NORM_L1)


def extract_hair_features(hair_roi) -> VisualFeatures | None:
    """BGR hair ROI -> {dominant_hsv, histogram}; empty/unusable ROI -> None.

    Call hair_roi.crop_hair_roi first if the input is a portrait or a full frame
    with a known face box. A ready-made hair crop comes directly to this function.
    """
    if hair_roi is None or hair_roi.size == 0:
        return None
    if hair_roi.ndim != 3 or hair_roi.shape[2] != 3 or hair_roi.dtype != np.uint8:
        raise ValueError("Hair ROI must be a uint8 BGR image with three channels.")

    hsv_roi = cv2.cvtColor(hair_roi, cv2.COLOR_BGR2HSV)
    mask = filter_lineart_and_background(hsv_roi)
    dominant_color = extract_dominant_hair_color(hsv_roi, mask)
    color_hist = extract_color_histogram(hsv_roi, mask)
    if dominant_color is None or color_hist is None:
        return None
    return {"dominant_hsv": dominant_color.tolist(), "histogram": color_hist}
