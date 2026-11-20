from datetime import date
from io import BytesIO
from typing import Annotated, Literal

from fastapi import APIRouter, File, Form, Query, Request, Response, UploadFile
from fastapi.responses import FileResponse
from PIL import Image

from app.database import DB
from app.errors import ApiError
from app.models import BatchJob
from app.schemas.inspection import BatchResult, Category, ErrorResponse, InspectionPage, InspectionResult, Prediction, WebcamPreview
from app.services import inspections as service
from app.services.batch import snapshot
from app.services.images import decode, display_name, storage_path

router = APIRouter(prefix="/api", tags=["inspections"])
upload_errors = {
    413: {"model": ErrorResponse, "description": "Upload limit exceeded"},
    502: {"model": ErrorResponse, "description": "Inference failed"},
    503: {"model": ErrorResponse, "description": "Model not ready"},
}


@router.post("/inspect", response_model=InspectionResult, status_code=201, responses=upload_errors)
def inspect(request: Request, db: DB, file: Annotated[UploadFile, File()],
            category: Annotated[Category, Form()],
            source: Annotated[Literal["upload", "webcam"], Form()] = "upload"):
    settings = request.app.state.settings
    image = decode(file, settings)
    adapter = request.app.state.inference
    model = service.require_model(db, category, adapter)
    return service.serialize(service.persist_inspection(
        db, settings, adapter, model, image, display_name(file), source,
    ))


@router.post("/inspect/batch", response_model=BatchResult, status_code=202,
             responses={**upload_errors, 429: {"model": ErrorResponse}})
def inspect_batch(request: Request, response: Response, db: DB, category: Annotated[Category, Form()],
                  files: Annotated[list[UploadFile], File(min_length=1)]):
    settings = request.app.state.settings
    if len(files) > settings.max_batch_images:
        raise ApiError(413, "batch_too_large", "Batch exceeds the configured image count.")
    adapter = request.app.state.inference
    model = service.require_model(db, category, adapter)
    job = request.app.state.batch_worker.submit(db, model, adapter, files)
    response.headers["Location"] = f"/api/inspect/batch/{job.id}"
    return snapshot(db, job)


@router.get("/inspect/batch/{id}", response_model=BatchResult)
def batch_status(id: str, db: DB):
    job = db.get(BatchJob, id)
    if job is None:
        raise ApiError(404, "batch_not_found", "Batch job does not exist.")
    return snapshot(db, job)


@router.post("/inspect/webcam", response_model=WebcamPreview,
             responses={**upload_errors, 429: {"model": ErrorResponse}})
def preview_webcam(request: Request, response: Response, db: DB,
                   file: Annotated[UploadFile, File()], category: Annotated[Category, Form()]):
    state = request.app.state
    model = service.require_model(db, category, state.inference)
    image = decode(file, state.settings, pixel_limit=1280 * 960)
    response.headers["Cache-Control"] = "no-store"
    return state.webcam.preview(state.inference, model, image, display_name(file))


@router.post("/inspect/webcam/{id}/save", response_model=InspectionResult)
def save_webcam(id: str, request: Request, db: DB):
    return request.app.state.webcam.save(id, db, request.app.state.settings)


@router.get("/inspections", response_model=InspectionPage)
def list_inspections(db: DB, search: Annotated[str, Query(max_length=255)] = "",
                     category: Category | Literal[""] = "",
                     prediction: Prediction | Literal[""] = "",
                     day: Annotated[date | None, Query(alias="date")] = None,
                     date_from: Annotated[date | None, Query(alias="dateFrom")] = None,
                     date_to: Annotated[date | None, Query(alias="dateTo")] = None,
                     sort: Literal["newest", "oldest"] = "newest",
                     page: Annotated[int, Query(ge=1, le=1_000_000)] = 1,
                     page_size: Annotated[int, Query(alias="pageSize", ge=1, le=100)] = 10):
    if day and (date_from or date_to):
        raise ApiError(422, "invalid_date_range", "Use either a single date or a date range.")
    return service.history(db, search=search, category=category, prediction=prediction,
                           date_from=day or date_from, date_to=day or date_to,
                           sort=sort, page=page, page_size=page_size)


@router.get("/inspections/{id}", response_model=InspectionResult, responses={404: {"model": ErrorResponse}})
def inspection_detail(id: str, db: DB):
    return service.serialize(service.get_inspection(db, id))


@router.delete("/inspections/{id}", status_code=204, responses={404: {"model": ErrorResponse}})
def delete_inspection(id: str, request: Request, db: DB):
    record = service.get_inspection(db, id)
    names = (record.original_image_path, record.heatmap_path, record.overlay_path)
    db.delete(record)
    db.commit()
    service.remove_images(request.app.state.settings, names)
    return Response(status_code=204)


@router.get("/inspections/{id}/media/{kind}", response_class=FileResponse,
            responses={200: {"content": {"image/png": {}}}, 404: {"model": ErrorResponse}})
def media(id: str, kind: Literal["original", "heatmap", "overlay", "thumbnail"], request: Request, db: DB):
    record = service.get_inspection(db, id)
    name = {"original": record.original_image_path, "thumbnail": record.original_image_path, "heatmap": record.heatmap_path,
            "overlay": record.overlay_path}[kind]
    if name:
        path = storage_path(request.app.state.settings, name)
        if path.is_file():
            if kind == "thumbnail":
                try:
                    with Image.open(path) as image, BytesIO() as output:
                        image.thumbnail((120, 120))
                        image.save(output, format="PNG")
                        return Response(output.getvalue(), media_type="image/png",
                                        headers={"Cache-Control": "no-store"})
                except (OSError, Image.DecompressionBombError) as error:
                    raise ApiError(404, "image_not_found", "Image is unavailable.") from error
            return FileResponse(path, media_type="image/png", headers={"Cache-Control": "no-store"})
    raise ApiError(404, "image_not_found", "Image is unavailable.")
