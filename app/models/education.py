from sqlalchemy import CheckConstraint, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class Governorate(Base):
    __tablename__ = "education_governorates"
    id: Mapped[str] = mapped_column(String(20), primary_key=True)
    name_ar: Mapped[str] = mapped_column(String(200))
    name_en: Mapped[str] = mapped_column(String(200))
    search_text: Mapped[str] = mapped_column(Text)
    region: Mapped[str] = mapped_column(String(20), index=True)
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    geometry: Mapped[dict] = mapped_column(JSON)
    boundary_date: Mapped[str] = mapped_column(String(20))
    source: Mapped[str] = mapped_column(String(200))


class Directorate(Base):
    __tablename__ = "education_directorates"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    name_ar: Mapped[str] = mapped_column(String(200))
    name_en: Mapped[str] = mapped_column(String(200))
    search_text: Mapped[str] = mapped_column(Text)
    governorate_id: Mapped[str | None] = mapped_column(ForeignKey("education_governorates.id"), index=True)
    region: Mapped[str | None] = mapped_column(String(20), index=True)
    category: Mapped[str] = mapped_column(String(30))
    source_url: Mapped[str] = mapped_column(String(500))
    source_date: Mapped[str] = mapped_column(String(20))
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    geometry: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class School(Base):
    __tablename__ = "education_schools"
    __table_args__ = (
        CheckConstraint("(latitude IS NULL AND longitude IS NULL) OR (latitude IS NOT NULL AND longitude IS NOT NULL)", name="school_coordinate_pair"),
        CheckConstraint("latitude IS NULL OR (latitude >= -90 AND latitude <= 90)", name="school_latitude"),
        CheckConstraint("longitude IS NULL OR (longitude >= -180 AND longitude <= 180)", name="school_longitude"),
        CheckConstraint("latitude IS NULL OR coordinate_source IS NOT NULL", name="school_coordinate_source"),
    )
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    # National codes in the source are not unique; never use this column as a PK.
    national_code: Mapped[str] = mapped_column(String(60), index=True)
    name_ar: Mapped[str] = mapped_column(String(500))
    name_en: Mapped[str] = mapped_column(String(500))
    search_text: Mapped[str] = mapped_column(Text)
    school_type: Mapped[str] = mapped_column(String(60), index=True)
    governorate_id: Mapped[str | None] = mapped_column(ForeignKey("education_governorates.id"), index=True)
    directorate_id: Mapped[str | None] = mapped_column(ForeignKey("education_directorates.id"), index=True)
    region: Mapped[str] = mapped_column(String(20), index=True)
    latitude: Mapped[float | None] = mapped_column(Float, index=True)
    longitude: Mapped[float | None] = mapped_column(Float, index=True)
    coordinate_source: Mapped[str | None] = mapped_column(String(500))
    source_row: Mapped[int] = mapped_column(Integer)
    source_values: Mapped[dict] = mapped_column(JSON)


class EducationSource(Base):
    __tablename__ = "education_sources"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    report: Mapped[dict] = mapped_column(JSON)
