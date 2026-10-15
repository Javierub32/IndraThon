"""Input quality and geometric correspondence checks; never accuracy scores."""
import cv2
import numpy as np

from .features import working_image


def inspect_pair(swir_rgb, true_rgb):
    swir = working_image(swir_rgb, 768)
    visible = cv2.resize(true_rgb, (swir.shape[1], swir.shape[0]), interpolation=cv2.INTER_AREA)
    flat = float(np.std(swir.astype(np.float32), axis=(0, 1)).max()) < 1.5
    valid = np.any(swir > 3, axis=2) & np.any(visible > 3, axis=2)
    checks = [{"id": "information", "label": "Información de la composición", "status": "review" if flat else "ok",
               "detail": "La composición SWIR carece de variación espacial suficiente; se evita clasificarla." if flat else "La composición contiene variación espacial utilizable."}]
    alignment = {"status": "unverified", "inliers": 0, "matches": 0}
    # Compare spatial structure rather than RGB intensities across composites.
    def structural_edges(image):
        gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
        return cv2.convertScaleAbs(cv2.magnitude(cv2.Sobel(gray, cv2.CV_32F, 1, 0), cv2.Sobel(gray, cv2.CV_32F, 0, 1)))

    orb = cv2.ORB_create(nfeatures=1800, fastThreshold=10)
    left, left_desc = orb.detectAndCompute(structural_edges(visible), None)
    right, right_desc = orb.detectAndCompute(structural_edges(swir), None)
    if left_desc is not None and right_desc is not None:
        pairs = cv2.BFMatcher(cv2.NORM_HAMMING).knnMatch(left_desc, right_desc, k=2)
        good = [pair[0] for pair in pairs if len(pair) == 2 and pair[0].distance < .75 * pair[1].distance]
        alignment["matches"] = len(good)
        if len(good) >= 12:
            source = np.float32([left[m.queryIdx].pt for m in good])
            target = np.float32([right[m.trainIdx].pt for m in good])
            matrix, inliers = cv2.estimateAffinePartial2D(source, target, method=cv2.RANSAC,
                                                       ransacReprojThreshold=3, maxIters=2000, confidence=.995)
            if matrix is not None and inliers is not None:
                support = int(inliers.sum())
                alignment["inliers"] = support
                if support >= 12 and support / len(good) >= .5:
                    h, w = swir.shape[:2]
                    corners = np.float32([[0, 0, 1], [w - 1, 0, 1], [0, h - 1, 1], [w - 1, h - 1, 1]])
                    displacement = float(np.linalg.norm(corners @ matrix.T - corners[:, :2], axis=1).max())
                    alignment.update({"status": "aligned", "max_displacement_check_pixels": round(displacement, 2),
                                      "check_size": [w, h]})
                    if displacement > max(5, max(h, w) * .008):
                        raise ValueError("Las composiciones presentan un desplazamiento, giro o escala incompatibles. Alinea True Color y SWIR antes de analizar; compartir dimensiones no garantiza el encuadre.")
    checks.append({"id": "alignment", "label": "Correspondencia espacial", "status": "ok" if alignment["status"] == "aligned" else "review",
                   "detail": f"Coincidencia geométrica: {alignment['inliers']} puntos concordantes." if alignment["status"] == "aligned" else "No hay suficientes correspondencias para verificar automáticamente el encuadre; revísalo visualmente."})
    coverage = round(100 * float(valid.mean()), 2)
    checks.append({"id": "coverage", "label": "Cobertura de ambas imágenes", "status": "ok" if coverage >= 90 else "review",
                   "detail": f"{coverage}% del encuadre tiene datos no negros en ambas composiciones."})
    clipped = round(100 * float((swir[:, :, 0] >= 253).mean()), 2)
    checks.append({"id": "clipping", "label": "Saturación del canal rojo", "status": "review" if clipped > 10 else "ok",
                   "detail": f"{clipped}% de píxeles alcanza el límite de visualización; en esa zona se pierde información radiométrica."})
    return {"status": "review_required" if any(c["status"] == "review" for c in checks) else "usable",
            "uninformative": flat, "checks": checks, "alignment": alignment,
            "paired_coverage_percent": coverage, "red_clipping_percent": clipped,
            "reference_validation": "not_provided",
            "representation": "rendered_rgb", "spectral_bands_verified": False}


def complete_quality(quality, mask, uncertain, fire):
    fraction = 100 * float(uncertain.mean())
    quality["checks"].append({"id": "observation", "label": "Superficie observable", "status": "review" if fraction > 30 else "ok",
                              "detail": f"{fraction:.1f}% de incertidumbre visual o falta de datos. Las zonas ocultas no se clasifican como ausencia de incendio."})
    if float(mask.mean()) > .65:
        quality["checks"].append({"id": "extent", "label": "Extensión excepcional", "status": "review",
                                  "detail": "La detección ocupa más del 65% del encuadre; revisa el render y los umbrales."})
    if fire is not None:
        quality["checks"].append({"id": "fire_context", "label": "Contraste local de los focos", "status": "ok",
                                  "detail": f"Se descartaron {fire['stats']['rejected_seed_pixels']} píxeles semilla sin contraste local suficiente. Es un filtro de candidatos, no una medida de precisión."})
    quality["status"] = "review_required" if any(c["status"] == "review" for c in quality["checks"]) else "usable"
    return quality
