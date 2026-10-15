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


def grow_water_regions(seeds, candidates, valid):
    """Grow water candidates within components with substantial seed support."""
    seeds = np.asarray(seeds, dtype=bool) & valid
    candidates = np.asarray(candidates, dtype=bool) & valid
    if not seeds.any() or not candidates.any():
        return np.zeros_like(valid, dtype=bool)

    # Close narrow gaps at shorelines before keeping only seed-supported regions.
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    connected_candidates = cv2.morphologyEx(candidates.astype(np.uint8), cv2.MORPH_CLOSE, kernel).astype(bool)
    connected_candidates &= valid
    connected_candidates |= seeds
    count, labels = cv2.connectedComponents(connected_candidates.astype(np.uint8), connectivity=8)
    component_sizes = np.bincount(labels.ravel(), minlength=count)
    seed_counts = np.bincount(labels[seeds].ravel(), minlength=count)
    # Requiring a meaningful share of strong water pixels avoids growing a
    # handful of accidental matches across large dark areas such as burn scars.
    required_support = np.maximum(12, np.ceil(component_sizes * 0.15).astype(np.int64))
    supported = seed_counts >= required_support
    supported[0] = False
    return supported[labels]


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
        # Rendered water may be teal or nearly neutral in true color, so blue
        # channel dominance alone misses real reservoirs. Use strong darkness
        # in SWIR relative to the paired visible image as a second seed signal.
        visible_value = visible_hsv[:, :, 2]
        swir_value = hsv[:, :, 2]
        swir_visible_ratio = swir_value / np.maximum(visible_value, .03)
        blue_water_seeds = ((visible[:, :, 2] > 1.25 * visible[:, :, 0]) &
                            (visible_value < .55) & (swir_value < .25))
        spectral_water_seeds = ((swir_value < .32) & (visible_value < .75) &
                                (swir_visible_ratio < .55))
        water_seeds = (blue_water_seeds | spectral_water_seeds) & valid

        blue_water_candidates = ((visible[:, :, 2] > 1.08 * visible[:, :, 0]) &
                                 (visible[:, :, 2] > .90 * visible[:, :, 1]) &
                                 (visible_value < .70) & (swir_value < .40))
        spectral_water_candidates = ((swir_value < .48) & (visible_value < .85) &
                                     (swir_visible_ratio < .85))
        water_candidates = (blue_water_candidates | spectral_water_candidates) & valid
        water = grow_water_regions(water_seeds, water_candidates, valid)
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
