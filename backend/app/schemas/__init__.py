from typing import Literal

from pydantic import BaseModel


class Category(BaseModel):
    slug: str
    name: str


class Health(BaseModel):
    status: Literal["ok", "degraded"]
    database: Literal["ready", "unavailable"]
    categories: list[Category]
