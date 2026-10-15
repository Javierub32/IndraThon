"""Sparse active-fire candidates from a fixed-rendering Sentinel-2 SWIR JPEG.

Rule adapted from Mitra et al. (arXiv:2609.16199v1, Eqs. 2-4). The paper
applies its thresholds to converted Level-2A reflectance before rendering;
here the inverse of its published fixed rendering is only an approximation
because the app receives quantized, lossy JPEG composites.
"""

from dataclasses import asdict, dataclass

import cv2
import numpy as np


@dataclass(frozen=True)
class ActiveFireConfig:
    b12_seed: float = 0.35
    ratio_seed: float = 4.0
    b12_candidate: float = 0.25
    ratio_candidate: float = 2.0
    b12_render_max: float = 0.60
    b8a_render_max: float = 0.45
    growth_steps: int = 2
    min_component_pixels: int = 2
    contextual_filter: bool = True
    context_radius_fraction: float = 0.015
    min_red_excess: float = 0.08
    min_context_z: float = 1.5

    def __post_init__(self):
        if not 0 < self.b12_candidate <= self.b12_seed <= self.b12_render_max:
            raise ValueError("Los umbrales de brillo activo deben ser positivos y ordenados.")
        if not 0 < self.ratio_candidate <= self.ratio_seed or self.b8a_render_max <= 0:
            raise ValueError("Los umbrales de contraste activo deben ser positivos y ordenados.")
        if not isinstance(self.growth_steps, int) or not 0 <= self.growth_steps <= 8 or not 1 <= self.min_component_pixels <= 100:
            raise ValueError("El crecimiento y el tamaño mínimo activos están fuera de rango.")
        if not .002 <= self.context_radius_fraction <= .10 or not 0 <= self.min_red_excess <= 1 or not 0 <= self.min_context_z <= 10:
            raise ValueError("Los parámetros de contexto activo están fuera de rango.")

    def to_dict(self):
        return asdict(self)


def detect_active_fire(swir_rgb, uncertain=None, original_size=None, config=None):
    """Return a sparse, uncertainty-filtered active-fire candidate mask.

    Expected SWIR order is R=B12, G=B11, B=B8A using the paper's fixed
    rendering limits. Two 4-neighbour growth steps and a two-pixel sieve
    retain small hot targets while avoiding unbounded expansion.
    """
    config = config or ActiveFireConfig()
    if swir_rgb.ndim != 3 or swir_rgb.shape[2] != 3 or swir_rgb.dtype != np.uint8:
        raise ValueError("La detección activa requiere una composición SWIR RGB de 8 bits.")
    height, width = swir_rgb.shape[:2]
    if min(height, width) < 1:
        raise ValueError("La composición SWIR está vacía.")
    if uncertain is None:
        uncertain = np.zeros((height, width), dtype=bool)
    else:
        uncertain = np.asarray(uncertain, dtype=bool)
        if uncertain.shape != (height, width):
            raise ValueError("La incertidumbre debe compartir la cuadrícula SWIR.")

    rgb = swir_rgb.astype(np.float32)
    rho12 = (rgb[:, :, 0] / 255.0) * config.b12_render_max
    rho8a = (rgb[:, :, 2] / 255.0) * config.b8a_render_max
    ratio = np.divide(rho12, rho8a, out=np.full_like(rho12, np.inf), where=rho8a > 1e-6)
    valid = np.all(swir_rgb > 3, axis=2) & ~uncertain

    raw_seeds = valid & (rho12 >= config.b12_seed) & (ratio >= config.ratio_seed)
    candidates = valid & (rho12 >= config.b12_candidate) & (ratio >= config.ratio_candidate)
    seeds = raw_seeds.copy()
    context_support = raw_seeds.copy()
    if config.contextual_filter:
        red = rgb[:, :, 0] / 255.0
        background = (valid & ~raw_seeds).astype(np.float32)
        radius = max(5, round(max(height, width) * config.context_radius_fraction))
        kernel_size = (2 * radius + 1,) * 2
        count = cv2.boxFilter(background, -1, kernel_size, normalize=False, borderType=cv2.BORDER_CONSTANT)
        mean = cv2.boxFilter(red * background, -1, kernel_size, normalize=False, borderType=cv2.BORDER_CONSTANT) / np.maximum(count, 1)
        variance = cv2.boxFilter(red * red * background, -1, kernel_size, normalize=False, borderType=cv2.BORDER_CONSTANT) / np.maximum(count, 1) - mean * mean
        excess = red - mean
        z = excess / np.sqrt(np.maximum(variance, 0) + .015 ** 2)
        context_support = raw_seeds & (excess >= config.min_red_excess) & (z >= config.min_context_z) & (count >= kernel_size[0] ** 2 * .25)
        # Keep an entire seed component if it has local anomalous support;
        # this preserves broad hot cores and tiny point targets alike.
        n, seed_labels = cv2.connectedComponents(raw_seeds.astype(np.uint8), connectivity=8)
        supported = np.bincount(seed_labels[context_support], minlength=n) > 0
        supported[0] = False
        seeds = supported[seed_labels]

    # Match the reference rule's bounded four-neighbour expansion.
    cross = cv2.getStructuringElement(cv2.MORPH_CROSS, (3, 3))
    grown = seeds.astype(np.uint8)
    for _ in range(config.growth_steps):
        grown |= cv2.dilate(grown, cross) & candidates.astype(np.uint8)

    # Discard isolated one-pixel speckles; keep small real hotspots.
    component_count, component_labels, stats, centroids = cv2.connectedComponentsWithStats(
        grown, connectivity=8
    )
    seed_counts = np.bincount(component_labels[seeds].ravel(), minlength=component_count)
    keep = (stats[:, cv2.CC_STAT_AREA] >= config.min_component_pixels) & (seed_counts > 0)
    keep[0] = False
    mask = keep[component_labels]

    # A display-only strength image: 1.0 marks both seed conditions. It is
    # not a calibrated probability and is not used in place of the rule.
    score = np.minimum(rho12 / config.b12_seed, ratio / config.ratio_seed)
    score = np.clip(score, 0, 1).astype(np.float32)
    score[~valid] = 0

    original_width, original_height = original_size or (width, height)
    sx, sy = original_width / width, original_height / height
    peak_b12 = np.zeros(component_count, dtype=np.float32)
    peak_ratio = np.zeros(component_count, dtype=np.float32)
    flat_labels = component_labels.ravel()
    np.maximum.at(peak_b12, flat_labels, rho12.ravel())
    np.maximum.at(peak_ratio, flat_labels, np.minimum(ratio, np.finfo(np.float32).max).ravel())
    hotspots = []
    for label in range(1, component_count):
        if not keep[label]:
            continue
        x, y, box_width, box_height, area = (int(v) for v in stats[label])
        cx, cy = centroids[label]
        hotspots.append({
            "id": 0,
            "centroid": [round(float((cx + 0.5) * sx - 0.5), 2),
                         round(float((cy + 0.5) * sy - 0.5), 2)],
            "bbox": [round(x * sx), round(y * sy),
                     round(box_width * sx), round(box_height * sy)],
            "area_analysis_pixels": area,
            "area_original_pixels_estimated": round(area * sx * sy),
            "seed_pixels": int(seed_counts[label]),
            "peak_b12_approx": round(float(peak_b12[label]), 4),
            "peak_b12_b8a_ratio_approx": round(float(peak_ratio[label]), 3),
            "peak_red": round(float(peak_b12[label]) / config.b12_render_max, 4),
            "peak_red_blue_ratio": round(float(peak_ratio[label]) * config.b8a_render_max / config.b12_render_max, 3),
        })
    hotspots.sort(key=lambda item: (item["seed_pixels"], item["area_analysis_pixels"]), reverse=True)
    for index, hotspot in enumerate(hotspots, 1):
        hotspot["id"] = index

    candidate_pixels = int(candidates.sum())
    seed_pixels = int(seeds.sum())
    active_pixels = int(mask.sum())
    return {
        "mask": mask,
        "seeds": seeds,
        "raw_seeds": raw_seeds,
        "context_support": context_support,
        "candidates": candidates,
        "grown": grown.astype(bool),
        "score": score,
        "hotspots": hotspots,
        "config": config.to_dict(),
        "stats": {
            "raw_seed_pixels": int(raw_seeds.sum()),
            "rejected_seed_pixels": int(raw_seeds.sum()) - seed_pixels,
            "seed_pixels": seed_pixels,
            "candidate_pixels": candidate_pixels,
            "active_pixels": active_pixels,
            "active_percent": round(100 * active_pixels / mask.size, 4),
            "hotspot_count": len(hotspots),
        },
        "warnings": [
            "Umbrales aproximados del SWIR-rule del paper; su referencia usa reflectancias antes del render, aquí se invierten los límites publicados sobre un JPEG cuantizado y con pérdida.",
            "La regla usa brillo y contraste R/B del render; el JPEG no permite verificar el orden de bandas ni recuperar reflectancias. Las equivalencias B12/B8A son solo la hipótesis de render del paper.",
            "El filtro contextual exige brillo anómalo respecto al fondo local; reduce candidatos uniformes, pero puede omitir frentes débiles o muy extensos.",
            "Los puntos son candidatos compatibles con fuego activo, no temperatura medida ni confirmación de incendio.",
        ],
    }


def render_active_overlay(base_rgb, active_mask):
    """Add an Indra solar-yellow layer over the affected-area view."""
    output = base_rgb.copy()
    color = np.array([255, 187, 33], dtype=np.float32)
    output[active_mask] = np.round(
        0.18 * output[active_mask].astype(np.float32) + 0.82 * color
    ).astype(np.uint8)
    contours, _ = cv2.findContours(
        active_mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )
    cv2.drawContours(output, contours, -1, (255, 255, 255), 1)
    return output
