import json
import math
from datetime import date, datetime
from typing import Any

from shapely.geometry import mapping
from shapely.geometry.base import BaseGeometry


def geometry_to_geojson(geometry: BaseGeometry | None) -> dict | None:
    if geometry is None or geometry.is_empty:
        return None if geometry is None else mapping(geometry)
    return mapping(geometry)


def json_safe(properties: dict[str, Any]) -> dict[str, Any]:
    def clean(value: Any) -> Any:
        if isinstance(value, dict):
            return {str(key): clean(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [clean(item) for item in value]
        if isinstance(value, float) and not math.isfinite(value):
            return None
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, (date, datetime)):
            return value.isoformat()
        if value.__class__.__name__ == "NAType":
            return None
        if hasattr(value, "item"):
            return clean(value.item())
        return str(value)

    return json.loads(json.dumps(clean(properties), allow_nan=False))
