import datetime

from pydantic import BaseModel, ConfigDict


class CityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    country_code: str
    admin_region: str | None
    latitude: float
    longitude: float
    elevation_m: float | None
    timezone: str


class CityCreate(BaseModel):
    name: str
    country_code: str
    admin_region: str | None = None
    latitude: float
    longitude: float
    elevation_m: float | None = None
    timezone: str


class WeatherRecordOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    city_id: int
    time: datetime.datetime
    temperature_c: float | None
    feels_like_c: float | None
    humidity_pct: float | None
    pressure_hpa: float | None
    wind_speed_ms: float | None
    wind_direction_deg: float | None
    precipitation_mm: float | None
    cloud_cover_pct: float | None
    condition_code: int | None


class WeatherDailyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    city_id: int
    day: datetime.datetime
    avg_temp_c: float | None
    min_temp_c: float | None
    max_temp_c: float | None
    avg_humidity_pct: float | None
    total_precipitation_mm: float | None
    avg_wind_speed_ms: float | None
