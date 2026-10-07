import logging
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.config import Settings
from app.exceptions import AppError
from app.models import FileStatus, FileType, UploadedFile
from app.services.crs_service import measurement_frame
from app.services.feature_service import normalize_features
from app.services.geospatial_reader import read_geospatial

logger = logging.getLogger(__name__)


class FileService:
    def __init__(self, db: Session, settings: Settings) -> None:
        self.db = db
        self.settings = settings

    async def upload(self, upload: UploadFile) -> UploadedFile:
        original_name = Path(upload.filename or "").name
        extension = Path(original_name).suffix.lower()
        if extension not in {".kml", ".zip"}:
            raise AppError(
                "UNSUPPORTED_FILE_TYPE",
                "Only .kml and .zip files are supported.",
                status_code=415,
            )

        file_type = FileType.KML if extension == ".kml" else FileType.SHAPEFILE
        record = UploadedFile(
            filename="pending",
            original_filename=original_name,
            file_type=file_type,
            upload_size=0,
            status=FileStatus.UPLOADED,
        )
        self.settings.upload_dir.mkdir(parents=True, exist_ok=True)
        self.db.add(record)
        self.db.flush()
        stored_name = f"{record.id}{extension}"
        destination = self.settings.upload_dir / stored_name

        size = 0
        try:
            with destination.open("wb") as output:
                while chunk := await upload.read(1024 * 1024):
                    size += len(chunk)
                    if size > self.settings.max_upload_bytes:
                        raise AppError(
                            "FILE_TOO_LARGE",
                            "The uploaded file exceeds the configured size limit.",
                            status_code=413,
                            details={"maximum_bytes": self.settings.max_upload_bytes},
                        )
                    output.write(chunk)
        except Exception:
            destination.unlink(missing_ok=True)
            self.db.rollback()
            raise
        finally:
            await upload.close()

        record.filename = stored_name
        record.upload_size = size
        self.db.commit()
        self.db.refresh(record)
        logger.info("file_uploaded file_id=%s size=%d type=%s", record.id, size, file_type.value)
        try:
            return self.process(record, destination)
        finally:
            if self.settings.delete_upload_after_processing:
                destination.unlink(missing_ok=True)

    def process(self, record: UploadedFile, path: Path) -> UploadedFile:
        record.status = FileStatus.PROCESSING
        record.processing_error = None
        self.db.commit()
        logger.info("processing_started file_id=%s", record.id)
        try:
            source = read_geospatial(path, record.file_type, self.settings)
            measured, source_crs, measurement_crs = measurement_frame(source)
            features = normalize_features(record.id, source, measured, source_crs)
            self.db.add_all(features)
            self.db.flush()
            record.source_crs = source_crs
            record.measurement_crs = measurement_crs
            record.feature_count = len(features)
            record.status = FileStatus.COMPLETED
            record.processing_error = None
            self.db.commit()
            self.db.refresh(record)
            logger.info("processing_completed file_id=%s features=%d", record.id, len(features))
            return record
        except AppError as exc:
            self.db.rollback()
            current = self.db.get(UploadedFile, record.id)
            if current is not None:
                current.status = FileStatus.FAILED
                current.processing_error = exc.message
                self.db.commit()
            logger.warning("processing_failed file_id=%s code=%s", record.id, exc.code)
            raise
        except Exception as exc:
            self.db.rollback()
            current = self.db.get(UploadedFile, record.id)
            if current is not None:
                current.status = FileStatus.FAILED
                current.processing_error = "Unexpected processing failure."
                self.db.commit()
            logger.exception("processing_failed file_id=%s", record.id, exc_info=exc)
            raise AppError(
                "PROCESSING_FAILED", "The uploaded file could not be processed.", status_code=500
            ) from exc
