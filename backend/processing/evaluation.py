"""Metrics against independent masks. Reference 255 means ignore."""
import cv2
import numpy as np


def evaluate_mask(predicted, reference, tolerance=2):
    if predicted.shape != reference.shape:
        raise ValueError("La referencia y la predicción deben compartir tamaño y cuadrícula.")
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
    boundary_f1 = 2 * precision * recall / (precision + recall) if precision is not None and recall is not None and precision + recall else None
    return {"tp": tp, "fp": fp, "fn": fn, "iou": ratio(tp, tp + fp + fn),
            "dice": ratio(2 * tp, 2 * tp + fp + fn), "precision": ratio(tp, tp + fp),
            "recall": ratio(tp, tp + fn), "boundary_f1": boundary_f1,
            "boundary_tolerance_pixels": tolerance, "reference_valid_fraction": float(valid.mean())}
