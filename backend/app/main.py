import json
import logging
from contextlib import asynccontextmanager
from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.api import analytics, health, inspections
from app.config import Settings
from app.database import database_engine
from app.errors import ApiError, api_error
from app.schemas import Health
from app.services.batch import BatchWorker
from app.services.webcam import WebcamFrames
from app.services.images import UploadBodyLimit
from app.services.inspections import InferenceAdapter

logger = logging.getLogger("uvicorn.error")


def create_app(settings: Settings | None = None, inference: InferenceAdapter | None = None) -> FastAPI:
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.engine = database_engine(settings)
        worker = None
        try:
            if settings.patchcore_enabled and inference is None:
                from app.services.patchcore import PatchCoreAdapter

                adapter = PatchCoreAdapter(settings)
                with Session(app.state.engine) as db:
                    adapter.register(db)
                app.state.inference = adapter
            worker = BatchWorker(app.state.engine, settings)
            app.state.batch_worker = worker
            app.state.webcam = WebcamFrames()
            yield
        finally:
            if worker:
                await run_in_threadpool(worker.executor.shutdown)
            app.state.engine.dispose()

    app = FastAPI(title="DefectVision Pro", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.inference = inference
    app.add_exception_handler(ApiError, api_error)

    @app.exception_handler(SQLAlchemyError)
    async def database_error(request: Request, error: SQLAlchemyError):
        logger.error("database_error", exc_info=error)
        return await api_error(request, ApiError(503, "database_unavailable", "The database operation failed."))

    app.add_middleware(UploadBodyLimit, settings=settings)

    @app.middleware("http")
    async def log_request(request: Request, call_next):
        request_id = str(uuid4())
        start = perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            logger.exception("request_failed request_id=%s", request_id)
            response = JSONResponse({"detail": {"code": "internal_error", "message": "The request failed."}}, 500)
        response.headers["X-Request-ID"] = request_id
        route = request.scope.get("route")
        logger.info(json.dumps({
            "event": "http_request", "request_id": request_id, "method": request.method,
            "route": getattr(route, "path", None), "status": response.status_code,
            "duration_ms": round((perf_counter() - start) * 1000, 2),
        }))
        return response

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Content-Type"],
        expose_headers=["X-Request-ID", "Content-Disposition", "Location"],
    )
    app.include_router(health.router)
    app.add_api_route("/api/health", health.health, methods=["GET"], response_model=Health,
                      responses={503: {"model": Health}}, tags=["system"])
    app.include_router(inspections.router)
    app.include_router(analytics.router)
    return app


app = create_app()
