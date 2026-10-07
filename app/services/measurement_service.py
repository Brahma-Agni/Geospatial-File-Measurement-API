from dataclasses import dataclass

from shapely.geometry.base import BaseGeometry

from app.models import MeasurementStatus, MeasurementType


@dataclass(frozen=True)
class Measurement:
    type: MeasurementType | None
    value: float | None
    unit: str | None
    status: MeasurementStatus
    message: str | None = None


def measure(source: BaseGeometry | None, projected: BaseGeometry | None) -> Measurement:
    if source is None:
        return Measurement(None, None, None, MeasurementStatus.SKIPPED, "Geometry is null.")
    if source.is_empty:
        return Measurement(None, None, None, MeasurementStatus.SKIPPED, "Geometry is empty.")
    if not source.is_valid:
        return Measurement(None, None, None, MeasurementStatus.FAILED, "Geometry is invalid.")
    if projected is None or projected.is_empty:
        return Measurement(None, None, None, MeasurementStatus.FAILED, "Geometry is unmeasurable.")

    kind = source.geom_type
    if kind in {"Polygon", "MultiPolygon"}:
        return Measurement(
            MeasurementType.AREA, float(projected.area), "m2", MeasurementStatus.SUCCESS
        )
    if kind in {"LineString", "MultiLineString"}:
        return Measurement(
            MeasurementType.LENGTH, float(projected.length), "m", MeasurementStatus.SUCCESS
        )
    if kind in {"Point", "MultiPoint"}:
        return Measurement(None, None, None, MeasurementStatus.SKIPPED)
    return Measurement(
        None,
        None,
        None,
        MeasurementStatus.UNSUPPORTED,
        f"Geometry type {kind} is not supported for measurement.",
    )
