from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="DV_", env_file=ROOT / ".env", extra="ignore"
    )
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    database_path: Path = ROOT / "storage" / "defectvision.db"
    image_storage: Path = ROOT / "storage" / "uploads"
    max_upload_bytes: int = Field(default=10 * 1024 * 1024, gt=0)
    max_image_pixels: int = Field(default=20_000_000, gt=0)
    max_batch_images: int = Field(default=20, ge=1, le=100)
    patchcore_enabled: bool = False
    patchcore_device: Literal["auto", "cpu", "mps", "cuda"] = "auto"
    models_path: Path = ROOT / "models"
