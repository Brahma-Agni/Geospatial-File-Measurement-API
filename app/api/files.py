from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Query, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.database import get_db
from app.exceptions import AppError
from app.models import Feature, MeasurementStatus, UploadedFile
from app.schemas.feature import FeatureListResponse, FeatureResponse
from app.schemas.file import FileResponse
from app.schemas.measurement import (
    FeatureMeasurementResponse,
    MeasurementListResponse,
    MeasurementResponse,
)
from app.services.file_service import FileService

router = APIRouter(prefix="/api/files", tags=["files"])


def _file_or_404(db: Session, file_id: UUID):
    uploaded = db.get(UploadedFile, str(file_id))
    if uploaded is None:
        raise AppError("FILE_NOT_FOUND", "The requested file does not exist.", status_code=404)
    return uploaded


def _page_size(limit: int | None, settings: Settings) -> int:
    return min(limit or settings.default_page_size, settings.max_page_size)


def _features(db: Session, file_id: UUID, offset: int, limit: int) -> list[Feature]:
    statement = (
        select(Feature)
        .where(Feature.uploaded_file_id == str(file_id))
        .order_by(Feature.feature_index)
        .offset(offset)
        .limit(limit)
    )
    return list(db.scalars(statement))


def _feature_count(db: Session, file_id: UUID) -> int:
    return (
        db.scalar(
            select(func.count())
            .select_from(Feature)
            .where(Feature.uploaded_file_id == str(file_id))
        )
        or 0
    )


@router.post("/", response_model=FileResponse, status_code=201, response_model_exclude_none=True)
async def upload_file(
    file: Annotated[UploadFile, File(...)],
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> FileResponse:
    return FileResponse.model_validate(await FileService(db, settings).upload(file))


@router.get("/{file_id}/", response_model=FileResponse, response_model_exclude_none=True)
def get_file(file_id: UUID, db: Annotated[Session, Depends(get_db)]) -> FileResponse:
    return FileResponse.model_validate(_file_or_404(db, file_id))


@router.get("/{file_id}/features/", response_model=FeatureListResponse)
def get_features(
    file_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    limit: Annotated[int | None, Query(ge=1)] = None,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> FeatureListResponse:
    _file_or_404(db, file_id)
    page_size = _page_size(limit, settings)
    features = _features(db, file_id, offset, page_size)
    return FeatureListResponse(
        file_id=str(file_id),
        feature_count=_feature_count(db, file_id),
        limit=page_size,
        offset=offset,
        features=[
            FeatureResponse(
                feature_index=item.feature_index,
                source_feature_id=item.source_feature_id,
                geometry_type=item.geometry_type,
                geometry=item.geometry,
                properties=item.properties,
                source_crs=item.source_crs,
            )
            for item in features
        ],
    )


@router.get("/{file_id}/measurements/", response_model=MeasurementListResponse)
def get_measurements(
    file_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    limit: Annotated[int | None, Query(ge=1)] = None,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> MeasurementListResponse:
    uploaded = _file_or_404(db, file_id)
    if not uploaded.source_crs or not uploaded.measurement_crs:
        raise AppError(
            "PROCESSING_FAILED", "The file has no completed measurements.", status_code=422
        )
    page_size = _page_size(limit, settings)
    results = []
    for item in _features(db, file_id, offset, page_size):
        measurement = None
        if (
            item.measurement_type is not None
            or item.measurement_status != MeasurementStatus.SKIPPED
            or item.measurement_message
        ):
            measurement = MeasurementResponse(
                type=item.measurement_type,
                value=item.measurement_value,
                unit=item.measurement_unit,
                status=item.measurement_status,
                message=item.measurement_message,
            )
        results.append(
            FeatureMeasurementResponse(
                feature_index=item.feature_index,
                geometry_type=item.geometry_type,
                properties=item.properties,
                measurement=measurement,
            )
        )
    return MeasurementListResponse(
        file_id=str(file_id),
        source_crs=uploaded.source_crs,
        measurement_crs=uploaded.measurement_crs,
        feature_count=_feature_count(db, file_id),
        limit=page_size,
        offset=offset,
        features=results,
    )
