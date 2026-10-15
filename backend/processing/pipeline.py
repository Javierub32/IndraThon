"""Shared pipeline used by FastAPI and the exploration notebook."""

from time import perf_counter

import cv2
import numpy as np

from .features import extract_features, working_image
from .geometry import clean_mask, extract_regions
from .segmentation import SegmentationConfig, reconstruct, segment, thresholds
from .active_fire import detect_active_fire, render_active_overlay
from .quality import inspect_pair, complete_quality


def render_overlay(rgb, mask, uncertain, opacity=0.38):
    output = rgb.copy()
    output[mask] = np.round((1 - opacity) * output[mask] + opacity * np.array([3, 108, 124])).astype(np.uint8)
    contours, _ = cv2.findContours(mask.astype(np.uint8), cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    cv2.drawContours(output, contours, -1, (255, 187, 33), 2)
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
    visible = (swir.copy() if true_rgb is None else
               cv2.resize(true_rgb, (width, height), interpolation=cv2.INTER_AREA))
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
        f = extract_features(swir[y:end], None if true_rgb is None else visible[y:end])
        uncertain[y:end] = f["uncertain"]
        refined[y:end] |= band[y:end] & (f["score"] >= low) & f["valid"]
    refined &= ~uncertain
    # New boundary candidates must remain connected to the coarse detection.
    refined = reconstruct(refined & up.astype(bool), refined)
    return refined, swir, visible


def analyze(swir_rgb, true_rgb=None, config=None, original_size=None, active_fire=False):
    started = perf_counter()
    config = config or SegmentationConfig()
    if true_rgb is not None and swir_rgb.shape != true_rgb.shape:
        raise ValueError("True Color y SWIR deben tener las mismas dimensiones y el mismo encuadre.")
    if swir_rgb.ndim != 3 or swir_rgb.shape[2] != 3 or min(swir_rgb.shape[:2]) < 32:
        raise ValueError("Se necesitan imágenes RGB de al menos 32 × 32 píxeles.")
    original_width, original_height = original_size or (swir_rgb.shape[1], swir_rgb.shape[0])
    quality = inspect_pair(swir_rgb, true_rgb)
    swir_only = true_rgb is None
    swir = working_image(swir_rgb, config.max_side)
    height, width = swir.shape[:2]
    visible = (swir.copy() if swir_only else
               cv2.resize(true_rgb, (width, height), interpolation=cv2.INTER_AREA))
    features = extract_features(swir, None if swir_only else visible)
    if quality["uninformative"]:
        features["uncertain"][:] = True
    segmented = segment(features, config)
    cleaned = clean_mask(segmented["grown"], features["valid"], features["uncertain"], config)
    mask, refined_swir, refined_visible = refine_boundary(cleaned, swir_rgb, true_rgb, config) if config.refine and not quality["uninformative"] else (cleaned, None, None)
    if refined_swir is not None:
        swir, visible = refined_swir, refined_visible
        uncertain = np.zeros(mask.shape, dtype=bool)
        valid = np.any(swir > 3, axis=2) & np.any(visible > 3, axis=2)
        final_seeds = np.zeros(mask.shape, dtype=bool)
        high, _ = thresholds(config)
        for y in range(0, mask.shape[0], 384):
            f = extract_features(swir[y:y + 384], None if swir_only else visible[y:y + 384])
            uncertain[y:y + 384] = f["uncertain"]
            final_seeds[y:y + 384] = (f["score"] >= high) & f["valid"] & ~f["uncertain"] & f["seed_allowed"]
        mask = clean_mask(mask, valid, uncertain, config)
        active_uncertain = uncertain.copy()
        active_valid = valid.copy() & (not quality["uninformative"])
    else:
        uncertain, valid = features["uncertain"], features["valid"]
        final_seeds = segmented["seeds"]
        active_uncertain = uncertain.copy()
        active_valid = valid.copy() & (not quality["uninformative"])
    # No fragment may survive solely by having grown through an occluded area.
    mask = reconstruct(final_seeds, mask)
    uncertain = uncertain | ~valid
    labels = np.zeros(mask.shape, dtype=np.uint8)
    labels[uncertain] = 255
    labels[mask] = 1
    regions, perimeter = extract_regions(mask, (original_width, original_height), config.simplify_pixels)
    fire = None
    overlay = render_overlay(visible, mask, uncertain)
    if active_fire:
        fire = detect_active_fire(
            swir, active_uncertain, (original_width, original_height), observation_valid=active_valid
        )
        fire["overlay"] = render_active_overlay(overlay, fire["mask"])
        fire["labels"] = labels.copy()
        fire["labels"][fire["mask"]] = 2
    count = int(mask.sum())
    observable = int((~uncertain).sum())
    scale_area = original_width * original_height / mask.size
    area_m2 = count * scale_area * config.pixel_size_m ** 2
    for region in regions:
        region["area_hectares_estimated"] = round(region["area_working_pixels"] * scale_area * config.pixel_size_m ** 2 / 10000, 3)
        region["perimeter_m_estimated"] = round(region["perimeter_original_pixels_estimated"] * config.pixel_size_m, 2)
    if fire is not None:
        fire["stats"]["active_area_hectares_estimated"] = round(fire["stats"]["active_pixels"] * scale_area * config.pixel_size_m ** 2 / 10000, 3)
        for hotspot in fire["hotspots"]:
            hotspot["area_hectares_estimated"] = round(hotspot["area_analysis_pixels"] * scale_area * config.pixel_size_m ** 2 / 10000, 3)
    if swir_only:
        warnings = ["Análisis de una composición SWIR renderizada: no equivale a reflectancias ni a índices espectrales calibrados.",
                    f"Escala declarada: {config.pixel_size_m:g} m por píxel original cuadrado. Las medidas son estimaciones; la imagen no contiene georreferenciación para verificar la escala ni obtener coordenadas terrestres.",
                    "Modo solo SWIR: no se aplican filtros que requieren True Color para distinguir agua, vegetación, superficies claras, humo o nubes; estos factores pueden generar falsos positivos o zonas no evaluadas."]
    else:
        warnings = ["Análisis de colores de un JPEG: no son reflectancias ni índices espectrales calibrados.",
                    f"Escala declarada: {config.pixel_size_m:g} m por píxel original cuadrado. Las medidas son estimaciones; los JPEG no contienen georreferenciación para verificar la escala ni obtener coordenadas terrestres.",
                    "La máscara de incertidumbre es una heurística visual de humo/nube y zonas sin datos."]
    if not count:
        warnings.append("No se encontró una región con evidencia suficiente con estos parámetros.")
    if not swir_only:
        warnings.append("El encuadre se comprueba con correspondencias geométricas cuando hay textura suficiente; no se corrigen automáticamente desplazamientos.")
    quality = complete_quality(quality, mask, uncertain, fire)
    return {"config": config.to_dict(), "original_size": {"width": original_width, "height": original_height},
            "analysis_size": {"width": mask.shape[1], "height": mask.shape[0]},
            "coarse_size": {"width": width, "height": height}, "regions": regions,
            "spatial_resolution": {"original_pixel_m": config.pixel_size_m, "source": "user_declared", "georeferenced": False,
                                   "analysis_pixel_m_x": original_width / mask.shape[1] * config.pixel_size_m,
                                   "analysis_pixel_m_y": original_height / mask.shape[0] * config.pixel_size_m},
            "stats": {"affected_analysis_pixels": count, "affected_original_pixels_estimated": round(count * scale_area),
                      "uncertain_analysis_pixels": int(uncertain.sum()), "region_count": len(regions),
                      "affected_percent": round(100 * count / mask.size, 3),
                      "uncertain_percent": round(100 * uncertain.sum() / mask.size, 3),
                      "affected_observable_percent": round(100 * count / observable, 3) if observable else None,
                      "perimeter_original_pixels_estimated": round(perimeter, 2),
                      "affected_area_m2_estimated": round(area_m2, 2),
                      "affected_area_hectares_estimated": round(area_m2 / 10000, 3),
                      "perimeter_m_estimated": round(perimeter * config.pixel_size_m, 2),
                      "processing_ms": round((perf_counter() - started) * 1000)},
            "warnings": warnings, "quality": quality, "mask": mask, "labels": labels, "uncertain": uncertain,
            "true_rgb": visible, "has_true_color": not swir_only,
            "input_mode": "swir_only" if swir_only else "paired",
            "swir_rgb": swir, "active_fire": fire,
            "overlay": overlay,
            "steps": {"swir": working_image(swir_rgb, config.max_side), "true_color": visible,
                      **features, **segmented, "cleaned": cleaned}}
