"""Two-threshold segmentation and connected reconstruction."""

from dataclasses import asdict, dataclass

import cv2
import numpy as np


@dataclass(frozen=True)
class SegmentationConfig:
    max_side: int = 2048
    sensitivity: float = 0.5
    min_area_fraction: float = 0.00012
    closing_radius: int = 2
    max_hole_fraction: float = 0.00015
    simplify_pixels: float = 1.5
    refine: bool = True

    def __post_init__(self):
        if not 256 <= self.max_side <= 3072:
            raise ValueError("La resolución de análisis debe estar entre 256 y 3072.")
        if not 0 <= self.sensitivity <= 1:
            raise ValueError("La sensibilidad debe estar entre 0 y 1.")
        if not 0 <= self.min_area_fraction <= 0.02:
            raise ValueError("La superficie mínima debe estar entre 0 y 0,02.")
        if not 0 <= self.closing_radius <= 8:
            raise ValueError("El radio de cierre debe estar entre 0 y 8.")
        if not 0 <= self.max_hole_fraction <= 0.01 or not 0 <= self.simplify_pixels <= 10:
            raise ValueError("Parámetros de geometría fuera de rango.")

    def to_dict(self):
        return asdict(self)


def thresholds(config):
    shift = (0.5 - config.sensitivity) * 0.24
    return 0.64 + shift, 0.36 + shift


def reconstruct(seeds, candidates, min_area=1):
    """Keep candidate components connected to seeds; connectivity is eight."""
    count, labels, stats, _ = cv2.connectedComponentsWithStats(candidates.astype(np.uint8), 8)
    seed_counts = np.bincount(labels[seeds].ravel(), minlength=count)
    keep = (seed_counts > 0) & (stats[:, cv2.CC_STAT_AREA] >= min_area)
    keep[0] = False
    return keep[labels]


def segment(features, config):
    high, low = thresholds(config)
    score = features["score"]
    seeds = (score >= high) & features["valid"]
    candidates = (score >= low) & features["valid"]
    grown = reconstruct(seeds, candidates)
    return {"seeds": seeds, "candidates": candidates, "grown": grown,
            "seed_threshold": high, "candidate_threshold": low}
