"""Mask cleanup, hole preservation and geometry in image coordinates."""

import cv2
import numpy as np


def clean_mask(mask, valid, uncertain, config):
    binary = mask.astype(np.uint8)
    if config.closing_radius:
        radius = config.closing_radius
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * radius + 1, 2 * radius + 1))
        binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)
    binary[~valid | uncertain] = 0
    count, labels, stats, _ = cv2.connectedComponentsWithStats(binary, 8)
    keep = stats[:, cv2.CC_STAT_AREA] >= max(4, round(binary.size * config.min_area_fraction))
    keep[0] = False
    binary = keep[labels].astype(np.uint8)
    # Fill only enclosed, small, observable holes. Border-connected background,
    # water-size holes and uncertain observations remain outside the detection.
    count, inverse, stats, _ = cv2.connectedComponentsWithStats(1 - binary, 8)
    border = np.unique(np.concatenate((inverse[0], inverse[-1], inverse[:, 0], inverse[:, -1])))
    protected = np.unique(inverse[~valid | uncertain])
    fill = stats[:, cv2.CC_STAT_AREA] <= round(binary.size * config.max_hole_fraction)
    fill[border] = False
    fill[protected] = False
    fill[0] = False
    binary[fill[inverse]] = 1
    return binary.astype(bool)


def extract_regions(mask, original_size, simplify_pixels=1.5):
    height, width = mask.shape
    original_width, original_height = original_size
    sx, sy = original_width / width, original_height / height
    count, labels, stats, centroids = cv2.connectedComponentsWithStats(mask.astype(np.uint8), 8)
    contours, hierarchy = cv2.findContours(mask.astype(np.uint8), cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
    if hierarchy is None:
        return [], 0.0
    hierarchy = hierarchy[0]
    regions = []
    perimeter_total = 0.0

    def ring(contour):
        points = cv2.approxPolyDP(contour, simplify_pixels, True).reshape(-1, 2).astype(float)
        # Centred pixel coordinates; clamp to the image extent.
        points[:, 0] = np.clip((points[:, 0] + 0.5) * sx - 0.5, 0, original_width - 1)
        points[:, 1] = np.clip((points[:, 1] + 0.5) * sy - 0.5, 0, original_height - 1)
        return np.round(points, 2).tolist()

    for i, contour in enumerate(contours):
        if hierarchy[i][3] != -1 or len(contour) < 3:
            continue
        point = contour[0, 0]
        label = labels[point[1], point[0]]
        scaled = contour.astype(np.float32).copy()
        scaled[:, :, 0] *= sx
        scaled[:, :, 1] *= sy
        perimeter = float(cv2.arcLength(scaled, True))
        holes, child = [], hierarchy[i][2]
        while child != -1:
            if len(contours[child]) >= 3:
                holes.append(ring(contours[child]))
            child = hierarchy[child][0]
        x, y, w, h, area = stats[label]
        regions.append({"id": len(regions) + 1, "outer": ring(contour), "holes": holes,
                        "area_working_pixels": int(area),
                        "area_original_pixels_estimated": round(float(area * sx * sy)),
                        "perimeter_original_pixels_estimated": round(perimeter, 2),
                        "centroid": [round(float((centroids[label, 0] + .5) * sx - .5), 2),
                                     round(float((centroids[label, 1] + .5) * sy - .5), 2)],
                        "bbox": [round(x * sx), round(y * sy), round(w * sx), round(h * sy)]})
        perimeter_total += perimeter
    regions.sort(key=lambda region: region["area_working_pixels"], reverse=True)
    for i, region in enumerate(regions):
        region["id"] = i + 1
    return regions, perimeter_total
