from pydantic import BaseModel


class FeatureResponse(BaseModel):
    feature_index: int
    source_feature_id: str | None
    geometry_type: str | None
    geometry: dict | None
    properties: dict
    source_crs: str


class FeatureListResponse(BaseModel):
    file_id: str
    feature_count: int
    limit: int
    offset: int
    features: list[FeatureResponse]
