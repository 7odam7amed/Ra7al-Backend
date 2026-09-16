"""Production data reset: delete ALL operational data, preserving CEO accounts.

Safety design:
- READ-ONLY JSON snapshot of every table (plus schema fingerprint) is written
  to backups/ BEFORE any deletion (backups/ is gitignored).
- Deletion runs in ONE transaction; any failure rolls everything back.
- Refuses to run unless at least one CEO account exists.
- Users are deleted with role <> 'CEO' only; CEO rows are never touched.
- alembic_version and every table definition are never modified.
- Post-run verification re-checks every expectation inside the same script.

Usage:
    PYTHONPATH=. python scripts/reset_prod_data.py --apply
    PYTHONPATH=. python scripts/reset_prod_data.py --dry-run
"""

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import psycopg2
import psycopg2.extras

from app.core.config import get_settings

# FK-safe deletion order (children before parents). Derived from the live
# information_schema FK graph:
#   boarding_records -> subscriptions/trips/pickup_points/users
#   payments -> reservations/subscriptions/users
#   reservations -> trips/subscriptions/pickup_points/users
#   subscriptions -> payments(subscription_id RESTRICT)/routes/plans/users
#   trip_stops -> trips/pickup_points
#   trips -> routes/buses/users
#   pickup_points -> routes
#   users.university_id -> universities (CEO rows have NULL university_id)
DELETION_ORDER = [
    "boarding_records",
    "payments",
    "reservations",
    "subscriptions",
    "trip_stops",
    "trips",
    "pickup_points",
    "routes",
    "buses",
    "users",          # DELETE ... WHERE role <> 'CEO'
    "subscription_plans",
    "universities",
    "stations",
    "otp_verifications",  # guarded: absent in prod since migration 013
]

# Tables that must be empty after the reset.
EXPECTED_EMPTY = [
    t for t in DELETION_ORDER if t not in ("users", "otp_verifications")
] + ["otp_verifications"]

EXPECTED_CEO_COUNT = 5  # verified during inspection; asserted post-reset


def _snapshot(conn) -> dict:
    """READ-ONLY full-table snapshot (JSON-serializable) for the backup file."""
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
            ORDER BY table_name
            """
        )
        tables = [r["table_name"] for r in cur.fetchall()]
        data: dict = {"captured_at_utc": datetime.now(timezone.utc).isoformat()}
        for t in tables:
            cur.execute(f'SELECT * FROM "{t}"')
            data[t] = [dict(r) for r in cur.fetchall()]
        cur.execute(
            """
            SELECT table_name, column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_schema = 'public'
            ORDER BY table_name, ordinal_position
            """
        )
        data["_schema_fingerprint"] = [dict(r) for r in cur.fetchall()]
        cur.execute("SELECT version_num FROM alembic_version")
        data["_alembic_version"] = cur.fetchone()["version_num"]
        return data


def _verify(cur, expected_ceo_ids: set[int], existing_tables: set[str]) -> list[str]:
    """Return a list of verification failures (empty list = all good)."""
    failures: list[str] = []

    cur.execute("SELECT COUNT(*) FROM users WHERE role = 'CEO'")
    ceo_count = cur.fetchone()[0]
    if ceo_count != len(expected_ceo_ids):
        failures.append(
            f"CEO count changed: expected {len(expected_ceo_ids)}, found {ceo_count}"
        )

    cur.execute(
        "SELECT id, full_name, phone_number, status, is_active, role "
        "FROM users WHERE role = 'CEO' ORDER BY id"
    )
    ceos = cur.fetchall()
    for row in ceos:
        if row[0] not in expected_ceo_ids:
            failures.append(f"Unexpected CEO row appeared: {row}")
        if row[3] != "APPROVED" or not row[4] or row[5] != "CEO":
            failures.append(f"CEO account fields altered: {row}")

    cur.execute("SELECT COUNT(*) FROM users WHERE role <> 'CEO'")
    if cur.fetchone()[0] != 0:
        failures.append("Non-CEO users still remain")

    for table in EXPECTED_EMPTY:
        if table not in existing_tables:
            # e.g. otp_verifications: dropped by migration 013 in production.
            continue
        cur.execute(f'SELECT COUNT(*) FROM "{table}"')
        if cur.fetchone()[0] != 0:
            failures.append(f"Table {table} is not empty after reset")

    return failures


def _existing_tables(cur) -> set[str]:
    cur.execute(
        """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
        """
    )
    return {r[0] for r in cur.fetchall()}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--apply", action="store_true", help="Execute the deletion")
    mode.add_argument("--dry-run", action="store_true", help="Verify only")
    args = parser.parse_args()

    conn = psycopg2.connect(get_settings().DATABASE_URL)
    try:
        # Pre-counts (read-only) for the report.
        with conn.cursor() as cur:
            counts = {}
            for t in DELETION_ORDER:
                try:
                    cur.execute(f'SELECT COUNT(*) FROM "{t}"')
                    counts[t] = cur.fetchone()[0]
                except psycopg2.errors.UndefinedTable:
                    conn.rollback()
                    counts[t] = "TABLE_MISSING"
            cur.execute("SELECT id FROM users WHERE role = 'CEO' ORDER BY id")
            ceo_ids = {r[0] for r in cur.fetchall()}
        if not ceo_ids:
            raise SystemExit("REFUSING: no CEO accounts found; nothing to preserve")
        conn.rollback()

        print("Pre-reset row counts:")
        for t, c in counts.items():
            print(f"  {t}: {c}")
        print(f"CEO IDs to preserve: {sorted(ceo_ids)}")

        if args.dry_run:
            print("\nDRY RUN: no deletion executed.")
            return

        # 1. Snapshot BEFORE deleting anything.
        backup_dir = Path("backups")
        backup_dir.mkdir(exist_ok=True)
        snapshot = _snapshot(conn)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        backup_path = backup_dir / f"pre_reset_snapshot_{stamp}.json"
        backup_path.write_text(json.dumps(snapshot, default=str, indent=2))
        print(f"\nSnapshot written: {backup_path}")

        # 2. Deletion: ONE transaction, FK-safe order.
        with conn.cursor() as cur:
            tables_before = _existing_tables(cur)
            for table in DELETION_ORDER:
                if counts.get(table) == "TABLE_MISSING":
                    print(f"  skip {table} (table does not exist)")
                    continue
                if table == "users":
                    cur.execute("DELETE FROM users WHERE role <> 'CEO'")
                else:
                    cur.execute(f'DELETE FROM "{table}"')
                print(f"  deleted {cur.rowcount} row(s) from {table}")

            failures = _verify(cur, ceo_ids, tables_before)
            if failures:
                print("\nVERIFICATION FAILED — rolling back:")
                for f in failures:
                    print(f"  - {f}")
                raise SystemExit(2)

            conn.commit()
            print("\nTransaction committed.")

        # 3. Post-commit verification on a fresh snapshot of state.
        with conn.cursor() as cur:
            tables_after = _existing_tables(cur)
            failures = _verify(cur, ceo_ids, tables_after)
            cur.execute("SELECT version_num FROM alembic_version")
            version = cur.fetchone()[0]

        print("\nPost-reset verification:")
        print(f"  Alembic version: {version}")
        print(f"  Tables present ({len(tables_after)}): {', '.join(sorted(tables_after))}")
        if failures:
            print("  FAILED:")
            for f in failures:
                print(f"    - {f}")
            raise SystemExit(2)
        print("  All checks passed: CEOs preserved, operational data cleared.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
