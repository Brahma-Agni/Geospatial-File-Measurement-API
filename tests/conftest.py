import os
import zipfile
from pathlib import Path

test_root = Path("/tmp/geospatial-api-tests")
test_root.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("DATABASE_URL", f"sqlite:///{test_root / 'test.db'}")
os.environ.setdefault("UPLOAD_DIR", str(test_root / "uploads"))

import geopandas as gpd  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from shapely.geometry import LineString, Point, Polygon  # noqa: E402

from app.database import Base, engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(autouse=True)
def clean_database():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


@pytest.fixture
def client():
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


@pytest.fixture
def source_frame() -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(
        {"name": ["Plot", "Road", "Marker"]},
        geometry=[
            Polygon([(77.0, 12.0), (77.001, 12.0), (77.001, 12.001), (77.0, 12.001)]),
            LineString([(77.0, 12.0), (77.001, 12.0)]),
            Point(77.0, 12.0),
        ],
        crs="EPSG:4326",
    )


@pytest.fixture
def shapefile_zip(tmp_path: Path, source_frame: gpd.GeoDataFrame) -> Path:
    directory = tmp_path / "shape"
    directory.mkdir()
    source_frame.iloc[[0]].to_file(directory / "survey.shp", engine="pyogrio")
    archive = tmp_path / "survey.zip"
    with zipfile.ZipFile(archive, "w") as output:
        for path in directory.iterdir():
            output.write(path, path.name)
    return archive


@pytest.fixture
def kml_file(tmp_path: Path) -> Path:
    path = tmp_path / "survey.kml"
    path.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2"><Document>
<Placemark><name>Plot A</name><Polygon><outerBoundaryIs><LinearRing><coordinates>
77,12,0 77.001,12,0 77.001,12.001,0 77,12.001,0 77,12,0
</coordinates></LinearRing></outerBoundaryIs></Polygon></Placemark>
<Placemark><name>Road</name><LineString><coordinates>
77,12,0 77.001,12,0
</coordinates></LineString></Placemark>
<Placemark><name>Marker</name><Point><coordinates>77,12,0</coordinates></Point></Placemark>
</Document></kml>""",
        encoding="utf-8",
    )
    return path


def upload(client: TestClient, path: Path, content_type: str = "application/octet-stream"):
    with path.open("rb") as stream:
        return client.post("/api/files/", files={"file": (path.name, stream, content_type)})
