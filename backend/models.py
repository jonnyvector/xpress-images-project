"""Pydantic request/response models."""

from pydantic import BaseModel


class ProjectCreate(BaseModel):
    name: str
    product_type: str = "Cabinet Door"


class ProjectUpdate(BaseModel):
    name: str | None = None
    product_type: str | None = None
    door_style: str | None = None
    style_notes: str | None = None
    selected_swatches: list[str] | None = None


class ResultItem(BaseModel):
    index: int
    wood_name: str


class ErrorItem(BaseModel):
    wood_name: str
    error: str


class ProjectResponse(BaseModel):
    id: str
    name: str
    product_type: str
    door_style: str | None
    style_notes: str
    selected_swatches: list[str]
    upload_filename: str | None
    has_signature: bool
    has_base_image: bool
    learning_status: str
    learning_error: str | None
    generation_status: str
    generation_completed: int
    generation_total: int
    results: list[ResultItem]
    errors: list[ErrorItem]
    retrying_indices: list[int] = []


class SwatchResponse(BaseModel):
    key: str
    name: str
    description: str | None = None
    swatch_image_url: str
    reference_image_url: str | None = None
    is_virtual: bool = False
    swatch_key: str | None = None


class StyleResponse(BaseModel):
    key: str
    name: str
    category: str


class GenerationStatusResponse(BaseModel):
    status: str
    completed: int
    total: int
    results: list[ResultItem]
    errors: list[ErrorItem]
    retrying_indices: list[int] = []


class SaveToFolderResponse(BaseModel):
    saved_to: str
    files: list[str]
