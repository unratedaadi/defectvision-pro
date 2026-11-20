"""Load and serve locally installed DefectVision PatchCore artifacts."""

import json
import logging
from datetime import UTC, datetime
from math import isfinite
from pathlib import Path
from pickle import UnpicklingError
from threading import Lock
from uuid import uuid4

from PIL import Image
from pydantic import TypeAdapter
from sqlalchemy import select
from sqlalchemy.orm import Session
from typing_extensions import TypedDict
from yaml import YAMLError

from app.config import ROOT, Settings
from app.errors import ApiError
from app.models import CATEGORIES, ModelRegistry
from app.services.inspections import InferenceResult
from ml.artifacts import load_metadata, read_config, read_json
from ml.dataset import digest
from ml.patchcore import Predictor, choose_device, load_model

logger = logging.getLogger(__name__)


class EvaluationMetrics(TypedDict, total=False):
    image_auroc: float | None
    auroc: float | None
    precision: float | None
    recall: float | None
    f1: float | None
    pixel_auroc: float | None
    average_inference_latency_ms: float | None
    confusion_matrix: tuple[tuple[int, int], tuple[int, int]]


class RocPoint(TypedDict):
    fpr: float
    tpr: float


class DeviceTiming(TypedDict):
    count: int
    mean_ms: float


class CalibrationDetails(TypedDict):
    method: str
    split: str
    sample_count: int


class EvaluationProvenance(TypedDict, total=False):
    dataset_split: str
    evaluated_at: str
    calibration: CalibrationDetails
    test_count: int
    labeled_count: int
    pixel_image_count: int
    latency_scope: str
    roc: list[RocPoint]
    inference_devices: list[str]
    pixel_metric_size: list[int]
    hardware: dict[str, str]
    latency_by_device: dict[str, DeviceTiming]


METRICS_SCHEMA = TypeAdapter(EvaluationMetrics)
PROVENANCE_SCHEMA = TypeAdapter(EvaluationProvenance)


def read_evaluation(run, category, meta, threshold):
    path = run / "evaluation.json"
    if not path.is_file():
        return None
    try:
        report = read_json(path)
        if (report["category"], report["version"], report["threshold"]) != (
            category, run.name, threshold["threshold"],
        ) or report["sha256"] != {**meta["sha256"], "threshold.json": digest(run / "threshold.json")}:
            raise ValueError("Evaluation does not match the installed checkpoint and threshold.")
        provenance = {key: value for key, value in report.items() if key not in ("images", "metrics")}
        # Validate the fields consumed by the API and UI while retaining other recorded metrics.
        METRICS_SCHEMA.validate_json(json.dumps(report["metrics"], allow_nan=False), strict=True)
        PROVENANCE_SCHEMA.validate_python(provenance, strict=True)
        metrics = {**report["metrics"], "_evaluation": provenance}
        json.dumps(metrics, allow_nan=False)
        return metrics
    except (OSError, ValueError, KeyError, TypeError):
        logger.warning("Skipping invalid evaluation metadata %s", path, exc_info=True)
        return None


def layers(anomaly, size):
    # Resize the score field before coloring so the overlay aligns to the decoded image.
    field = Image.fromarray(anomaly).resize(size, Image.Resampling.BILINEAR)
    low, high = field.getextrema()
    span = high - low
    if span == 0:
        intensity = Image.new("L", size)
    else:
        intensity = field.point(lambda value: (value - low) * (255.0 / span)).convert("L")
    green = intensity.point(lambda value: min(255, 2 * value))
    heatmap = Image.merge("RGB", (intensity, green, intensity.point(lambda value: 255 - value)))
    overlay = heatmap.copy()
    overlay.putalpha(intensity)
    return heatmap, overlay


class PatchCoreAdapter:
    def __init__(self, settings: Settings):
        self.root = (ROOT / settings.models_path.expanduser()).resolve()
        self.device = choose_device(settings.patchcore_device)
        self.lock = Lock()
        # Keep one loaded model per product, even if several versions are registered.
        self.cache = {}

    def checkpoint(self, category: str, version: str) -> Path:
        path = self.root / category / version / "patchcore.pt"
        if path.resolve() != path or path.parent.parent != self.root / category:
            raise ValueError("Checkpoint must be a regular local model artifact.")
        return path

    def register(self, db: Session):
        for category, _ in CATEGORIES:
            directory = self.root / category
            if not directory.is_dir():
                continue
            for run in sorted(directory.iterdir()):
                if not run.is_dir() or run.name.startswith(".") or not (run / "threshold.json").is_file():
                    continue
                try:
                    path = self.checkpoint(category, run.name)
                    meta = load_metadata(run, category)
                    threshold = read_json(run / "threshold.json")
                    if (threshold["category"], threshold["version"], threshold["sha256"]) != (
                        category, run.name, meta["sha256"],
                    ) or not isfinite(threshold["threshold"]):
                        raise ValueError("Invalid threshold metadata")
                    metrics = read_evaluation(run, category, meta, threshold)
                    row = db.scalar(select(ModelRegistry).where(
                        ModelRegistry.category == category, ModelRegistry.model_version == run.name,
                    ))
                    if row is None:
                        created = datetime.fromisoformat(meta["created_at"]).astimezone(UTC).replace(tzinfo=None)
                        row = ModelRegistry(id=str(uuid4()), category=category, model_version=run.name,
                                            status="ready", created_at=created)
                        db.add(row)
                    row.checkpoint_path = str(path)
                    row.calibrated_threshold = threshold["threshold"]
                    row.evaluation_metrics = metrics
                    db.commit()
                except (OSError, ValueError, KeyError, TypeError):
                    logger.warning("Skipping invalid PatchCore artifact %s", run, exc_info=True)
                    db.rollback()

    def predict(self, image: Image.Image, model: ModelRegistry) -> InferenceResult:
        with self.lock:
            try:
                path = self.checkpoint(model.category, model.model_version)
                if path != Path(model.checkpoint_path):
                    raise ValueError("Checkpoint path is outside the configured artifact layout.")
                run = path.parent
                signature = tuple((item.stat().st_mtime_ns, item.stat().st_size) for item in (
                    path, run / "model.json", run / "config.yaml", run / "threshold.json", run / "split.json",
                ))
                cached = self.cache.get(model.category)
                key = (path, signature, model.calibrated_threshold)
                if not cached or cached[0] != key:
                    meta = load_metadata(run, model.category)
                    threshold = read_json(run / "threshold.json")
                    if (threshold["category"], threshold["version"], threshold["sha256"], threshold["threshold"]) != (
                        model.category, model.model_version, meta["sha256"], model.calibrated_threshold,
                    ):
                        raise ValueError("Threshold does not match the registered model.")
                    config = read_config(run / "config.yaml")
                    if config["category"] != model.category:
                        raise ValueError("Model configuration category does not match.")
                    predictor = Predictor(load_model(path, config, self.device), config)
                    self.cache[model.category] = key, predictor
                else:
                    predictor = cached[1]
            except (OSError, ValueError, KeyError, TypeError, RuntimeError, EOFError, UnpicklingError, YAMLError) as error:
                logger.warning("PatchCore checkpoint unavailable for %s", model.category, exc_info=True)
                raise ApiError(503, "model_not_ready", "The trained checkpoint is missing or incompatible.") from error
            score, anomaly = predictor(image)
            heatmap, overlay = layers(anomaly, image.size)
            return InferenceResult(score, heatmap, overlay)
