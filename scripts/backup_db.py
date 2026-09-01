"""Secure PostgreSQL database backup automation script for Ra7al Backend.

Usage:
    python scripts/backup_db.py [--output-dir /path/to/backups]

Environment Variables:
    DATABASE_URL: Full database connection string (e.g. postgresql://<user>:<password>@<host>:5432/<dbname>)
"""

import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import subprocess
import sys
from urllib.parse import urlparse


def parse_database_url(url: str) -> dict[str, str | int]:
    """Extract connection parameters from DATABASE_URL."""
    parsed = urlparse(url)
    if parsed.scheme not in ("postgresql", "postgres"):
        raise ValueError(f"Unsupported database scheme: {parsed.scheme}")

    return {
        "user": parsed.username or "postgres",
        "password": parsed.password or "",
        "host": parsed.hostname or "localhost",
        "port": parsed.port or 5432,
        "dbname": parsed.path.lstrip("/") or "bus_system",
    }


def perform_backup(output_dir: Path) -> Path:
    """Execute pg_dump with environment-based credential injection."""
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("ERROR: DATABASE_URL environment variable is required", file=sys.stderr)
        sys.exit(1)

    db_params = parse_database_url(db_url)
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_file = output_dir / f"ra7al_backup_{timestamp}.dump"

    env = os.environ.copy()
    if db_params["password"]:
        env["PGPASSWORD"] = str(db_params["password"])

    cmd = [
        "pg_dump",
        "-h",
        str(db_params["host"]),
        "-p",
        str(db_params["port"]),
        "-U",
        str(db_params["user"]),
        "-d",
        str(db_params["dbname"]),
        "-Fc",  # Custom format (compressed, suitable for pg_restore)
        "-f",
        str(backup_file),
    ]

    print(f"Starting database backup to {backup_file}...")
    try:
        subprocess.run(cmd, env=env, check=True, capture_output=True, text=True)
        print(f"Backup successfully generated: {backup_file}")
        return backup_file
    except subprocess.CalledProcessError as e:
        print(f"ERROR: pg_dump failed: {e.stderr}", file=sys.stderr)
        sys.exit(1)
    except FileNotFoundError:
        print("ERROR: pg_dump executable not found in PATH", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backup Ra7al PostgreSQL database.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("backups"),
        help="Directory to store backup dumps (default: ./backups)",
    )
    args = parser.parse_args()
    perform_backup(args.output_dir)
