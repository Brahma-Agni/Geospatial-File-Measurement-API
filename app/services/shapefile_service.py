from pathlib import Path
from tempfile import TemporaryDirectory

import geopandas as gpd

from app.config import Settings
from app.utils.archive import extract_shapefile


def read_zipped_shapefile(path: Path, settings: Settings) -> gpd.GeoDataFrame:
    with TemporaryDirectory(prefix="geospatial-") as temporary:
        shape = extract_shapefile(
            path, Path(temporary), settings.max_archive_entries, settings.max_extracted_bytes
        )
        return gpd.read_file(shape, engine="pyogrio")
