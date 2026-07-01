"""initial schema: cities, weather hypertable, compression, continuous aggregate

Revision ID: 45cad369f4e1
Revises:
Create Date: 2026-07-01 15:58:40.598379

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '45cad369f4e1'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS timescaledb")

    op.create_table(
        "cities",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("country_code", sa.Text(), nullable=False),
        sa.Column("admin_region", sa.Text(), nullable=True),
        sa.Column("latitude", sa.Double(), nullable=False),
        sa.Column("longitude", sa.Double(), nullable=False),
        sa.Column("elevation_m", sa.REAL(), nullable=True),
        sa.Column("timezone", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("name", "country_code", "admin_region", name="uq_cities_name_country_admin"),
    )
    op.create_index("ix_cities_country_code", "cities", ["country_code"])

    # weather_records is a hypertable, so it's created with raw SQL rather than
    # op.create_table: the partitioning column must be part of the primary key,
    # and hypertable creation/compression/continuous aggregates are TimescaleDB
    # DDL that SQLAlchemy's table constructs don't model.
    op.execute(
        """
        CREATE TABLE weather_records (
            city_id BIGINT NOT NULL REFERENCES cities (id),
            time TIMESTAMPTZ NOT NULL,
            temperature_c REAL,
            feels_like_c REAL,
            humidity_pct REAL,
            pressure_hpa REAL,
            wind_speed_ms REAL,
            wind_direction_deg REAL,
            precipitation_mm REAL,
            cloud_cover_pct REAL,
            condition_code SMALLINT,
            PRIMARY KEY (city_id, time)
        )
        """
    )

    # Monthly chunks: at ~3000 cities x hourly readings that's ~2M rows/chunk,
    # well under the ~25%-of-RAM-per-chunk guidance on this box, while keeping
    # total chunk count low (~100 for a 200M-row / ~8yr corpus) so planning
    # and chunk-exclusion overhead stays cheap. Adjust with
    # set_chunk_time_interval() if actual ingestion cadence differs.
    # create_default_indexes=false: the default time-only index isn't useful
    # here since every query filters by city_id first (point lookups across
    # cities, or a range for one city) — the (city_id, time) primary key
    # already covers both, and skipping the extra index halves per-row write
    # amplification at 200M-row scale.
    op.execute(
        """
        SELECT create_hypertable(
            'weather_records', by_range('time', INTERVAL '1 month'),
            create_default_indexes => false
        )
        """
    )

    # Native compression: cities remain rows within a chunk (segmentby) so a
    # single-city range scan over compressed data still only decompresses
    # that city's rows, and rows within a segment are stored ordered by time
    # for good delta-encoding.
    op.execute(
        """
        ALTER TABLE weather_records SET (
            timescaledb.compress,
            timescaledb.compress_segmentby = 'city_id',
            timescaledb.compress_orderby = 'time DESC'
        )
        """
    )
    # Leave the last ~3 months uncompressed so recent/late-arriving data can
    # still be inserted or corrected cheaply; older chunks compress in the
    # background.
    op.execute("SELECT add_compression_policy('weather_records', INTERVAL '3 months')")

    # Daily rollup per city, continuously and incrementally refreshed, so
    # range queries over long spans (e.g. multi-year trends for one city)
    # don't have to scan/decompress raw rows.
    op.execute(
        """
        CREATE MATERIALIZED VIEW weather_daily
        WITH (timescaledb.continuous) AS
        SELECT
            city_id,
            time_bucket('1 day', time) AS day,
            AVG(temperature_c) AS avg_temp_c,
            MIN(temperature_c) AS min_temp_c,
            MAX(temperature_c) AS max_temp_c,
            AVG(humidity_pct) AS avg_humidity_pct,
            SUM(precipitation_mm) AS total_precipitation_mm,
            AVG(wind_speed_ms) AS avg_wind_speed_ms
        FROM weather_records
        GROUP BY city_id, time_bucket('1 day', time)
        WITH NO DATA
        """
    )
    # Continuous aggregates don't support UNIQUE indexes, so this is a plain
    # index; correctness relies on the GROUP BY in the view definition above.
    op.execute("CREATE INDEX ix_weather_daily_city_day ON weather_daily (city_id, day DESC)")
    op.execute(
        """
        SELECT add_continuous_aggregate_policy('weather_daily',
            start_offset => INTERVAL '3 days',
            end_offset => INTERVAL '1 day',
            schedule_interval => INTERVAL '1 day')
        """
    )


def downgrade() -> None:
    op.execute("DROP MATERIALIZED VIEW IF EXISTS weather_daily CASCADE")
    op.execute("DROP TABLE IF EXISTS weather_records CASCADE")
    op.drop_index("ix_cities_country_code", table_name="cities")
    op.drop_table("cities")
