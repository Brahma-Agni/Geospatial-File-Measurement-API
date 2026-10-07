from datetime import UTC, datetime

import numpy as np
from shapely.geometry import Point, Polygon

from app.utils.geometry import geometry_to_geojson, json_safe


def test_geometry_serialization_preserves_source_coordinates():
    result = geometry_to_geojson(Point(77.1, 12.2))
    assert result == {"type": "Point", "coordinates": (77.1, 12.2)}


def test_null_and_empty_geometry_serialization():
    assert geometry_to_geojson(None) is None
    assert geometry_to_geojson(Polygon())["type"] == "Polygon"


def test_property_serialization_normalizes_external_scalar_types():
    result = json_safe(
        {
            "nan": float("nan"),
            "infinity": float("inf"),
            "integer": np.int64(7),
            "when": datetime(2026, 1, 2, 3, 4, tzinfo=UTC),
            "nested": [np.float64(2.5), np.nan],
        }
    )
    assert result == {
        "nan": None,
        "infinity": None,
        "integer": 7,
        "when": "2026-01-02T03:04:00+00:00",
        "nested": [2.5, None],
    }
