"""Select a hair ROI. This module crops pixels; it never computes features.

Without a box/mask the input must be a single-character portrait: the legacy
fallback keeps its top 45%. Never apply that fallback to a full video frame.
"""

import cv2
import numpy as np


def crop_hair_roi(image, bbox=None, hair_mask=None):
    """Return a BGR ROI from a portrait, face box (x, y, w, h), or binary mask.

    A supplied mask excludes non-hair pixels, even inside its bounding rectangle.
    Blacked-out pixels are ignored by hair_features' existing colour filter.
    Raise ValueError for an empty image or a region outside the image.
    """
    if image is None or image.size == 0:
        raise ValueError("Image is empty.")
    img_height, img_width = image.shape[:2]

    if hair_mask is not None:
        if hair_mask.ndim != 2 or hair_mask.shape != image.shape[:2]:
            raise ValueError("Hair mask must be 2D and match the image dimensions.")
        binary_mask = (hair_mask > 0).astype(np.uint8)
        x, y, w, h = cv2.boundingRect(binary_mask)
        if w == 0 or h == 0:
            raise ValueError("Hair mask does not contain any hair region.")
        roi = image[y:y + h, x:x + w].copy()
        roi[binary_mask[y:y + h, x:x + w] == 0] = 0
        return roi

    if bbox is not None:
        x, y, w, h = bbox
        if w <= 0 or h <= 0:
            raise ValueError("Bounding box width and height must be positive.")
        # Same face-box heuristic as the old extractor, with clamped coordinates.
        y_start = min(img_height, max(0, int(y - int(0.4 * h))))
        y_end = min(img_height, max(0, int(y + 0.2 * h)))
        x_start = min(img_width, max(0, int(x - 0.1 * w)))
        x_end = min(img_width, max(0, int(x + 1.1 * w)))
        roi = image[y_start:y_end, x_start:x_end]
    else:
        roi = image[:int(img_height * 0.45), :]

    if roi.size == 0:
        raise ValueError("Selected region does not contain any pixels.")
    return roi
