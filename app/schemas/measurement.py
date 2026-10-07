from pydantic import BaseModel

from app.models import MeasurementStatus, MeasurementType


class MeasurementResponse(BaseModel):
    type: MeasurementType | None
    value: float | None
    unit: str | None
    status: MeasurementStatus
    message: str | None = None


class FeatureMeasurementResponse(BaseModel):
    feature_index: int
    geometry_type: str | None
    properties: dict
    measurement: MeasurementResponse | None


class MeasurementListResponse(BaseModel):
    file_id: str
    source_crs: str
    measurement_crs: str
    feature_count: int
    limit: int
    offset: int
    features: list[FeatureMeasurementResponse]
