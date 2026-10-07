import geopandas as gpd
import pytest
from shapely.geometry import (
    GeometryCollection,
    LineString,
    MultiLineString,
    MultiPoint,
    MultiPolygon,
    Point,
    Polygon,
)

from app.exceptions import AppError
from app.models import MeasurementStatus, MeasurementType
from app.services.crs_service import measurement_frame
from app.services.measurement_service import measure


@pytest.mark.parametrize(
    ("geometry", "kind", "value", "unit"),
    [
        (Polygon([(0, 0), (10, 0), (10, 10), (0, 10)]), MeasurementType.AREA, 100, "m2"),
        (
            MultiPolygon(
                [
                    Polygon([(0, 0), (10, 0), (10, 10), (0, 10)]),
                    Polygon([(20, 0), (25, 0), (25, 10), (20, 10)]),
                ]
            ),
            MeasurementType.AREA,
            150,
            "m2",
        ),
        (LineString([(0, 0), (3, 4)]), MeasurementType.LENGTH, 5, "m"),
        (
            MultiLineString([[(0, 0), (3, 4)], [(0, 0), (0, 2)]]),
            MeasurementType.LENGTH,
            7,
            "m",
        ),
    ],
)
def test_measured_geometry(geometry, kind, value, unit):
    result = measure(geometry, geometry)
    assert result.type == kind
    assert result.value == pytest.approx(value)
    assert result.unit == unit
    assert result.status == MeasurementStatus.SUCCESS


@pytest.mark.parametrize("geometry", [Point(1, 2), MultiPoint([(1, 2), (3, 4)])])
def test_point_has_no_measurement(geometry):
    result = measure(geometry, geometry)
    assert result.value is None
    assert result.status == MeasurementStatus.SKIPPED


def test_geometry_collection_is_unsupported():
    result = measure(GeometryCollection([Point(0, 0)]), GeometryCollection([Point(0, 0)]))
    assert result.status == MeasurementStatus.UNSUPPORTED
    assert "GeometryCollection" in result.message


def test_null_and_empty_geometry_are_skipped():
    assert measure(None, None).status == MeasurementStatus.SKIPPED
    assert measure(Polygon(), Polygon()).status == MeasurementStatus.SKIPPED


def test_invalid_polygon_fails_without_repair():
    bowtie = Polygon([(0, 0), (1, 1), (1, 0), (0, 1), (0, 0)])
    assert measure(bowtie, bowtie).status == MeasurementStatus.FAILED


def test_geographic_polygon_and_line_are_projected():
    frame = gpd.GeoDataFrame(
        geometry=[
            Polygon([(77, 12), (77.001, 12), (77.001, 12.001), (77, 12.001)]),
            LineString([(77, 12), (77.001, 12)]),
        ],
        crs="EPSG:4326",
    )
    projected, source, target = measurement_frame(frame)
    assert source == "EPSG:4326"
    assert target != source
    assert projected.geometry.iloc[0].area == pytest.approx(12000, rel=0.1)
    assert projected.geometry.iloc[1].length == pytest.approx(109, rel=0.1)


def test_metric_projected_crs_is_preserved():
    frame = gpd.GeoDataFrame(
        geometry=[Polygon([(0, 0), (10, 0), (10, 10), (0, 10)])], crs="EPSG:32643"
    )
    projected, source, target = measurement_frame(frame)
    assert source == target == "EPSG:32643"
    assert projected.geometry.iloc[0].area == pytest.approx(100)


def test_projected_feet_are_transformed_to_metric_crs():
    frame = gpd.GeoDataFrame(geometry=[Point(987000, 190000)], crs="EPSG:2263")
    projected, source, target = measurement_frame(frame)
    assert source == "EPSG:2263"
    assert target != source
    assert projected.crs.axis_info[0].unit_name.lower() in {"metre", "meter"}


def test_unprojectable_extent_has_domain_error():
    frame = gpd.GeoDataFrame(geometry=[Point(float("nan"), float("nan"))], crs="EPSG:4326")
    with pytest.raises(AppError) as error:
        measurement_frame(frame)
    assert error.value.code == "MISSING_CRS"
