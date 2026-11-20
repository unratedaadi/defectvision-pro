from datetime import datetime

from sqlalchemy import JSON, CheckConstraint, Float, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

CATEGORIES = (
    ("bottle", "Bottle"),
    ("metal_nut", "Metal Nut"),
    ("tile", "Tile"),
)


class ProductCategory(Base):
    __tablename__ = "product_categories"
    __table_args__ = (
        CheckConstraint("slug IN ('bottle', 'metal_nut', 'tile')", name="category_slug"),
    )

    slug: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)


class ModelRegistry(Base):
    __tablename__ = "model_registry"
    __table_args__ = (
        UniqueConstraint("category", "model_version"),
        CheckConstraint("status IN ('ready', 'inactive', 'failed')", name="model_status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    category: Mapped[str] = mapped_column(ForeignKey("product_categories.slug"), index=True)
    model_version: Mapped[str] = mapped_column(String(80))
    checkpoint_path: Mapped[str]
    calibrated_threshold: Mapped[float]
    status: Mapped[str]
    evaluation_metrics: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(server_default=func.current_timestamp())


class BatchJob(Base):
    __tablename__ = "batch_jobs"
    __table_args__ = (
        CheckConstraint("status IN ('processing', 'completed', 'partial', 'failed')", name="batch_status"),
        CheckConstraint(
            "total_images > 0 AND processed_images >= 0 AND failed_images >= 0 "
            "AND processed_images + failed_images <= total_images", name="batch_counts",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    category: Mapped[str] = mapped_column(ForeignKey("product_categories.slug"), index=True)
    status: Mapped[str]
    total_images: Mapped[int]
    processed_images: Mapped[int]
    failed_images: Mapped[int]
    errors: Mapped[list | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(server_default=func.current_timestamp())
    completed_at: Mapped[datetime | None]


class Inspection(Base):
    __tablename__ = "inspections"
    __table_args__ = (
        CheckConstraint("prediction IN ('normal', 'defective')", name="inspection_prediction"),
        CheckConstraint("source IN ('upload', 'batch', 'webcam')", name="inspection_source"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    category: Mapped[str] = mapped_column(ForeignKey("product_categories.slug"), index=True)
    prediction: Mapped[str]
    anomaly_score: Mapped[float]
    inference_latency_ms: Mapped[float | None] = mapped_column(Float)
    threshold_used: Mapped[float]
    model_version: Mapped[str] = mapped_column(String(80))
    filename: Mapped[str] = mapped_column(String(255))
    original_image_path: Mapped[str]
    heatmap_path: Mapped[str | None]
    overlay_path: Mapped[str | None]
    source: Mapped[str]
    batch_id: Mapped[str | None] = mapped_column(ForeignKey("batch_jobs.id"), index=True)
    batch_index: Mapped[int | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.current_timestamp(), index=True)
