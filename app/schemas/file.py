from datetime import UTC, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models import FileStatus, FileType


class FileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    filename: str = Field(validation_alias="original_filename")
    file_type: FileType
    upload_size: int
    feature_count: int
    source_crs: str | None
    measurement_crs: str | None
    status: FileStatus
    created_at: datetime
    updated_at: datetime
    processing_error: str | None = None

    @field_validator("created_at", "updated_at")
    @classmethod
    def ensure_utc(cls, value: datetime) -> datetime:
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value
