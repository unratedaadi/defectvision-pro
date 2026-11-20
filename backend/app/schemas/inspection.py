from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_serializer

Category = Literal["bottle", "metal_nut", "tile"]
Prediction = Literal["normal", "defective"]
Source = Literal["upload", "batch", "webcam"]


class InspectionResult(BaseModel):
    id: str
    filename: str
    category: Category
    prediction: Prediction
    score: float
    threshold: float
    modelVersion: str
    imageUrl: str
    heatmapUrl: str | None
    overlayUrl: str | None
    source: Source
    batchId: str | None
    batchIndex: int | None = None
    inferenceLatencyMs: float | None = None
    createdAt: datetime

    @field_serializer("createdAt")
    def utc_timestamp(self, value: datetime):
        return value.replace(tzinfo=UTC).isoformat()


class InspectionPage(BaseModel):
    items: list[InspectionResult]
    total: int


class WebcamPreview(InspectionResult):
    expiresIn: int


class ModelStatus(BaseModel):
    category: Category
    ready: bool
    status: str
    version: str | None
    threshold: float | None
    auroc: float | None


class Evaluation(BaseModel):
    category: Category
    modelVersion: str
    metrics: dict
    provenance: dict | None = None


class BatchFailure(BaseModel):
    index: int
    filename: str
    code: str
    message: str


class BatchResult(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    category: Category
    status: Literal["processing", "completed", "partial", "failed"]
    total_images: int
    processed_images: int
    failed_images: int
    created_at: datetime
    completed_at: datetime | None
    items: list[InspectionResult] = []
    errors: list[BatchFailure] = []


class Counts(BaseModel):
    total: int
    normal: int
    defective: int
    defectPercentage: float | None


class CategoryCounts(Counts):
    category: Category


class DayCounts(Counts):
    date: str


class Summary(Counts):
    categories: list[CategoryCounts]
    averageInferenceLatencyMs: float | None
    timedInspections: int


class Analytics(Summary):
    trend: list[DayCounts]
    recent: list[InspectionResult]
    dateFrom: str
    dateTo: str


class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    detail: ErrorDetail
