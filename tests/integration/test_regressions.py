import io
import zipfile
from pathlib import Path

from sqlalchemy import select

from app.config import Settings, get_settings
from app.database import SessionLocal
from app.main import app
from app.models import FileStatus, UploadedFile
from tests.conftest import upload


def test_invalid_kml_returns_safe_error_and_persists_failed_state(client, tmp_path):
    path = tmp_path / "broken.kml"
    path.write_text("<kml><not-closed>", encoding="utf-8")
    response = upload(client, path)
    assert response.status_code == 422
    assert response.json() == {
        "error": {"code": "INVALID_KML", "message": "The uploaded KML could not be read."}
    }
    assert str(tmp_path) not in response.text

    with SessionLocal() as db:
        record = db.scalar(select(UploadedFile))
        assert record.status == FileStatus.FAILED
        assert record.processing_error == "The uploaded KML could not be read."


def test_client_filename_cannot_control_storage_path(client, kml_file):
    payload = kml_file.read_bytes()
    response = client.post(
        "/api/files/",
        files={"file": ("../../outside.KML", io.BytesIO(payload), "application/xml")},
    )
    assert response.status_code == 201, response.text
    assert response.json()["filename"] == "outside.KML"

    with SessionLocal() as db:
        record = db.get(UploadedFile, response.json()["id"])
        assert record.filename == f"{record.id}.kml"
        assert ".." not in record.filename


def test_zip_slip_error_does_not_create_external_file(client, tmp_path):
    archive = tmp_path / "traversal.zip"
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr("../../escaped.shp", b"x")
    response = upload(client, archive)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_ARCHIVE"
    assert not (tmp_path / "escaped.shp").exists()


def test_corrupt_shapefile_returns_structured_error(client, tmp_path):
    archive = tmp_path / "corrupt.zip"
    with zipfile.ZipFile(archive, "w") as output:
        for suffix in ("shp", "shx", "dbf"):
            output.writestr(f"survey.{suffix}", b"not-a-shapefile")
    response = upload(client, archive)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_SHAPEFILE"
    assert "Traceback" not in response.text


def test_original_geojson_is_not_projected(client, kml_file):
    uploaded = upload(client, kml_file).json()
    feature = client.get(f"/api/files/{uploaded['id']}/features/?limit=1").json()["features"][0]
    first_coordinate = feature["geometry"]["coordinates"][0][0]
    assert first_coordinate[:2] == [77.0, 12.0]
    assert feature["source_crs"] == "EPSG:4326"


def test_pagination_boundaries_and_validation(client, kml_file):
    file_id = upload(client, kml_file).json()["id"]
    empty_page = client.get(f"/api/files/{file_id}/features/?offset=999").json()
    assert empty_page["features"] == []
    assert client.get(f"/api/files/{file_id}/features/?limit=0").status_code == 422
    assert client.get(f"/api/files/{file_id}/features/?offset=-1").status_code == 422


def test_metadata_timestamps_are_utc_and_internal_name_is_not_exposed(client, kml_file):
    body = upload(client, kml_file).json()
    assert body["created_at"].endswith("Z")
    assert body["updated_at"].endswith("Z")
    assert body["filename"] == "survey.kml"
    assert f"{body['id']}.kml" not in body.values()
    assert "processing_error" not in body


def test_upload_requires_multipart_file_field(client):
    response = client.post("/api/files/", data={"file": "not a file"})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_ephemeral_upload_is_deleted_after_processing(client, kml_file, tmp_path):
    upload_dir = tmp_path / "ephemeral"
    app.dependency_overrides[get_settings] = lambda: Settings(
        upload_dir=upload_dir, delete_upload_after_processing=True
    )
    try:
        response = upload(client, kml_file)
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 201, response.text
    assert not (upload_dir / f"{response.json()['id']}.kml").exists()
    assert list(Path(upload_dir).iterdir()) == []
