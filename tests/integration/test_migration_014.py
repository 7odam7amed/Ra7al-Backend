"""Database migration and model/migration consistency tests.

Verifies the structural guarantees that keep the application schema and the
Alembic migration chain aligned (production root cause #1 was a schema drift:
the application expected buses.image_url but the deployed database predated
migration 014).

These tests run against the in-memory SQLite test database created from the
ORM metadata, and statically validate the Alembic migration files.
"""
import re
from pathlib import Path

from app.models.base import BaseModel


def _alembic_versions_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "alembic" / "versions"


def test_migration_017_is_current_head() -> None:
    """017 must be the single Alembic head reachable from the chain."""
    revisions: dict[str, str | None] = {}
    for path in _alembic_versions_dir().glob("*.py"):
        content = path.read_text(encoding="utf-8")
        rev_match = re.search(r'^revision:\s*str\s*=\s*"([^"]+)"', content, re.MULTILINE)
        down_match = re.search(
            r'^down_revision:\s*Union\[str, None\]\s*=\s*(?:"([^"]+)"|None)', content, re.MULTILINE
        )
        if rev_match:
            revisions[rev_match.group(1)] = (
                down_match.group(1) if down_match and down_match.group(1) else None
            )

    assert "014_bus_image_flexible_plans" in revisions
    assert revisions["014_bus_image_flexible_plans"] == "013_remove_otp_verification"
    assert "015_subscription_selection" in revisions
    assert revisions["015_subscription_selection"] == "014_bus_image_flexible_plans"
    assert "016_daily_flexible_duration" in revisions
    assert revisions["016_daily_flexible_duration"] == "015_subscription_selection"
    assert "017_transportation_refactor" in revisions
    assert revisions["017_transportation_refactor"] == "016_daily_flexible_duration"
    assert "018_drop_subscription_points" in revisions
    assert revisions["018_drop_subscription_points"] == "017_transportation_refactor"
    assert "019_trip_stops_updated_at" in revisions
    assert revisions["019_trip_stops_updated_at"] == "018_drop_subscription_points"

    # Single head: no revision besides 019 may be un-referenced as a down_revision
    referenced = {d for d in revisions.values() if d is not None}
    heads = [r for r in revisions if r not in referenced]
    assert heads == ["019_trip_stops_updated_at"]

    # alembic_version.version_num is VARCHAR(32): every revision id must fit
    for revision_id in revisions:
        assert len(revision_id) <= 32, (
            f"Revision id '{revision_id}' exceeds 32 characters"
        )


def test_migration_014_upgrade_adds_image_url_non_destructively() -> None:
    """Migration 014 upgrade must add buses.image_url and never drop bus data."""
    content = (_alembic_versions_dir() / "014_bus_image_flexible_plans.py").read_text(
        encoding="utf-8"
    )

    # Conditional, idempotent column add (safe against already-migrated prod)
    assert '"image_url" not in bus_columns' in content
    assert 'op.add_column(' in content
    assert 'sa.Column("image_url", sa.String(length=500), nullable=True)' in content

    # Nullable column + no destructive statements in upgrade()
    assert "nullable=True" in content
    upgrade_section = content.split("def upgrade")[1].split("def downgrade")[0]
    assert "op.drop_table" not in upgrade_section
    assert "op.drop_column" not in upgrade_section


def test_migration_014_downgrade_removes_image_url() -> None:
    """Downgrade path must remove image_url (verifying full reversibility)."""
    content = (_alembic_versions_dir() / "014_bus_image_flexible_plans.py").read_text(
        encoding="utf-8"
    )
    downgrade = content.split("def downgrade")[1]
    assert 'op.drop_column("buses", "image_url")' in downgrade


def test_bus_model_matches_migration_014_column_definition() -> None:
    """The Bus ORM model must declare image_url exactly as migration 014 creates it."""
    from app.models.bus import Bus

    column = Bus.__table__.columns["image_url"]
    assert column is not None
    assert column.nullable is True
    assert column.type.length == 500


def test_models_do_not_drift_from_alembic_chain() -> None:
    """Every ORM table must exist in at least one migration's declared lineage.

    Guards against future model additions without a corresponding migration
    (the root cause of the production schema drift).
    """
    migration_content = ""
    for path in _alembic_versions_dir().glob("*.py"):
        migration_content += path.read_text(encoding="utf-8")

    for table in BaseModel.metadata.tables.values():
        if table.name == "alembic_version":
            continue
        # The table must be referenced by name in the migration chain
        assert f'"{table.name}"' in migration_content, (
            f"Table '{table.name}' exists in ORM metadata but is never referenced "
            f"by any Alembic migration file"
        )


def test_migration_019_reconciles_trip_stops_updated_at() -> None:
    """Regression guard for the production 500 on GET /api/v1/trips.

    Migration 017 created trip_stops WITHOUT updated_at while the TripStop
    ORM model inherits it from BaseModel. Migration 019 must add the column
    with the project-wide timestamp semantics (timestamptz, NOT NULL,
    server_default now()) and backfill existing rows; its downgrade must
    remove only that column.
    """
    content = (
        _alembic_versions_dir() / "019_trip_stops_updated_at.py"
    ).read_text(encoding="utf-8")

    assert "op.add_column(" in content
    assert '"trip_stops",' in content
    assert '"updated_at"' in content
    assert "sa.DateTime(timezone=True)" in content
    assert "server_default=sa.func.now()" in content
    assert "nullable=False" in content
    # Existing production rows must receive a valid timestamp.
    assert "UPDATE trip_stops SET updated_at" in content
    # Downgrade removes only the newly added column.
    downgrade = content.split("def downgrade")[1]
    assert 'op.drop_column("trip_stops", "updated_at")' in downgrade

    # The ORM model must declare exactly what the migration creates.
    from app.models.base import BaseModel

    column = BaseModel.metadata.tables["trip_stops"].columns["updated_at"]
    assert column.nullable is False
    assert column.server_default is not None


def test_bus_image_url_is_optional_in_create_path() -> None:
    """BusRepository.create must accept creation without image_url (no-image flow)."""
    import inspect

    from app.repositories.bus_repository import BusRepository

    signature = inspect.signature(BusRepository.create)
    image_param = signature.parameters.get("image_url")
    assert image_param is not None
    assert image_param.default is None
