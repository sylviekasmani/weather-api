import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    type_annotation_map = {datetime.datetime: DateTime(timezone=True)}


class City(Base):
    __tablename__ = "cities"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str]
    country_code: Mapped[str]
    admin_region: Mapped[str | None]
    latitude: Mapped[float]
    longitude: Mapped[float]
    elevation_m: Mapped[float | None]
    timezone: Mapped[str]
    created_at: Mapped[datetime.datetime]

    __table_args__ = (
        UniqueConstraint("name", "country_code", "admin_region", name="uq_cities_name_country_admin"),
        Index("ix_cities_country_code", "country_code"),
    )


class WeatherRecord(Base):
    """Hypertable. Table structure (partitioning, compression, PK) is managed
    entirely by the Alembic migration's raw SQL — this mapping is for querying
    only, not for `Base.metadata.create_all`.
    """

    __tablename__ = "weather_records"

    city_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("cities.id"), primary_key=True)
    time: Mapped[datetime.datetime] = mapped_column(primary_key=True)
    temperature_c: Mapped[float | None]
    feels_like_c: Mapped[float | None]
    humidity_pct: Mapped[float | None]
    pressure_hpa: Mapped[float | None]
    wind_speed_ms: Mapped[float | None]
    wind_direction_deg: Mapped[float | None]
    precipitation_mm: Mapped[float | None]
    cloud_cover_pct: Mapped[float | None]
    condition_code: Mapped[int | None]


class WeatherDaily(Base):
    """Read-only mapping onto the `weather_daily` continuous aggregate."""

    __tablename__ = "weather_daily"

    city_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    day: Mapped[datetime.datetime] = mapped_column(primary_key=True)
    avg_temp_c: Mapped[float | None]
    min_temp_c: Mapped[float | None]
    max_temp_c: Mapped[float | None]
    avg_humidity_pct: Mapped[float | None]
    total_precipitation_mm: Mapped[float | None]
    avg_wind_speed_ms: Mapped[float | None]

    __mapper_args__ = {"eager_defaults": True}
