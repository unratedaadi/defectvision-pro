import logging
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, time, timedelta
from math import isfinite
from time import perf_counter
from typing import Protocol
from uuid import uuid4

from PIL import Image
from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session

from app.config import ROOT, Settings
from app.errors import ApiError
from app.models import CATEGORIES, BatchJob, Inspection, ModelRegistry
from app.schemas.inspection import InspectionResult
from app.services.images import storage_path

logger = logging.getLogger(__name__)


@dataclass
class InferenceResult:
    score: float
    heatmap: Image.Image | None = None
    overlay: Image.Image | None = None
    latency_ms: float | None = None


class InferenceAdapter(Protocol):
    def predict(self, image: Image.Image, model: ModelRegistry) -> InferenceResult: ...


def utc_now():
    return datetime.now(UTC).replace(tzinfo=None)


def latest_models(db: Session) -> dict[str, ModelRegistry]:
    rows = db.scalars(select(ModelRegistry).order_by(ModelRegistry.created_at.desc(), ModelRegistry.id.desc()))
    models: dict[str, ModelRegistry] = {}
    for row in rows:
        models.setdefault(row.category, row)
    return models


def model_ready(model: ModelRegistry | None, adapter: InferenceAdapter | None) -> bool:
    return bool(model and adapter and model.status == "ready"
                and isfinite(model.calibrated_threshold)
                and (ROOT / model.checkpoint_path).is_file())


def require_model(db: Session, category: str, adapter: InferenceAdapter | None) -> ModelRegistry:
    model = latest_models(db).get(category)
    if not model_ready(model, adapter) or model is None:
        raise ApiError(503, "model_not_ready", f"No trained inference model is available for {category}.")
    return model


def get_inspection(db: Session, inspection_id: str) -> Inspection:
    record = db.get(Inspection, inspection_id)
    if record is None:
        raise ApiError(404, "inspection_not_found", "Inspection does not exist.")
    return record


def serialize(record: Inspection) -> InspectionResult:
    url = f"/api/inspections/{record.id}/media"
    return InspectionResult(
        id=record.id, filename=record.filename, category=record.category,
        prediction=record.prediction, score=record.anomaly_score, threshold=record.threshold_used,
        modelVersion=record.model_version, imageUrl=f"{url}/original",
        heatmapUrl=f"{url}/heatmap" if record.heatmap_path else None,
        overlayUrl=f"{url}/overlay" if record.overlay_path else None,
        source=record.source, batchId=record.batch_id, batchIndex=record.batch_index, createdAt=record.created_at,
        inferenceLatencyMs=record.inference_latency_ms,
    )


def remove_images(settings: Settings, names):
    for name in filter(None, names):
        try:
            storage_path(settings, name).unlink(missing_ok=True)
        except (OSError, ApiError):
            logger.exception("inspection_media_cleanup_failed")


def infer(adapter: InferenceAdapter, model: ModelRegistry, image: Image.Image) -> InferenceResult:
    try:
        started = perf_counter()
        result = adapter.predict(image, model)
        elapsed_ms = (perf_counter() - started) * 1000
        if not isfinite(result.score):
            raise ValueError("Non-finite anomaly score")
        if any(layer is not None and layer.size != image.size for layer in (result.heatmap, result.overlay)):
            raise ValueError("Inference images must match the original image dimensions")
        return replace(result, latency_ms=elapsed_ms)
    except ApiError:
        raise
    except Exception as error:
        logger.exception("inference_failed")
        raise ApiError(502, "inference_failed", "The model could not inspect this image.") from error


def new_inspection(model, result, filename, source, batch=None, batch_index=None):
    return Inspection(
        id=str(uuid4()), category=model.category, source=source, filename=filename,
        prediction="defective" if result.score >= model.calibrated_threshold else "normal",
        anomaly_score=result.score, threshold_used=model.calibrated_threshold, model_version=model.model_version,
        inference_latency_ms=result.latency_ms,
        batch_id=batch.id if batch else None, batch_index=batch_index, created_at=utc_now(),
    )


def persist_inspection(db: Session, settings: Settings, adapter: InferenceAdapter,
                       model: ModelRegistry, image: Image.Image, filename: str, source: str,
                       batch: BatchJob | None = None, batch_index: int | None = None) -> Inspection:
    result = infer(adapter, model, image)
    record = new_inspection(model, result, filename, source, batch, batch_index)
    return save_inspection(db, settings, record, image, result, batch)


def save_inspection(db, settings, record, image, result, batch=None):
    names = []
    try:
        for kind, pixels in (("original", image), ("heatmap", result.heatmap), ("overlay", result.overlay)):
            if pixels is None:
                continue
            name = f"{record.id}-{kind}.png"
            path = storage_path(settings, name)
            path.parent.mkdir(parents=True, exist_ok=True)
            names.append(name)
            pixels.save(path, format="PNG")
            setattr(record, f"{kind}_image_path" if kind == "original" else f"{kind}_path", name)
        db.add(record)
        if batch:
            batch.processed_images += 1
        db.commit()
    except Exception:
        db.rollback()
        remove_images(settings, names)
        raise
    return record


def inspection_filters(category=None, prediction=None, date_from=None, date_to=None):
    if date_from and date_to and date_from > date_to:
        raise ApiError(422, "invalid_date_range", "Start date must be on or before end date.")
    filters = []
    if category:
        filters.append(Inspection.category == category)
    if prediction:
        filters.append(Inspection.prediction == prediction)
    if date_from:
        filters.append(Inspection.created_at >= datetime.combine(date_from, time.min).isoformat(sep=" "))
    if date_to and date_to < date.max:
        next_day = datetime.combine(date_to + timedelta(days=1), time.min)
        filters.append(Inspection.created_at < next_day.isoformat(sep=" "))
    return filters


def ordered_inspections(filters, sort="newest"):
    order = (Inspection.created_at.asc(), Inspection.id.asc()) if sort == "oldest" else (
        Inspection.created_at.desc(), Inspection.id.desc(),
    )
    return select(Inspection).where(*filters).order_by(*order)


def history(db: Session, *, search: str = "", category=None, prediction=None,
            date_from=None, date_to=None, sort="newest", page: int = 1, page_size: int = 10):
    filters = inspection_filters(category, prediction, date_from, date_to)
    if term := search.strip():
        filters.append(or_(Inspection.id.icontains(term, autoescape=True),
                           Inspection.filename.icontains(term, autoescape=True)))
    # SQLite legacy transaction mode does not start a transaction for SELECT.
    db.connection().exec_driver_sql("BEGIN")
    total = db.scalar(select(func.count()).select_from(Inspection).where(*filters))
    records = db.scalars(ordered_inspections(filters, sort)
                         .offset((page - 1) * page_size).limit(page_size))
    return {"items": [serialize(record) for record in records], "total": total}


def counts(total, defective):
    return {"total": total, "normal": total - defective, "defective": defective,
            "defectPercentage": defective * 100 / total if total else None}


def analytics(db: Session, days: int, *, category=None, include_recent=False):
    end = utc_now().date()
    start = end - timedelta(days=days - 1)
    filters = inspection_filters(category=category, date_from=start, date_to=end)
    if include_recent:
        db.connection().exec_driver_sql("BEGIN")
    day = func.substr(Inspection.created_at, 1, 10)
    latency = Inspection.inference_latency_ms
    rows = db.execute(select(
        day, Inspection.category, func.count(Inspection.id),
        func.sum(case((Inspection.prediction == "defective", 1), else_=0)),
        func.sum(latency), func.count(latency),
    ).where(*filters).group_by(day, Inspection.category))
    by_category = {slug: [0, 0] for slug, _ in CATEGORIES if not category or slug == category}
    by_day = {(start + timedelta(days=offset)).isoformat(): [0, 0] for offset in range(days)}
    total = defective = timed = 0
    latency_sum = 0.0
    for key, slug, count, defects, duration, measured in rows:
        for group in (by_category[slug], by_day[key]):
            group[0] += count
            group[1] += defects
        total += count
        defective += defects
        timed += measured
        latency_sum += duration or 0
    return {
        **counts(total, defective),
        "categories": [{"category": slug, **counts(*value)} for slug, value in by_category.items()] if total else [],
        "trend": [{"date": key, **counts(*value)} for key, value in by_day.items()] if total else [],
        "averageInferenceLatencyMs": latency_sum / timed if timed else None,
        "timedInspections": timed,
        "recent": [serialize(row) for row in db.scalars(ordered_inspections(filters).limit(5))] if include_recent else [],
        "dateFrom": start.isoformat(),
        "dateTo": end.isoformat(),
    }
