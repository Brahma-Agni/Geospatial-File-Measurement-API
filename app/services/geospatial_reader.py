from pathlib import Path

import geopandas as gpd

from app.config import Settings
from app.exceptions import AppError
from app.models import FileType
from app.services.shapefile_service import read_zipped_shapefile


def read_geospatial(path: Path, file_type: FileType, settings: Settings) -> gpd.GeoDataFrame:
    try:
        if file_type == FileType.SHAPEFILE:
            frame = read_zipped_shapefile(path, settings)
        else:
            frame = gpd.read_file(path, driver="KML", engine="pyogrio")
    except AppError:
        raise
    except Exception as exc:
        code = "INVALID_SHAPEFILE" if file_type == FileType.SHAPEFILE else "INVALID_KML"
        raise AppError(code, f"The uploaded {file_type.value} could not be read.") from exc

    if frame.empty:
        raise AppError("EMPTY_DATASET", "The uploaded dataset contains no features.")
    if frame.crs is None:
        raise AppError("MISSING_CRS", "The uploaded dataset has no coordinate reference system.")
    return frame
