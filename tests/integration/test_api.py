import zipfile
from uuid import uuid4

import geopandas as gpd

from app.config import Settings, get_settings
from app.main import app
from tests.conftest import upload


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_valid_kml_upload_and_endpoints(client, kml_file):
    response = upload(client, kml_file, "application/vnd.google-earth.kml+xml")
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["filename"] == "survey.kml"
    assert body["status"] == "COMPLETED"
    assert body["feature_count"] == 3
    assert body["source_crs"] == "EPSG:4326"

    file_id = body["id"]
    assert client.get(f"/api/files/{file_id}/").status_code == 200
    features = client.get(f"/api/files/{file_id}/features/?limit=1&offset=1").json()
    assert features["feature_count"] == 3
    assert len(features["features"]) == 1
    assert features["features"][0]["geometry_type"] == "LineString"

    measurements = client.get(f"/api/files/{file_id}/measurements/").json()
    assert measurements["features"][0]["measurement"]["type"] == "AREA"
    assert measurements["features"][1]["measurement"]["type"] == "LENGTH"
    assert measurements["features"][2]["measurement"] is None


def test_valid_shapefile_upload(client, shapefile_zip):
    response = upload(client, shapefile_zip, "application/zip")
    assert response.status_code == 201, response.text
    assert response.json()["file_type"] == "SHAPEFILE"
    assert response.json()["feature_count"] == 1


def test_unsupported_extension(client, tmp_path):
    path = tmp_path / "data.geojson"
    path.write_text("{}")
    response = upload(client, path)
    assert response.status_code == 415
    assert response.json()["error"]["code"] == "UNSUPPORTED_FILE_TYPE"


def test_oversized_upload(client, tmp_path):
    path = tmp_path / "large.kml"
    path.write_bytes(b"x" * (1024 * 1024 + 1))
    app.dependency_overrides[get_settings] = lambda: Settings(max_upload_size_mb=1)
    try:
        response = upload(client, path)
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "FILE_TOO_LARGE"


def test_malformed_zip(client, tmp_path):
    path = tmp_path / "bad.zip"
    path.write_bytes(b"broken")
    response = upload(client, path)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_ARCHIVE"


def test_missing_crs(client, tmp_path):
    shape_dir = tmp_path / "no-crs"
    shape_dir.mkdir()
    gpd.GeoDataFrame({"name": ["x"]}, geometry=gpd.points_from_xy([1], [2])).to_file(
        shape_dir / "no-crs.shp", engine="pyogrio"
    )
    archive = tmp_path / "no-crs.zip"
    with zipfile.ZipFile(archive, "w") as output:
        for path in shape_dir.iterdir():
            output.write(path, path.name)
    response = upload(client, archive)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "MISSING_CRS"


def test_empty_dataset(client, tmp_path):
    shape_dir = tmp_path / "empty"
    shape_dir.mkdir()
    gpd.GeoDataFrame({"name": []}, geometry=[], crs="EPSG:4326").to_file(
        shape_dir / "empty.shp", engine="pyogrio"
    )
    archive = tmp_path / "empty.zip"
    with zipfile.ZipFile(archive, "w") as output:
        for path in shape_dir.iterdir():
            output.write(path, path.name)
    response = upload(client, archive)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "EMPTY_DATASET"


def test_unknown_file(client):
    file_id = uuid4()
    response = client.get(f"/api/files/{file_id}/")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "FILE_NOT_FOUND"
    assert client.get(f"/api/files/{file_id}/features/").status_code == 404
    assert client.get(f"/api/files/{file_id}/measurements/").status_code == 404


def test_invalid_identifier_has_structured_error(client):
    response = client.get("/api/files/not-a-uuid/")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_pagination_limit_is_capped(client, kml_file, monkeypatch):
    response = upload(client, kml_file)
    file_id = response.json()["id"]
    page = client.get(f"/api/files/{file_id}/features/?limit=999999").json()
    assert page["limit"] == 500
