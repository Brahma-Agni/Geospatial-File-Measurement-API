from typing import Any

import geopandas as gpd

from app.models import Feature
from app.services.measurement_service import measure
from app.utils.geometry import geometry_to_geojson, json_safe


def normalize_features(
    file_id: str,
    source: gpd.GeoDataFrame,
    measured: gpd.GeoDataFrame,
    source_crs: str,
) -> list[Feature]:
    features: list[Feature] = []
    geometry_column = source.geometry.name
    for position, ((index, row), (_, _measured_row)) in enumerate(
        zip(source.iterrows(), measured.iterrows(), strict=True)
    ):
        geometry = source.geometry.iloc[position]
        projected_geometry = measured.geometry.iloc[position]
        measurement = measure(geometry, projected_geometry)
        properties: dict[str, Any] = {
            str(key): value for key, value in row.items() if key != geometry_column
        }
        features.append(
            Feature(
                uploaded_file_id=file_id,
                feature_index=position,
                source_feature_id=str(index) if index is not None else None,
                geometry_type=geometry.geom_type if geometry is not None else None,
                geometry=geometry_to_geojson(geometry),
                properties=json_safe(properties),
                source_crs=source_crs,
                measurement_type=measurement.type,
                measurement_value=measurement.value,
                measurement_unit=measurement.unit,
                measurement_status=measurement.status,
                measurement_message=measurement.message,
            )
        )
    return features
