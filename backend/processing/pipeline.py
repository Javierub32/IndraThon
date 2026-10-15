"""Shared pipeline used by FastAPI and the exploration notebook."""

from time import perf_counter

import cv2
import numpy as np

from .features import extract_features, working_image
from .geometry import clean_mask, extract_regions
from .segmentation import SegmentationConfig, reconstruct, segment, thresholds


def render_overlay(rgb, mask, uncertain, opacity=0.38):
    output = rgb.copy()
    output[mask] = np.round((1 - opacity) * output[mask] + opacity * np.array([249, 126, 40])).astype(np.uint8)
    contours, _ = cv2.findContours(mask.astype(np.uint8), cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    cv2.drawContours(output, contours, -1, (255, 220, 125), 2)
    return output


def refine_boundary(mask, swir_rgb, true_rgb, config):
    """Refine only a narrow boundary band at up to twice the coarse resolution.

    Bounded resolution avoids 61-megapixel float feature stacks. The output
    explicitly reports its actual analysis size; original pixel areas are estimates.
    """
    swir = working_image(swir_rgb, min(config.max_side * 2, 4096))
    if swir.shape[:2] == mask.shape:
        return mask, None, None
    height, width = swir.shape[:2]
    visible = cv2.resize(true_rgb, (width, height), interpolation=cv2.INTER_AREA)
    up = cv2.resize(mask.astype(np.uint8), (width, height), interpolation=cv2.INTER_NEAREST)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))
    outer = cv2.dilate(up, kernel).astype(bool)
    inner = cv2.erode(up, kernel).astype(bool)
    band = outer & ~inner
    uncertain = np.zeros_like(up, dtype=bool)
    refined = inner.copy()
    # Features are evaluated in bounded tiles, including all uncertainty pixels.
    _, low = thresholds(config)
    for y in range(0, height, 384):
        end = min(height, y + 384)
        f = extract_features(swir[y:end], visible[y:end])
        uncertain[y:end] = f["uncertain"]
        refined[y:end] |= band[y:end] & (f["score"] >= low) & f["valid"]
    refined &= ~uncertain
    # New boundary candidates must remain connected to the coarse detection.
    refined = reconstruct(refined & up.astype(bool), refined)
    return refined, swir, visible


def analyze(swir_rgb, true_rgb, config=None, original_size=None):
    started = perf_counter()
    config = config or SegmentationConfig()
    if swir_rgb.shape != true_rgb.shape:
        raise ValueError("True Color y SWIR deben tener las mismas dimensiones y el mismo encuadre.")
    if swir_rgb.ndim != 3 or swir_rgb.shape[2] != 3 or min(swir_rgb.shape[:2]) < 32:
        raise ValueError("Se necesitan imágenes RGB de al menos 32 × 32 píxeles.")
    original_width, original_height = original_size or (swir_rgb.shape[1], swir_rgb.shape[0])
    swir = working_image(swir_rgb, config.max_side)
    height, width = swir.shape[:2]
    visible = cv2.resize(true_rgb, (width, height), interpolation=cv2.INTER_AREA)
    features = extract_features(swir, visible)
    segmented = segment(features, config)
    cleaned = clean_mask(segmented["grown"], features["valid"], features["uncertain"], config)
    mask, refined_swir, refined_visible = refine_boundary(cleaned, swir_rgb, true_rgb, config) if config.refine else (cleaned, None, None)
    if refined_swir is not None:
        swir, visible = refined_swir, refined_visible
        uncertain = np.zeros(mask.shape, dtype=bool)
        valid = np.any(swir > 3, axis=2)
        for y in range(0, mask.shape[0], 384):
            uncertain[y:y + 384] = extract_features(swir[y:y + 384], visible[y:y + 384])["uncertain"]
        mask = clean_mask(mask, valid, uncertain, config)
    else:
        uncertain, valid = features["uncertain"], features["valid"]
    uncertain = uncertain | ~valid
    labels = np.zeros(mask.shape, dtype=np.uint8)
    labels[uncertain] = 255
    labels[mask] = 1
    regions, perimeter = extract_regions(mask, (original_width, original_height), config.simplify_pixels)
    count = int(mask.sum())
    observable = int((~uncertain).sum())
    scale_area = original_width * original_height / mask.size
    warnings = ["Análisis de colores de un JPEG: no son reflectancias ni índices espectrales calibrados.",
                "Área y perímetro en píxeles originales estimados; no hay georreferenciación ni escala métrica.",
                "La máscara de incertidumbre es una heurística visual de humo/nube y zonas sin datos."]
    if not count:
        warnings.append("No se encontró una región con evidencia suficiente con estos parámetros.")
    warnings.append("La coincidencia espacial se presupone por el encuadre; las imágenes no se registran automáticamente.")
    return {"config": config.to_dict(), "original_size": {"width": original_width, "height": original_height},
            "analysis_size": {"width": mask.shape[1], "height": mask.shape[0]},
            "coarse_size": {"width": width, "height": height}, "regions": regions,
            "stats": {"affected_analysis_pixels": count, "affected_original_pixels_estimated": round(count * scale_area),
                      "uncertain_analysis_pixels": int(uncertain.sum()), "region_count": len(regions),
                      "affected_percent": round(100 * count / mask.size, 3),
                      "uncertain_percent": round(100 * uncertain.sum() / mask.size, 3),
                      "affected_observable_percent": round(100 * count / observable, 3) if observable else None,
                      "perimeter_original_pixels_estimated": round(perimeter, 2),
                      "processing_ms": round((perf_counter() - started) * 1000)},
            "warnings": warnings, "mask": mask, "labels": labels, "uncertain": uncertain,
            "true_rgb": visible, "swir_rgb": swir,
            "overlay": render_overlay(visible, mask, uncertain),
            "steps": {"swir": working_image(swir_rgb, config.max_side), "true_color": cv2.resize(true_rgb, (width, height)),
                      **features, **segmented, "cleaned": cleaned}}
