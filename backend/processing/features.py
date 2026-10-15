"""Colour features. Input and output imagery always uses RGB, never BGR.

These are features of rendered JPEGs, not calibrated spectral indices.
"""

import cv2
import numpy as np


def working_image(rgb, max_side):
    height, width = rgb.shape[:2]
    scale = min(1.0, max_side / max(height, width))
    size = (max(1, round(width * scale)), max(1, round(height * scale)))
    return cv2.resize(rgb, size, interpolation=cv2.INTER_AREA) if scale < 1 else rgb.copy()


def extract_features(swir_rgb, true_rgb):
    rgb = swir_rgb.astype(np.float32) / 255.0
    red, green, blue = cv2.split(rgb)
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB)
    rg = (red - green) / (red + green + 1e-6)
    # Fixed scaling preserves differences across scenes. No per-image equalization.
    red_evidence = np.clip((rg + 0.02) / 0.28, 0, 1)
    lab_evidence = np.clip((lab[:, :, 1] + 3) / 32, 0, 1)
    saturation_evidence = np.clip((hsv[:, :, 1] - 0.12) / 0.60, 0, 1)
    score = 0.65 * red_evidence + 0.25 * lab_evidence + 0.10 * saturation_evidence
    valid = np.any(swir_rgb > 3, axis=2)
    compatible = valid & (hsv[:, :, 1] > 0.18) & (hsv[:, :, 2] > 0.12) & (red > blue * 1.03)
    score[~compatible] = 0
    visible_hsv = cv2.cvtColor(true_rgb.astype(np.float32) / 255, cv2.COLOR_RGB2HSV)
    # A conservative visual heuristic: bright, weakly saturated visible pixels
    # together with a cyan SWIR response. It is not a validated cloud mask.
    uncertain = (visible_hsv[:, :, 1] < 0.22) & (visible_hsv[:, :, 2] > 0.50)
    uncertain &= (blue > red * 0.92) & (green > red * 1.05) & valid
    return {"rg": rg, "lab_a": lab[:, :, 1], "saturation": hsv[:, :, 1],
            "score": score, "valid": valid, "uncertain": uncertain}
