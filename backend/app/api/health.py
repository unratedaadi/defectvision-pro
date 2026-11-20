import logging

from fastapi import APIRouter, Request, Response
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.models import BatchJob, Inspection, ModelRegistry, ProductCategory
from app.schemas import Category, Health

router = APIRouter(prefix="/api/v1", tags=["system"])
logger = logging.getLogger(__name__)


@router.get("/health", responses={503: {"model": Health}})
def health(request: Request, response: Response) -> Health:
    try:
        with request.app.state.engine.connect() as connection:
            # SQLite resolves the mapped columns without reading any rows.
            for model in (Inspection, BatchJob, ModelRegistry):
                connection.execute(select(model).limit(0))
            rows = connection.execute(
                select(ProductCategory.slug, ProductCategory.name).order_by(ProductCategory.slug)
            ).all()
    except SQLAlchemyError:
        logger.exception("Database readiness check failed")
        response.status_code = 503
        return Health(status="degraded", database="unavailable", categories=[])
    return Health(
        status="ok",
        database="ready",
        categories=[Category(slug=row.slug, name=row.name) for row in rows],
    )
