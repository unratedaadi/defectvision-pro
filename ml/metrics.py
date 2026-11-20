"""Evaluation metrics for defect-positive binary classification."""

import numpy as np
from sklearn.metrics import average_precision_score, confusion_matrix, roc_auc_score, roc_curve


def binary_metrics(rows):
    labeled = [row for row in rows if row["label"] in (0, 1)]
    labels = [row["label"] for row in labeled]
    scores = [row["score"] for row in labeled]
    tn, fp, fn, tp = confusion_matrix(
        labels, [row["prediction"] for row in labeled], labels=[0, 1],
    ).ravel()
    both = len(set(labels)) == 2
    curve = []
    if both:
        fpr, tpr, _ = roc_curve(labels, scores)
        curve = [{"fpr": float(x), "tpr": float(y)} for x, y in zip(fpr, tpr, strict=True)]
    return {
        "image_auroc": roc_auc_score(labels, scores) if both else None,
        "image_average_precision": average_precision_score(labels, scores) if any(labels) else None,
        "precision": float(tp / (tp + fp)) if tp + fp else None,
        "recall": float(tp / (tp + fn)) if tp + fn else None,
        "f1": float(2 * tp / (2 * tp + fp + fn)) if 2 * tp + fp + fn else None,
        "confusion_matrix": [[int(tn), int(fp)], [int(fn), int(tp)]],
    }, curve


def pixel_metrics(labels, scores):
    if not labels:
        return {"pixel_auroc": None, "pixel_average_precision": None}
    truth = np.concatenate(labels)
    predictions = np.concatenate(scores)
    return {
        "pixel_auroc": roc_auc_score(truth, predictions) if truth.any() and not truth.all() else None,
        "pixel_average_precision": average_precision_score(truth, predictions) if truth.any() else None,
    }
