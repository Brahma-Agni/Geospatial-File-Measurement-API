import geopandas as gpd
from shapely.geometry import Point

from app.models import MeasurementStatus
from app.services.feature_service import normalize_features


def test_normalization_preserves_source_and_uses_projected_measurement_copy():
    source = gpd.GeoDataFrame(
        {"nullable": [float("nan")], "count": [3]}, geometry=[Point(77, 12)], crs="EPSG:4326"
    )
    projected = source.to_crs("EPSG:32643")
    result = normalize_features("file-id", source, projected, "EPSG:4326")[0]
    assert result.geometry == {"type": "Point", "coordinates": (77.0, 12.0)}
    assert result.properties == {"nullable": None, "count": 3}
    assert result.measurement_status == MeasurementStatus.SKIPPED
    assert result.source_feature_id == "0"


def test_null_geometry_does_not_abort_dataset():
    source = gpd.GeoDataFrame({"name": ["missing"]}, geometry=[None], crs="EPSG:4326")
    projected = source.to_crs("EPSG:32643")
    result = normalize_features("file-id", source, projected, "EPSG:4326")[0]
    assert result.geometry is None
    assert result.geometry_type is None
    assert result.measurement_status == MeasurementStatus.SKIPPED
