"""Bulk-load historical weather records for one city from a CSV file.

Usage:
    .venv/bin/python scripts/load_city_weather_from_csv.py \
        --city "London" --country GB \
        --csv path/to/london_history.csv

If the city doesn't already exist in `cities`, also pass --latitude,
--longitude and --timezone (and optionally --admin-region/--elevation-m)
and it will be created automatically.

Expected CSV columns (header row required, extra columns are ignored):
    time, temperature_c, feels_like_c, humidity_pct, pressure_hpa,
    wind_speed_ms, wind_direction_deg, precipitation_mm, cloud_cover_pct,
    condition_code

`time` must be ISO 8601 (e.g. 2024-01-01T00:00:00Z). Any other numeric
column left blank is loaded as NULL.

Loads via COPY into an UNLOGGED staging table, then
INSERT ... ON CONFLICT DO NOTHING into weather_records, so the script is
safe to re-run over the same file (e.g. after a partial failure) without
producing duplicates.
"""

import argparse
import asyncio
import csv
import datetime
import sys
from pathlib import Path
from typing import Iterator

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncpg

from app.config import settings

COLUMNS = [
    "time",
    "temperature_c",
    "feels_like_c",
    "humidity_pct",
    "pressure_hpa",
    "wind_speed_ms",
    "wind_direction_deg",
    "precipitation_mm",
    "cloud_cover_pct",
    "condition_code",
]

FLOAT_COLUMNS = {
    "temperature_c",
    "feels_like_c",
    "humidity_pct",
    "pressure_hpa",
    "wind_speed_ms",
    "wind_direction_deg",
    "precipitation_mm",
    "cloud_cover_pct",
}


def parse_row(row: dict, city_id: int) -> tuple:
    time = datetime.datetime.fromisoformat(row["time"])
    values = [city_id, time]
    for col in COLUMNS[1:]:
        raw = (row.get(col) or "").strip()
        if not raw:
            values.append(None)
        elif col == "condition_code":
            values.append(int(raw))
        else:
            values.append(float(raw))
    return tuple(values)


def iter_records(csv_path: Path, city_id: int) -> Iterator[tuple]:
    with csv_path.open(newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            yield parse_row(row, city_id)


async def get_or_create_city(conn: asyncpg.Connection, args: argparse.Namespace) -> int:
    country_code = args.country.upper()
    city_id = await conn.fetchval(
        "SELECT id FROM cities WHERE name = $1 AND country_code = $2",
        args.city,
        country_code,
    )
    if city_id is not None:
        return city_id

    missing = [
        name
        for name, value in [("--latitude", args.latitude), ("--longitude", args.longitude), ("--timezone", args.timezone)]
        if value is None
    ]
    if missing:
        print(
            f"City name={args.city!r} country_code={country_code!r} doesn't exist yet; "
            f"pass {', '.join(missing)} to create it",
            file=sys.stderr,
        )
        sys.exit(1)

    city_id = await conn.fetchval(
        """
        INSERT INTO cities (name, country_code, admin_region, latitude, longitude, elevation_m, timezone, created_at)
        VALUES ($1, $2, $3, $4, $5, $6, $7, now())
        RETURNING id
        """,
        args.city,
        country_code,
        args.admin_region,
        args.latitude,
        args.longitude,
        args.elevation_m,
        args.timezone,
    )
    print(f"Created city {args.city!r} ({country_code}) as id={city_id}")
    return city_id


async def load(args: argparse.Namespace) -> None:
    dsn = settings.database_url.replace("postgresql+asyncpg://", "postgresql://")
    conn = await asyncpg.connect(dsn)
    try:
        city_id = await get_or_create_city(conn, args)
        csv_path = args.csv

        async with conn.transaction():
            await conn.execute(
                """
                CREATE TEMP TABLE weather_staging (
                    city_id BIGINT,
                    time TIMESTAMPTZ,
                    temperature_c REAL,
                    feels_like_c REAL,
                    humidity_pct REAL,
                    pressure_hpa REAL,
                    wind_speed_ms REAL,
                    wind_direction_deg REAL,
                    precipitation_mm REAL,
                    cloud_cover_pct REAL,
                    condition_code SMALLINT
                ) ON COMMIT DROP
                """
            )

            result = await conn.copy_records_to_table(
                "weather_staging",
                records=iter_records(csv_path, city_id),
                columns=["city_id", *COLUMNS],
            )
            print(f"Copied into staging: {result}")

            inserted = await conn.execute(
                """
                INSERT INTO weather_records
                SELECT * FROM weather_staging
                ON CONFLICT (city_id, time) DO NOTHING
                """
            )
            print(f"Inserted into weather_records: {inserted}")
    finally:
        await conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--city", required=True, help="City name, must match cities.name exactly")
    parser.add_argument("--country", required=True, help="ISO country code, e.g. GB")
    parser.add_argument("--csv", required=True, type=Path, help="Path to the CSV file to load")
    parser.add_argument("--latitude", type=float, help="Required only if the city doesn't exist yet")
    parser.add_argument("--longitude", type=float, help="Required only if the city doesn't exist yet")
    parser.add_argument("--timezone", help="Required only if the city doesn't exist yet, e.g. Europe/London")
    parser.add_argument("--admin-region", dest="admin_region", help="Optional state/region, used only when creating the city")
    parser.add_argument("--elevation-m", dest="elevation_m", type=float, help="Optional elevation in meters, used only when creating the city")
    args = parser.parse_args()

    asyncio.run(load(args))


if __name__ == "__main__":
    main()
