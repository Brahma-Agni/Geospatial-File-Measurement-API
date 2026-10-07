import os
from functools import lru_cache
from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./data/app.db"
    upload_dir: Path = Field(
        default_factory=lambda: (
            Path("/tmp/geospatial-uploads") if os.getenv("VERCEL") else Path("./data/uploads")
        )
    )
    max_upload_size_mb: int = Field(default_factory=lambda: 4 if os.getenv("VERCEL") else 50, gt=0)
    max_extracted_size_mb: int = Field(200, gt=0)
    max_archive_entries: int = Field(1000, gt=0)
    default_page_size: int = Field(100, gt=0)
    max_page_size: int = Field(500, gt=0)
    log_level: str = "INFO"
    delete_upload_after_processing: bool = Field(default_factory=lambda: bool(os.getenv("VERCEL")))
    vercel: bool = False

    @model_validator(mode="after")
    def validate_runtime(self) -> "Settings":
        if self.vercel and self.database_url.startswith("sqlite"):
            raise ValueError("DATABASE_URL must use an external database on Vercel")
        if self.vercel and self.max_upload_size_mb > 4:
            raise ValueError("MAX_UPLOAD_SIZE_MB cannot exceed 4 on Vercel")
        if self.vercel and not self.delete_upload_after_processing:
            raise ValueError("DELETE_UPLOAD_AFTER_PROCESSING must be true on Vercel")
        return self

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024

    @property
    def max_extracted_bytes(self) -> int:
        return self.max_extracted_size_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()
