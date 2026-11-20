import numpy as np
import pytest

from ml.metrics import binary_metrics, pixel_metrics


def test_binary_metrics_use_frozen_predictions_and_ignore_missing_labels():
    metrics, curve = binary_metrics([
        {"label": label, "score": score, "prediction": int(score >= 0.5)}
        for label, score in [(0, 0.1), (0, 0.7), (0, 0.2), (1, 0.8), (1, 0.4), (1, 0.9), (None, 1)]
    ])
    assert metrics["confusion_matrix"] == [[2, 1], [1, 2]]
    assert metrics["precision"] == metrics["recall"] == pytest.approx(2 / 3)
    assert metrics["f1"] == pytest.approx(2 / 3)
    assert metrics["image_auroc"] == pytest.approx(8 / 9)
    assert curve[0] == {"fpr": 0, "tpr": 0}
    assert curve[-1] == {"fpr": 1, "tpr": 1}


def test_undefined_image_and_pixel_metrics_are_null():
    metrics, curve = binary_metrics([{"label": 0, "score": 0.1, "prediction": 0}])
    assert metrics["confusion_matrix"] == [[1, 0], [0, 0]]
    assert all(metrics[key] is None for key in ("image_auroc", "precision", "recall", "f1"))
    assert curve == []
    assert pixel_metrics([np.zeros(4)], [np.arange(4)])["pixel_auroc"] is None
    assert pixel_metrics([], [])["pixel_auroc"] is None
    assert pixel_metrics([np.array([0, 1, 0, 1])], [np.array([0.1, 0.9, 0.2, 0.8])])["pixel_auroc"] == 1
