"""READ-ONLY inspection of the production database before data cleanup.

Prints per-table row counts and the users role breakdown so the cleanup
plan can be reviewed before any DELETE is executed. Never writes.
"""

import sys

import psycopg2

from app.core.config import get_settings


def main() -> None:
    url = get_settings().DATABASE_URL
    conn = psycopg2.connect(url)
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
                ORDER BY table_name
                """
            )
            tables = [r[0] for r in cur.fetchall()]
            print(f"Connected. Tables ({len(tables)}):")
            for t in tables:
                cur.execute(f'SELECT COUNT(*) FROM "{t}"')
                print(f"  {t}: {cur.fetchone()[0]}")

            print("\nUsers by role:")
            cur.execute("SELECT role, COUNT(*) FROM users GROUP BY role ORDER BY role")
            for role, count in cur.fetchall():
                print(f"  {role}: {count}")

            print("\nCEO accounts:")
            cur.execute(
                """
                SELECT id, full_name, phone_number, status, is_active
                FROM users WHERE role = 'CEO' ORDER BY id
                """
            )
            for row in cur.fetchall():
                print(f"  {row}")

            cur.execute(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = 'alembic_version'
                """
            )
            if cur.fetchone():
                cur.execute("SELECT version_num FROM alembic_version")
                print(f"\nAlembic version: {cur.fetchone()[0]}")
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
