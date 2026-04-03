"""Pydantic request/response models."""

from pydantic import BaseModel


class ProjectCreate(BaseModel):
    name: str
    product_type: str = "Cabinet Door"
    material_type: str = "wood"


class ProjectUpdate(BaseModel):
    name: str | None = None
    product_type: str | None = None
    material_type: str | None = None
    door_style: str | None = None
    corner_style: str | None = None
    style_notes: str | None = None
    gemini_model: str | None = None
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
    material_type: str
    door_style: str | None
    corner_style: str
    style_notes: str
    gemini_model: str
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
    signature_version: int = 0
    version_count: int = 0


class VersionSummary(BaseModel):
    version: int
    created_at: str
    material_type: str = "wood"
    door_style: str | None
    corner_style: str = "sharp"
    style_notes: str
    result_count: int


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
