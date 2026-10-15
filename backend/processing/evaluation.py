"""Metrics against independent masks. Reference 255 means ignore."""
import cv2
import numpy as np


def evaluate_mask(predicted, reference, tolerance=2):
    predicted, reference = np.asarray(predicted), np.asarray(reference)
    if predicted.shape != reference.shape:
        raise ValueError("La referencia y la predicción deben compartir tamaño y cuadrícula.")
    if predicted.ndim != 2 or not np.isin(predicted, [0, 1]).all() or not np.isin(reference, [0, 1, 255]).all():
        raise ValueError("Predicción binaria 0/1 y referencia 0/1/255 de un solo canal requeridas.")
    if not isinstance(tolerance, int) or not 0 <= tolerance <= 100:
        raise ValueError("La tolerancia de contorno debe ser un entero entre 0 y 100 píxeles.")
    valid = reference != 255
    predicted = (predicted == 1) & valid
    expected = (reference == 1) & valid
    tp = int((predicted & expected).sum())
    fp = int((predicted & ~expected & valid).sum())
    fn = int((~predicted & expected).sum())

    def ratio(numerator, denominator):
        return float(numerator / denominator) if denominator else None

    kernel = np.ones((3, 3), np.uint8)
    pred_edge = predicted & ~cv2.erode(predicted.astype(np.uint8), kernel).astype(bool)
    true_edge = expected & ~cv2.erode(expected.astype(np.uint8), kernel).astype(bool)
    # Ignore boundaries created only by the edge of an unobserved reference.
    safe = cv2.erode(valid.astype(np.uint8), np.ones((2 * tolerance + 3,) * 2, np.uint8)).astype(bool)
    pred_edge &= safe
    true_edge &= safe
    neighborhood = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * tolerance + 1,) * 2)
    precision = ratio((pred_edge & cv2.dilate(true_edge.astype(np.uint8), neighborhood).astype(bool)).sum(), pred_edge.sum())
    recall = ratio((true_edge & cv2.dilate(pred_edge.astype(np.uint8), neighborhood).astype(bool)).sum(), true_edge.sum())
    boundary_f1 = (2 * precision * recall / (precision + recall) if precision + recall else 0.0) if precision is not None and recall is not None else None
    return {"tp": tp, "fp": fp, "fn": fn, "iou": ratio(tp, tp + fp + fn),
            "dice": ratio(2 * tp, 2 * tp + fp + fn), "precision": ratio(tp, tp + fp),
            "recall": ratio(tp, tp + fn), "boundary_f1": boundary_f1,
            "boundary_tolerance_pixels": tolerance, "reference_valid_fraction": float(valid.mean())}


def evaluate_components(predicted, reference, min_iou=0.1):
    """One-to-one maximum-cardinality component matching at an IoU threshold.

    Ignore pixels are removed before computing eight-connected components.
    Components wholly inside ignored areas do not count as detections.
    """
    evaluate_mask(predicted, reference)
    if not 0 < min_iou <= 1:
        raise ValueError("El IoU mínimo debe estar entre 0 y 1.")
    valid = reference != 255
    npred, pred = cv2.connectedComponents(((predicted == 1) & valid).astype(np.uint8), connectivity=8)
    ntrue, truth = cv2.connectedComponents(((reference == 1) & valid).astype(np.uint8), connectivity=8)
    pa, ta = np.bincount(pred.ravel()), np.bincount(truth.ravel())
    overlap = (pred > 0) & (truth > 0)
    pairs, counts = np.unique(np.column_stack((pred[overlap], truth[overlap])), axis=0, return_counts=True)
    edges = {}
    for (p, t), intersection in zip(pairs, counts):
        iou = intersection / (pa[p] + ta[t] - intersection)
        if iou >= min_iou:
            edges.setdefault(int(p), []).append((int(t), float(iou)))
    # Iterative augmenting paths avoid recursion limits on many small hotspots.
    matched_true, matched_pred = {}, {}
    for start in edges:
        queue, parent, seen_true = [start], {start: None}, set()
        free = None
        for p in queue:
            for t, _ in sorted(edges.get(p, []), key=lambda item: -item[1]):
                if t in seen_true:
                    continue
                seen_true.add(t)
                if t not in matched_true:
                    free = (p, t)
                    break
                next_p = matched_true[t]
                if next_p not in parent:
                    parent[next_p] = (p, t)
                    queue.append(next_p)
            if free is not None:
                break
        while free is not None:
            p, t = free
            matched_true[t], matched_pred[p] = p, t
            free = parent[p]
    tp, predicted_count, reference_count = len(matched_pred), npred - 1, ntrue - 1
    return {"matched": tp, "false_components": predicted_count - tp, "missed_components": reference_count - tp,
            "predicted_components": predicted_count, "reference_components": reference_count,
            "precision": tp / predicted_count if predicted_count else None,
            "recall": tp / reference_count if reference_count else None,
            "minimum_iou": min_iou, "matching": "one_to_one_maximum_cardinality", "connectivity": 8}
