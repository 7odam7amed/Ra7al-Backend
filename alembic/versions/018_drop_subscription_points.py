"""Drop obsolete subscription pickup-point selection columns.

The pre-refactor subscription model stored the student's outbound/return
pickup points on the subscription itself (tied to the retired
``direction_mode`` design). Since the transportation refactor (017),
a reservation row per (student, trip, service date, direction) carries the
selected point in ``reservations.selected_pickup_point_id``; the
subscription is plan + validity + payment only. No schema, service, or API
reads these columns, and existing values are NULL.

- subscriptions: DROPS outbound_pickup_point_id, return_pickup_point_id and
  their FKs. No historical subscription data is lost (columns are unused and
  NULL); the authoritative per-direction selections live on reservations.

Downgrade restores both nullable columns and their original FK constraints.

Revision ID: 018_drop_subscription_points
Revises: 017_transportation_refactor
Create Date: 2026-09-15
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "018_drop_subscription_points"
down_revision: Union[str, None] = "017_transportation_refactor"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_DROPPED_COLUMNS: tuple[tuple[str, str, str], ...] = (
    # (column, fk_constraint_name, referenced_table)
    ("outbound_pickup_point_id", "fk_subscriptions_outbound_pickup_point_id", "pickup_points"),
    ("return_pickup_point_id", "fk_subscriptions_return_pickup_point_id", "pickup_points"),
)


def _has_column(inspector: sa.Inspector, table: str, column: str) -> bool:
    return column in {c["name"] for c in inspector.get_columns(table)}


def _has_fk(inspector: sa.Inspector, table: str, name: str) -> bool:
    return any(fk.get("name") == name for fk in inspector.get_foreign_keys(table))


def upgrade() -> None:
    inspector = sa.Inspector.from_engine(op.get_bind())

    for column, fk_name, _referenced in _DROPPED_COLUMNS:
        if not _has_column(inspector, "subscriptions", column):
            continue
        if _has_fk(inspector, "subscriptions", fk_name):
            op.drop_constraint(fk_name, "subscriptions", type_="foreignkey")
        op.drop_column("subscriptions", column)


def downgrade() -> None:
    inspector = sa.Inspector.from_engine(op.get_bind())

    for column, fk_name, referenced in _DROPPED_COLUMNS:
        if _has_column(inspector, "subscriptions", column):
            continue
        op.add_column(
            "subscriptions",
            sa.Column(column, sa.Integer(), nullable=True),
        )
        if not _has_fk(inspector, "subscriptions", fk_name):
            op.create_foreign_key(
                fk_name,
                "subscriptions",
                referenced,
                [column],
                ["id"],
                ondelete="RESTRICT",
            )
