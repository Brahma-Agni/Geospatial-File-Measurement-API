from pathlib import Path

import pytest
from pydantic import ValidationError

from app.config import Settings
from app.database import normalize_database_url


def test_vercel_defaults_use_ephemeral_storage_and_platform_upload_limit(monkeypatch):
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.delenv("UPLOAD_DIR")
    settings = Settings(database_url="postgresql://user:pass@example.test/database", _env_file=None)
    assert settings.vercel is True
    assert settings.upload_dir == Path("/tmp/geospatial-uploads")
    assert settings.max_upload_size_mb == 4
    assert settings.delete_upload_after_processing is True


def test_vercel_rejects_sqlite(monkeypatch):
    monkeypatch.setenv("VERCEL", "1")
    with pytest.raises(ValidationError, match="external database"):
        Settings(_env_file=None)


def test_vercel_rejects_configuration_above_platform_payload_limit(monkeypatch):
    monkeypatch.setenv("VERCEL", "1")
    with pytest.raises(ValidationError, match="cannot exceed 4"):
        Settings(
            database_url="postgresql://user:pass@example.test/database",
            max_upload_size_mb=5,
            _env_file=None,
        )


def test_vercel_requires_upload_cleanup(monkeypatch):
    monkeypatch.setenv("VERCEL", "1")
    with pytest.raises(ValidationError, match="must be true"):
        Settings(
            database_url="postgresql://user:pass@example.test/database",
            delete_upload_after_processing=False,
            _env_file=None,
        )


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("postgres://user:pass@host/db", "postgresql+psycopg://user:pass@host/db"),
        ("postgresql://user:pass@host/db", "postgresql+psycopg://user:pass@host/db"),
        ("postgresql+psycopg://user:pass@host/db", "postgresql+psycopg://user:pass@host/db"),
        ("sqlite:///data.db", "sqlite:///data.db"),
    ],
)
def test_database_url_normalization(source, expected):
    assert normalize_database_url(source) == expected
