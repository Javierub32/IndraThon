"""Sparse active-fire candidates from a fixed-rendering Sentinel-2 SWIR JPEG.

Rule adapted from Mitra et al. (arXiv:2609.16199v1, Eqs. 2-4). The paper
applies its thresholds to converted Level-2A reflectance before rendering;
here the inverse of its published fixed rendering is only an approximation
because the app receives quantized, lossy JPEG composites.

Contextual support is checked at several neighborhood sizes. Component scores
are heuristic evidence summaries, not calibrated probabilities.
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
    context_scale_factors: tuple = (0.5, 1.0, 2.0)
    min_red_excess: float = 0.08
    min_context_z: float = 1.5
    uncertain_rescue_margin: float = 0.45

    def __post_init__(self):
        if not 0 < self.b12_candidate <= self.b12_seed <= self.b12_render_max:
            raise ValueError("Los umbrales de brillo activo deben ser positivos y ordenados.")
        if not 0 < self.ratio_candidate <= self.ratio_seed or self.b8a_render_max <= 0:
            raise ValueError("Los umbrales de contraste activo deben ser positivos y ordenados.")
        if not isinstance(self.growth_steps, int) or not 0 <= self.growth_steps <= 8 or not 1 <= self.min_component_pixels <= 100:
            raise ValueError("El crecimiento y el tamaño mínimo activos están fuera de rango.")
        if (not .002 <= self.context_radius_fraction <= .10 or not 0 <= self.min_red_excess <= 1
                or not 0 <= self.min_context_z <= 10 or not 0 <= self.uncertain_rescue_margin <= 1):
            raise ValueError("Los parámetros de contexto activo están fuera de rango.")
        scales = tuple(self.context_scale_factors)
        if (not scales or any(not np.isfinite(scale) or scale <= 0 for scale in scales)
                or tuple(sorted(set(scales))) != scales):
            raise ValueError("Las escalas de contexto deben ser positivas, únicas y crecientes.")

    def to_dict(self):
        return asdict(self)


def detect_active_fire(swir_rgb, uncertain=None, original_size=None, config=None, observation_valid=None):
    """Return a sparse active-fire candidate mask with soft visual uncertainty.

    Expected SWIR order is R=B12, G=B11, B=B8A using the paper's fixed
    rendering limits. Two 4-neighbour growth steps and a two-pixel sieve
    retain small hot targets while avoiding unbounded expansion. When an
    independent observation-valid mask is supplied, visual uncertainty does
    not veto strong seeds; it only removes pixels from contextual backgrounds.
    Calls without that mask keep the legacy hard-uncertainty behavior.
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
    soft_uncertainty = observation_valid is not None
    if soft_uncertainty:
        observation_valid = np.asarray(observation_valid, dtype=bool)
        if observation_valid.shape != (height, width):
            raise ValueError("La validez de observación debe compartir la cuadrícula SWIR.")

    red = swir_rgb[:, :, 0].astype(np.float32) / 255.0
    rho12 = red * config.b12_render_max
    rho8a = (swir_rgb[:, :, 2].astype(np.float32) / 255.0) * config.b8a_render_max
    ratio = np.divide(rho12, rho8a, out=np.full_like(rho12, np.inf), where=rho8a > 1e-6)
    spectral_valid = np.all(swir_rgb > 3, axis=2)
    valid = spectral_valid & (observation_valid if soft_uncertainty else ~uncertain)

    raw_seeds = valid & (rho12 >= config.b12_seed) & (ratio >= config.ratio_seed)
    candidates = valid & (rho12 >= config.b12_candidate) & (ratio >= config.ratio_candidate)
    seeds = raw_seeds.copy()
    context_support = raw_seeds.copy()
    context_votes = np.zeros((height, width), dtype=np.uint8)
    context_radii = []
    scale_support_pixels = []
    uncertainty_rescued_components = None
    if config.contextual_filter:
        background = (valid & ~uncertain & ~raw_seeds).astype(np.float32)
        context_radii = sorted({
            max(1, round(max(height, width) * config.context_radius_fraction * scale))
            for scale in config.context_scale_factors
        })
        context_support = np.zeros((height, width), dtype=bool)
        for radius in context_radii:
            kernel_size = (2 * radius + 1,) * 2
            count = cv2.boxFilter(background, -1, kernel_size, normalize=False, borderType=cv2.BORDER_CONSTANT)
            mean = cv2.boxFilter(red * background, -1, kernel_size, normalize=False, borderType=cv2.BORDER_CONSTANT) / np.maximum(count, 1)
            variance = cv2.boxFilter(red * red * background, -1, kernel_size, normalize=False, borderType=cv2.BORDER_CONSTANT) / np.maximum(count, 1) - mean * mean
            excess = red - mean
            z = excess / np.sqrt(np.maximum(variance, 0) + .015 ** 2)
            enough_background = count >= kernel_size[0] ** 2 * .25
            scale_support = raw_seeds & (excess >= config.min_red_excess) & (z >= config.min_context_z) & enough_background
            context_support |= scale_support
            context_votes += scale_support.astype(np.uint8)
            scale_support_pixels.append(int(scale_support.sum()))
        # Keep an entire seed component if it has local anomalous support;
        # support at any neighborhood size is sufficient. This preserves
        # small targets while allowing broad fronts to use wider context.
        n, seed_labels = cv2.connectedComponents(raw_seeds.astype(np.uint8), connectivity=8)
        context_supported_components = np.bincount(seed_labels[context_support], minlength=n) > 0
        supported = context_supported_components.copy()
        if soft_uncertainty:
            raw_seed_margin = np.minimum(
                np.clip((rho12 - config.b12_seed) / max(config.b12_render_max - config.b12_seed, 1e-6), 0, 1),
                np.clip(ratio / config.ratio_seed - 1.0, 0, 1),
            )
            strong_uncertain_seeds = raw_seeds & uncertain & (raw_seed_margin >= config.uncertain_rescue_margin)
            uncertainty_rescued_components = np.bincount(
                seed_labels[strong_uncertain_seeds], minlength=n
            ) > 0
            # An obscured component can pass without neighborhood contrast
            # only when its SWIR evidence is well above both seed thresholds.
            supported |= uncertainty_rescued_components
            uncertainty_rescued_components &= ~context_supported_components
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
    uncertainty_rescued_by_output = np.zeros(component_count, dtype=bool)
    if uncertainty_rescued_components is not None:
        rescued_seed_pixels = seeds & uncertainty_rescued_components[seed_labels]
        uncertainty_rescued_by_output = np.bincount(
            component_labels[rescued_seed_pixels], minlength=component_count
        ) > 0

    # A display-only spectral strength image. It is not a calibrated
    # probability and is not used in place of the rule.
    score = np.minimum(rho12 / config.b12_seed, ratio / config.ratio_seed)
    score = np.clip(score, 0, 1).astype(np.float32)
    score[~valid] = 0

    # Summarize each component's spectral margin and multi-scale context
    # support over its seeds. The result is a heuristic ranking, not a
    # probability. With the contextual filter disabled, omit these values.
    if config.contextual_filter:
        seed_spectral_margin = np.minimum(
            np.clip((rho12[seeds] - config.b12_seed) / max(config.b12_render_max - config.b12_seed, 1e-6), 0, 1),
            np.clip(ratio[seeds] / config.ratio_seed - 1.0, 0, 1),
        )
        seed_context_consistency = context_votes[seeds].astype(np.float32) / max(len(context_radii), 1)
        seed_confidence = 0.5 * seed_spectral_margin + 0.5 * seed_context_consistency
        if soft_uncertainty:
            seed_confidence *= np.where(uncertain[seeds], 0.5, 1.0)
        confidence_sum = np.bincount(
            component_labels[seeds], weights=seed_confidence, minlength=component_count
        )
        confidence_by_component = np.divide(
            confidence_sum, seed_counts, out=np.zeros_like(confidence_sum), where=seed_counts > 0
        )
        context_supported_seed_count = np.bincount(
            component_labels[seeds], weights=(context_votes[seeds] > 0).astype(np.float32),
            minlength=component_count
        )
        context_support_by_component = np.divide(
            context_supported_seed_count, seed_counts,
            out=np.zeros_like(context_supported_seed_count), where=seed_counts > 0
        )
        context_consistency_sum = np.bincount(
            component_labels[seeds], weights=seed_context_consistency, minlength=component_count
        )
        context_scale_support_by_component = np.divide(
            context_consistency_sum, seed_counts,
            out=np.zeros_like(context_consistency_sum), where=seed_counts > 0
        )
        uncertain_seed_count = np.bincount(
            component_labels[seeds], weights=uncertain[seeds].astype(np.float32), minlength=component_count
        )
        uncertain_seed_fraction_by_component = np.divide(
            uncertain_seed_count, seed_counts,
            out=np.zeros_like(uncertain_seed_count), where=seed_counts > 0
        )
    else:
        confidence_by_component = None

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
        if confidence_by_component is not None:
            hotspots[-1].update({
                "confidence_score": round(float(confidence_by_component[label]), 3),
                "context_support_fraction": round(float(context_support_by_component[label]), 3),
                "context_scale_support": round(float(context_scale_support_by_component[label]), 3),
                "uncertain_seed_fraction": round(float(uncertain_seed_fraction_by_component[label]), 3),
                "uncertainty_rescued": bool(uncertainty_rescued_by_output[label]),
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
            "context_radii_pixels": context_radii,
            "context_support_pixels_by_scale": scale_support_pixels,
            "uncertain_raw_seed_pixels": int((raw_seeds & uncertain).sum()),
            "uncertain_seed_pixels": int((seeds & uncertain).sum()),
            "uncertainty_rescued_hotspots": int((keep & uncertainty_rescued_by_output).sum()),
        },
        "warnings": [],
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
