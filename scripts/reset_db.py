#!/usr/bin/env python3
"""Drop and recreate the weather database, then reapply migrations.

Table structure — the weather_records hypertable (monthly chunks),
its compression policy, and the weather_daily continuous aggregate —
lives entirely in the Alembic migration (alembic/versions/), not in
this script. So a full reset is just: drop db, create db, `alembic
upgrade head`; the migration recreates the hypertable/compression/
continuous aggregate exactly as declared.

Dropping/creating the database itself needs a role with CREATEDB
(the app role `weather_app` doesn't have it), so those two steps
shell out to psql as an admin role. psql will prompt for a password
if one isn't available via PGPASSWORD/~/.pgpass.
"""
import argparse
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit

from alembic import command
from alembic.config import Config

from app.config import settings

REPO_ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--admin-user", default="postgres", help="Role used to drop/create the database (needs CREATEDB)")
    parser.add_argument("--admin-db", default="postgres", help="Maintenance database to connect to for admin ops")
    parser.add_argument("--yes", action="store_true", help="Skip the confirmation prompt")
    args = parser.parse_args()

    url = urlsplit(settings.database_url.replace("+asyncpg", ""))
    db_name = url.path.lstrip("/")
    host = url.hostname
    port = url.port or 5432
    app_user = url.username

    if not args.yes:
        confirm = input(
            f"This will DROP and recreate database {db_name!r} on {host}:{port}, "
            f"destroying all data in it. Type the database name to confirm: "
        )
        if confirm != db_name:
            print("Aborted.")
            sys.exit(1)

    psql_base = [
        "psql", "-v", "ON_ERROR_STOP=1",
        "-h", host, "-p", str(port),
        "-U", args.admin_user, "-d", args.admin_db,
    ]

    print(f"Terminating other connections to {db_name!r}...")
    subprocess.run(
        psql_base + ["-c",
            f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            f"WHERE datname = '{db_name}' AND pid <> pg_backend_pid()"],
        check=True,
    )

    print(f"Dropping database {db_name!r}...")
    subprocess.run(psql_base + ["-c", f'DROP DATABASE IF EXISTS "{db_name}"'], check=True)

    print(f"Creating database {db_name!r} (owner {app_user!r})...")
    subprocess.run(psql_base + ["-c", f'CREATE DATABASE "{db_name}" OWNER "{app_user}"'], check=True)

    print("Running Alembic migrations (cities table, weather_records hypertable, "
          "compression policy, weather_daily continuous aggregate)...")
    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(REPO_ROOT / "alembic"))
    command.upgrade(cfg, "head")

    print("Done.")


if __name__ == "__main__":
    main()
