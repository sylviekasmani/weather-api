import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.schemas import WeatherDailyOut, WeatherRecordOut

router = APIRouter(prefix="/weather", tags=["weather"])

# "Point search, many cities" queries below use a LATERAL join so Postgres
# does one index scan per requested city_id against the (city_id, time)
# hypertable index, instead of one big scan across all matching chunks.

_LATEST_SQL = text(
    """
    SELECT w.*
    FROM unnest(CAST(:city_ids AS BIGINT[])) AS c(city_id)
    JOIN LATERAL (
        SELECT *
        FROM weather_records wr
        WHERE wr.city_id = c.city_id
        ORDER BY wr.time DESC
        LIMIT 1
    ) w ON true
    """
)

_AT_SQL = text(
    """
    SELECT w.*
    FROM unnest(CAST(:city_ids AS BIGINT[])) AS c(city_id)
    JOIN LATERAL (
        SELECT *
        FROM weather_records wr
        WHERE wr.city_id = c.city_id AND wr.time <= :at
        ORDER BY wr.time DESC
        LIMIT 1
    ) w ON true
    """
)

_RANGE_SQL = text(
    """
    SELECT *
    FROM weather_records
    WHERE city_id = :city_id AND time >= :start AND time < :end
    ORDER BY time
    """
)

_DAILY_SQL = text(
    """
    SELECT *
    FROM weather_daily
    WHERE city_id = :city_id AND day >= :start AND day < :end
    ORDER BY day
    """
)


@router.get("/latest", response_model=list[WeatherRecordOut])
async def get_latest(
    city_ids: list[int] = Query(...),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    """Point search: most recent reading for each of the given cities."""
    result = await session.execute(_LATEST_SQL, {"city_ids": city_ids})
    return [row._mapping for row in result]


@router.get("/at", response_model=list[WeatherRecordOut])
async def get_at(
    city_ids: list[int] = Query(...),
    at: datetime.datetime = Query(...),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    """Point search: reading at-or-before a given instant, for each city."""
    result = await session.execute(_AT_SQL, {"city_ids": city_ids, "at": at})
    return [row._mapping for row in result]


@router.get("/range", response_model=list[WeatherRecordOut])
async def get_range(
    city_id: int,
    start: datetime.datetime,
    end: datetime.datetime,
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    """Range search: raw readings for one city between start (inclusive) and end (exclusive)."""
    result = await session.execute(_RANGE_SQL, {"city_id": city_id, "start": start, "end": end})
    return [row._mapping for row in result]


@router.get("/daily", response_model=list[WeatherDailyOut])
async def get_daily(
    city_id: int,
    start: datetime.datetime,
    end: datetime.datetime,
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    """Range search: daily rollups for one city, backed by a continuous aggregate."""
    result = await session.execute(_DAILY_SQL, {"city_id": city_id, "start": start, "end": end})
    return [row._mapping for row in result]
