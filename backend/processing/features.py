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


def extract_features(swir_rgb, true_rgb=None):
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
    swir_valid = np.any(swir_rgb > 3, axis=2)
    valid = swir_valid if true_rgb is None else swir_valid & np.any(true_rgb > 3, axis=2)
    compatible = valid & (hsv[:, :, 1] > 0.18) & (hsv[:, :, 2] > 0.12) & (red > blue * 1.03)
    score[~compatible] = 0
    if true_rgb is None:
        # Keep the same SWIR color evidence, without inventing visible-band
        # tests for water, vegetation, bright surfaces, smoke, or clouds.
        water = np.zeros_like(valid)
        vegetation = np.zeros_like(valid)
        seed_allowed = np.ones_like(valid)
        uncertain = np.zeros_like(valid)
    else:
        visible_hsv = cv2.cvtColor(true_rgb.astype(np.float32) / 255, cv2.COLOR_RGB2HSV)
        visible = true_rgb.astype(np.float32) / 255
        # Only exclude strong, cross-composite evidence of these backgrounds.
        water = (visible[:, :, 2] > 1.25 * visible[:, :, 0]) & (visible_hsv[:, :, 2] < .55) & (hsv[:, :, 2] < .25)
        vegetation = (visible[:, :, 1] > 1.15 * visible[:, :, 0]) & (green > 1.15 * red)
        score[water | vegetation] = 0
        visible_rg = (visible[:, :, 0] - visible[:, :, 1]) / (visible[:, :, 0] + visible[:, :, 1] + 1e-6)
        bright_surface = (visible_hsv[:, :, 2] > .78) | ((visible[:, :, 0] > .65) & (visible_rg > .07) & (visible_hsv[:, :, 1] > .20))
        # Bright soil and roofs cannot initiate a scar by themselves, but remain
        # candidates so bright parts inside a supported scar can be recovered.
        seed_allowed = ~bright_surface
        # A conservative visual heuristic: bright, weakly saturated visible pixels
        # together with a cyan SWIR response. It is not a validated cloud mask.
        uncertain = (visible_hsv[:, :, 1] < 0.22) & (visible_hsv[:, :, 2] > 0.50)
        uncertain &= (blue > red * 0.92) & (green > red * 1.05) & valid
        uncertain |= (visible_hsv[:, :, 1] < .18) & (visible_hsv[:, :, 2] > .80) & (hsv[:, :, 1] < .20) & (hsv[:, :, 2] > .75) & valid
    return {"rg": rg, "lab_a": lab[:, :, 1], "saturation": hsv[:, :, 1],
            "score": score, "valid": valid, "uncertain": uncertain,
            "water": water & valid, "vegetation": vegetation & valid,
            "seed_allowed": seed_allowed}
