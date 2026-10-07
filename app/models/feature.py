from enum import StrEnum

from sqlalchemy import JSON, Enum, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class MeasurementType(StrEnum):
    AREA = "AREA"
    LENGTH = "LENGTH"


class MeasurementStatus(StrEnum):
    SUCCESS = "SUCCESS"
    SKIPPED = "SKIPPED"
    UNSUPPORTED = "UNSUPPORTED"
    FAILED = "FAILED"


class Feature(Base):
    __tablename__ = "features"
    __table_args__ = (UniqueConstraint("uploaded_file_id", "feature_index"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    uploaded_file_id: Mapped[str] = mapped_column(
        ForeignKey("uploaded_files.id", ondelete="CASCADE"), index=True
    )
    feature_index: Mapped[int] = mapped_column(Integer)
    source_feature_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    geometry_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    geometry: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    properties: Mapped[dict] = mapped_column(JSON, default=dict)
    source_crs: Mapped[str] = mapped_column(String(255))
    measurement_type: Mapped[MeasurementType | None] = mapped_column(
        Enum(MeasurementType), nullable=True
    )
    measurement_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    measurement_unit: Mapped[str | None] = mapped_column(String(16), nullable=True)
    measurement_status: Mapped[MeasurementStatus] = mapped_column(Enum(MeasurementStatus))
    measurement_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    uploaded_file = relationship("UploadedFile", back_populates="features")
