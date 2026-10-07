import geopandas as gpd
from pyproj import CRS

from app.exceptions import AppError


def crs_name(crs: CRS) -> str:
    return crs.to_string()


def _is_metric(crs: CRS) -> bool:
    return bool(crs.axis_info) and all(
        (axis.unit_name or "").lower() in {"metre", "meter"}
        and axis.unit_conversion_factor is not None
        and abs(axis.unit_conversion_factor - 1) < 1e-12
        for axis in crs.axis_info[:2]
    )


def measurement_frame(source: gpd.GeoDataFrame) -> tuple[gpd.GeoDataFrame, str, str]:
    source_crs = CRS.from_user_input(source.crs)
    try:
        target = (
            source_crs
            if source_crs.is_projected and _is_metric(source_crs)
            else source.estimate_utm_crs()
        )
    except Exception as exc:
        raise AppError(
            "MISSING_CRS", "A suitable metric measurement CRS could not be determined."
        ) from exc
    if target is None:
        raise AppError("MISSING_CRS", "A suitable metric measurement CRS could not be determined.")
    target = CRS.from_user_input(target)
    if not target.is_projected or not _is_metric(target):
        raise AppError("MISSING_CRS", "A suitable metric measurement CRS could not be determined.")
    try:
        measured = source.copy() if target == source_crs else source.to_crs(target)
    except Exception as exc:
        raise AppError("CORRUPT_FILE", "Feature coordinates could not be transformed.") from exc
    return measured, crs_name(source_crs), crs_name(target)
