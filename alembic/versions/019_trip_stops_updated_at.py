"""Add missing trip_stops.updated_at column (model/schema reconciliation).

Root cause of the production 500 on GET /api/v1/trips:

The ``TripStop`` ORM model inherits ``updated_at`` from ``BaseModel`` (as
every other timestamped entity in this project does), so SQLAlchemy includes
``trip_stops.updated_at`` in every SELECT, including the ``selectinload``
eager load used by ``TripRepository``. However, migration 017 created the
``trip_stops`` table WITHOUT an ``updated_at`` column, and no later migration
added one. Production Neon therefore lacks the column while the ORM expects
it, producing ``psycopg2.errors.UndefinedColumn: column trip_stops.updated_at
does not exist`` on GET /api/v1/trips (CEO dashboard).

This migration adds the column with exactly the same datatype/default/on-update
semantics used by the project's other timestamped models:

- ``DateTime(timezone=True)``, NOT NULL
- ``server_default=now()`` (matches ``BaseModel.updated_at`` server_default)
- existing rows are backfilled with the current timestamp (data preserved;
  no trip_stop business data is touched)

NOTE: the ORM's ``onupdate=func.now()`` is client-side SQL emitted on UPDATE
statements and does not require a database-side trigger, so ``now()`` as
server_default plus backfill fully reconciles model and schema.

Downgrade removes ONLY the newly added column.

Revision ID: 019_trip_stops_updated_at
Revises: 018_drop_subscription_points
Create Date: 2026-09-15
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "019_trip_stops_updated_at"
down_revision: Union[str, None] = "018_drop_subscription_points"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(inspector: sa.Inspector, table: str, column: str) -> bool:
    return column in {c["name"] for c in inspector.get_columns(table)}


def upgrade() -> None:
    inspector = sa.Inspector.from_engine(op.get_bind())

    if _has_column(inspector, "trip_stops", "updated_at"):
        # Already reconciled (e.g. partially applied); nothing to do.
        return

    # Same column definition as BaseModel.updated_at in every other
    # timestamped table (see migrations 002..011): timestamptz, NOT NULL,
    # server_default now(). server_default also covers any row inserted
    # concurrently between backfill and statement execution.
    op.add_column(
        "trip_stops",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    # Production safety: existing rows must receive a valid timestamp.
    # (With the server_default this is already true, but the backfill makes
    # the invariant explicit and covers databases where the default was
    # applied differently.)
    op.execute("UPDATE trip_stops SET updated_at = NOW() WHERE updated_at IS NULL")


def downgrade() -> None:
    inspector = sa.Inspector.from_engine(op.get_bind())

    if not _has_column(inspector, "trip_stops", "updated_at"):
        return

    op.drop_column("trip_stops", "updated_at")
