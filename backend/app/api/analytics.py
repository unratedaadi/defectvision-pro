from hashlib import sha256
from io import BytesIO
from math import isfinite
from pathlib import Path
from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, Path as PathParam, Query, Request, Response
from reportlab.pdfgen.canvas import Canvas
from sqlalchemy import select

from app.database import DB
from app.config import ROOT
from app.errors import ApiError
from app.models import BatchJob, CATEGORIES, ModelRegistry
from app.schemas.inspection import Analytics, Category, DayCounts, ErrorResponse, Evaluation, ModelStatus, Summary
from app.services.inspections import analytics, get_inspection, latest_models, model_ready
from app.services.batch import snapshot
from app.services.reports import batch_pdf, inspection_pdf

router = APIRouter(prefix="/api", tags=["analytics and models"])
Days = Annotated[int, Query(ge=1, le=365)]


@router.get("/models", response_model=list[ModelStatus])
def models(request: Request, db: DB):
    registered = latest_models(db)
    results = []
    for category, _ in CATEGORIES:
        model = registered.get(category)
        metrics = (model.evaluation_metrics or {}) if model else {}
        auroc = metrics.get("image_auroc", metrics.get("auroc"))
        ready = model_ready(model, request.app.state.inference)
        results.append(ModelStatus(
            category=category, ready=ready, status=model.status if model and model.status != "ready" else
            "ready" if ready else "unavailable",
            version=model.model_version if model else None,
            threshold=model.calibrated_threshold if model else None,
            auroc=auroc if isinstance(auroc, (int, float)) and isfinite(auroc) else None,
        ))
    return results


@router.get("/evaluation/{category}", response_model=Evaluation, responses={404: {"model": ErrorResponse}})
def evaluation(category: Category, db: DB):
    model = latest_models(db).get(category)
    if model is None or not model.evaluation_metrics:
        raise ApiError(404, "evaluation_unavailable", "No evaluation metrics have been recorded for this category.")
    metrics = dict(model.evaluation_metrics)
    provenance = metrics.pop("_evaluation", None)
    if isinstance(provenance, dict):
        samples = []
        for index in range(1, 4):
            sample = find_sample(provenance, index)
            if sample:
                query = {"version": model.model_version}
                if isinstance(sample.get("sha256"), str):
                    query["checksum"] = sample["sha256"]
                samples.append({**sample, "url": f"/api/evaluation/{category}/samples/{index}?{urlencode(query)}"})
        provenance = {**provenance, "samples": samples}
    else:
        provenance = None
    return Evaluation(category=category, modelVersion=model.model_version, metrics=metrics, provenance=provenance)


def find_sample(provenance, index):
    samples = provenance.get("samples") if isinstance(provenance, dict) else None
    if isinstance(samples, list):
        return next((item for item in samples if isinstance(item, dict)
                     and item.get("file") == f"localization-{index}.png" and isinstance(item.get("image"), str)), None)
    return None


@router.get("/evaluation/{category}/samples/{index}", response_class=Response,
            responses={200: {"content": {"image/png": {}}}, 404: {"model": ErrorResponse}})
def evaluation_sample(category: Category, index: Annotated[int, PathParam(ge=1, le=3)],
                      db: DB, request: Request, version: Annotated[str | None, Query(max_length=80)] = None,
                      checksum: Annotated[str | None, Query(pattern=r"^[a-f0-9]{64}$")] = None):
    model = db.scalar(select(ModelRegistry).where(ModelRegistry.category == category,
                      ModelRegistry.model_version == version)) if version is not None else latest_models(db).get(category)
    filename = f"localization-{index}.png"
    data = (model.evaluation_metrics or {}).get("_evaluation", {}) if model else {}
    sample = find_sample(data, index)
    if model and sample and (checksum is None or checksum == sample.get("sha256")):
        root = (ROOT / request.app.state.settings.models_path.expanduser()).resolve()
        run = (ROOT / Path(model.checkpoint_path)).parent.resolve()
        path = (run / filename).resolve()
        if run == root / category / model.model_version and path.parent == run and path.is_file():
            try:
                with path.open("rb") as stream:
                    content = stream.read(2_000_001)
                    expected = sample.get("sha256")
                    if len(content) <= 2_000_000 and content.startswith(b"\x89PNG\r\n\x1a\n") and (
                        expected is None or sha256(content).hexdigest() == expected
                    ):
                        return Response(content, media_type="image/png", headers={"Cache-Control": "no-store"})
            except OSError:
                pass
    raise ApiError(404, "sample_unavailable", "Evaluation sample is unavailable.")


@router.get("/analytics/summary", response_model=Summary)
def summary(db: DB, days: Days = 30, category: Category | None = None):
    return analytics(db, days, category=category)


@router.get("/analytics/trends", response_model=list[DayCounts])
def trends(db: DB, days: Days = 30, category: Category | None = None):
    return analytics(db, days, category=category)["trend"]


@router.get("/analytics/dashboard", response_model=Analytics)
def dashboard(db: DB, days: Days = 30, category: Category | None = None):
    return analytics(db, days, category=category, include_recent=True)


def pdf(filename: str, title: str, lines: list[str]) -> Response:
    output = BytesIO()
    canvas = Canvas(output)
    canvas.setTitle(title)
    canvas.setFont("Helvetica-Bold", 18)
    canvas.drawString(45, 780, title)
    canvas.setFont("Helvetica", 11)
    for index, line in enumerate(lines):
        canvas.drawString(45, 745 - 20 * index, line)
    canvas.save()
    return Response(output.getvalue(), media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.get("/reports/inspections.pdf", response_class=Response,
            responses={200: {"content": {"application/pdf": {}}}})
def aggregate_report(db: DB, days: Days = 30, category: Category | None = None):
    result = analytics(db, days, category=category)
    lines = [f"Reporting period: {days} days (UTC)", f"Inspections: {result['total']}",
             f"Defective: {result['defective']}"]
    if category:
        lines.append(f"Category filter: {category}")
    lines.extend(f"{row['category']}: {row['total']} inspected, {row['defective']} defective"
                 for row in result["categories"])
    return pdf("defectvision-inspection-report.pdf", "DefectVision Pro | Inspection summary", lines)


@router.get("/reports/{id}", response_class=Response,
            responses={200: {"content": {"application/pdf": {}}}, 404: {"model": ErrorResponse}})
def inspection_report(id: str, db: DB, request: Request):
    record = get_inspection(db, id)
    return Response(inspection_pdf(record, request.app.state.settings), media_type="application/pdf",
                    headers={"Content-Disposition": 'attachment; filename="defectvision-inspection.pdf"'})


@router.get("/reports/batch/{id}", response_class=Response,
            responses={200: {"content": {"application/pdf": {}}}, 404: {"model": ErrorResponse}})
def batch_report(id: str, db: DB):
    job = db.get(BatchJob, id)
    if job is None:
        raise ApiError(404, "batch_not_found", "Batch job does not exist.")
    return Response(batch_pdf(job, snapshot(db, job).items), media_type="application/pdf",
                    headers={"Content-Disposition": 'attachment; filename="defectvision-batch.pdf"'})
