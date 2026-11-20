import logging
from concurrent.futures import ThreadPoolExecutor
from tempfile import TemporaryFile
from threading import BoundedSemaphore
from uuid import uuid4

from fastapi import UploadFile
from sqlalchemy import inspect, select, update
from sqlalchemy.orm import Session

from app.errors import ApiError
from app.models import BatchJob, Inspection, ModelRegistry
from app.schemas.inspection import BatchResult
from app.services import inspections as service
from app.services.images import decode, display_name

logger = logging.getLogger(__name__)


def snapshot(db, job):
    records = db.scalars(select(Inspection).where(Inspection.batch_id == job.id)
                         .order_by(Inspection.batch_index, Inspection.created_at, Inspection.id)
                         .limit(job.processed_images))
    return BatchResult(
        id=job.id, category=job.category, status=job.status,
        total_images=job.total_images, processed_images=job.processed_images,
        failed_images=job.failed_images, created_at=job.created_at, completed_at=job.completed_at,
        items=[service.serialize(record) for record in records], errors=job.errors or [],
    )


def interrupt_jobs(db, job_id=None):
    jobs = update(BatchJob).where(BatchJob.status == "processing")
    if job_id:
        jobs = jobs.where(BatchJob.id == job_id)
    db.execute(jobs.values(status="failed", failed_images=BatchJob.total_images - BatchJob.processed_images,
                           completed_at=service.utc_now()))
    db.commit()


class BatchWorker:
    def __init__(self, engine, settings):
        self.engine = engine
        self.settings = settings
        # One outstanding batch per local API process, including upload staging.
        self.slot = BoundedSemaphore(1)
        if inspect(engine).has_table("batch_jobs"):
            with Session(engine) as db:
                interrupt_jobs(db)
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="inspection-batch")

    def submit(self, db, model, adapter, files):
        if not self.slot.acquire(blocking=False):
            raise ApiError(429, "batch_busy", "A batch is already running. Try again when it completes.")
        staged = []
        job = None
        try:
            for upload in files:
                stream = TemporaryFile()
                staged.append(UploadFile(stream, filename=display_name(upload)))
                stream.write(upload.file.read(self.settings.max_upload_bytes + 1))
                stream.seek(0)
            job = BatchJob(id=str(uuid4()), category=model.category, status="processing",
                           total_images=len(staged), processed_images=0, failed_images=0, errors=[],
                           created_at=service.utc_now())
            db.add(job)
            db.commit()
            self.executor.submit(self.process, job.id, model.id, adapter, staged)
        except BaseException:
            try:
                db.rollback()
                if job is not None:
                    interrupt_jobs(db, job.id)
            finally:
                self.release(staged)
            raise
        return job

    def release(self, files):
        try:
            for file in files:
                file.file.close()
        finally:
            self.slot.release()

    def process(self, job_id, model_id, adapter, files):
        try:
            with Session(self.engine, expire_on_commit=False) as db:
                job = db.get(BatchJob, job_id)
                model = db.get(ModelRegistry, model_id)
                for index, file in enumerate(files):
                    name = display_name(file)
                    try:
                        image = decode(file, self.settings)
                        if not service.model_ready(model, adapter):
                            raise ApiError(503, "model_not_ready", "The batch model is unavailable.")
                        service.persist_inspection(db, self.settings, adapter, model, image, name, "batch", job, index)
                    except ApiError as error:
                        job.errors = [*job.errors, {"index": index, "filename": name,
                                                   "code": error.code, "message": str(error)}]
                        job.failed_images += 1
                        db.commit()
                job.status = "partial" if job.failed_images and job.processed_images else (
                    "failed" if job.failed_images else "completed")
                job.completed_at = service.utc_now()
                db.commit()
        except Exception:
            logger.exception("batch_processing_failed job_id=%s", job_id)
            with Session(self.engine) as db:
                interrupt_jobs(db, job_id)
        finally:
            self.release(files)
