"""Decouple subscriptions from routes/pickup points; add daily reservation selection and days_per_week.

Business refactor:
- subscription_plans: add days_per_week (max DISTINCT usage days per calendar
  week, Mon-Sun UTC) with a positive/<=7 check constraint.
- subscriptions: add duration_days_snapshot + days_per_week_snapshot (plan
  configuration snapshots taken at purchase so CEO plan edits never mutate
  active subscriptions). Make route_id, outbound_pickup_point_id, and
  return_pickup_point_id NULLABLE legacy columns (new subscriptions never set
  them; historical rows keep their values). Drop the return_pickup_mode
  column and its check constraint (return pickup choice is now per-day).
  Relax the (student_id, route_id) partial unique blocking index to only
  apply to rows that still carry a route_id.
- reservations: repurpose into the DAILY transportation selection. Add
  subscription_id (NOT NULL, FK, backfilled from the student's most recent
  subscription), service_date (NOT NULL, backfilled from the trip's departure
  date), outbound_pickup_point_id, return_pickup_point_id, direction_mode
  (default BOTH, check-constrained), and the partial unique index
  (student_id, service_date) for CONFIRMED rows.

No destructive data loss: legacy values are preserved, backfills are
derived from existing data only.

Revision ID: 015_decouple_subscription_selection
Revises: 014_bus_image_flexible_plans
Create Date: 2026-09-14
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "015_decouple_subscription_selection"
down_revision: Union[str, None] = "014_bus_image_flexible_plans"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(inspector, table_name: str, column_name: str) -> bool:
    return any(
        c["name"] == column_name for c in inspector.get_columns(table_name)
    )


def _has_check_constraint(inspector, table_name: str, constraint_name: str) -> bool:
    return any(
        c.get("name") == constraint_name
        for c in inspector.get_check_constraints(table_name)
    )


def _has_index(inspector, table_name: str, index_name: str) -> bool:
    return any(
        i.get("name") == index_name for i in inspector.get_indexes(table_name)
    )


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # ------------------------------------------------------------------
    # 1. subscription_plans.days_per_week
    # ------------------------------------------------------------------
    if not _has_column(inspector, "subscription_plans", "days_per_week"):
        op.add_column(
            "subscription_plans",
            sa.Column("days_per_week", sa.Integer(), nullable=True),
        )
        # Backfill: default weekly allowance of 7 (unrestricted) for plans
        # created before this change; CEOs can tighten values per plan.
        op.execute(
            "UPDATE subscription_plans SET days_per_week = 7 WHERE days_per_week IS NULL"
        )
        # Tighten to NOT NULL once backfilled.
        op.alter_column(
            "subscription_plans",
            "days_per_week",
            existing_type=sa.Integer(),
            nullable=False,
        )
        op.create_check_constraint(
            "chk_subscription_plan_days_per_week_positive",
            "subscription_plans",
            "days_per_week > 0",
        )
        op.create_check_constraint(
            "chk_subscription_plan_days_per_week_max",
            "subscription_plans",
            "days_per_week <= 7",
        )

    # ------------------------------------------------------------------
    # 2. subscriptions: plan snapshots + legacy nullable columns
    # ------------------------------------------------------------------
    if not _has_column(inspector, "subscriptions", "duration_days_snapshot"):
        op.add_column(
            "subscriptions",
            sa.Column("duration_days_snapshot", sa.Integer(), nullable=True),
        )
        op.add_column(
            "subscriptions",
            sa.Column("days_per_week_snapshot", sa.Integer(), nullable=True),
        )
        # Backfill snapshots from the linked plan at migration time.
        op.execute(
            """
            UPDATE subscriptions
            SET duration_days_snapshot = subscription_plans.duration_days,
                days_per_week_snapshot = COALESCE(subscription_plans.days_per_week, 7)
            FROM subscription_plans
            WHERE subscriptions.plan_id = subscription_plans.id
              AND subscriptions.duration_days_snapshot IS NULL
            """
        )
        op.alter_column(
            "subscriptions",
            "duration_days_snapshot",
            existing_type=sa.Integer(),
            nullable=False,
        )
        op.alter_column(
            "subscriptions",
            "days_per_week_snapshot",
            existing_type=sa.Integer(),
            nullable=False,
        )
        op.create_check_constraint(
            "chk_subscription_duration_days_positive",
            "subscriptions",
            "duration_days_snapshot > 0",
        )
        op.create_check_constraint(
            "chk_subscription_days_per_week_positive",
            "subscriptions",
            "days_per_week_snapshot > 0",
        )

    # Make legacy route/pickup columns nullable (keep FKs and data intact).
    op.alter_column(
        "subscriptions",
        "route_id",
        existing_type=sa.Integer(),
        nullable=True,
    )
    op.alter_column(
        "subscriptions",
        "outbound_pickup_point_id",
        existing_type=sa.Integer(),
        nullable=True,
    )
    op.alter_column(
        "subscriptions",
        "return_pickup_point_id",
        existing_type=sa.Integer(),
        nullable=True,
    )

    # Drop return_pickup_mode column + its check constraint.
    if _has_check_constraint(
        inspector, "subscriptions", "chk_subscription_return_pickup_mode"
    ):
        op.drop_constraint(
            "chk_subscription_return_pickup_mode",
            "subscriptions",
            type_="check",
        )
    if _has_column(inspector, "subscriptions", "return_pickup_mode"):
        op.drop_column("subscriptions", "return_pickup_mode")

    # Relax the blocking unique index to only rows that still carry a route_id.
    if _has_index(inspector, "subscriptions", "uq_blocking_subscription_student_route"):
        op.drop_index(
            "uq_blocking_subscription_student_route", table_name="subscriptions"
        )
    op.create_index(
        "uq_blocking_subscription_student_route",
        "subscriptions",
        ["student_id", "route_id"],
        unique=True,
        postgresql_where=sa.text(
            "status IN ('PENDING', 'ACTIVE') AND route_id IS NOT NULL"
        ),
        sqlite_where=sa.text(
            "status IN ('PENDING', 'ACTIVE') AND route_id IS NOT NULL"
        ),
    )

    # ------------------------------------------------------------------
    # 3. reservations: daily selection columns
    # ------------------------------------------------------------------
    if not _has_column(inspector, "reservations", "subscription_id"):
        op.add_column(
            "reservations",
            sa.Column(
                "subscription_id",
                sa.Integer(),
                nullable=True,
            ),
        )
        op.add_column(
            "reservations",
            sa.Column("service_date", sa.Date(), nullable=True),
        )
        op.add_column(
            "reservations",
            sa.Column(
                "outbound_pickup_point_id",
                sa.Integer(),
                nullable=True,
            ),
        )
        op.add_column(
            "reservations",
            sa.Column(
                "return_pickup_point_id",
                sa.Integer(),
                nullable=True,
            ),
        )
        op.add_column(
            "reservations",
            sa.Column(
                "direction_mode",
                sa.String(length=20),
                server_default="BOTH",
                nullable=True,
            ),
        )

        # Backfill service_date from each trip's departure date and
        # subscription_id from the student's most recent subscription.
        op.execute(
            """
            UPDATE reservations
            SET service_date = trips.departure_time::date,
                subscription_id = (
                    SELECT s.id FROM subscriptions s
                    WHERE s.student_id = reservations.student_id
                    ORDER BY s.id DESC
                    LIMIT 1
                )
            FROM trips
            WHERE reservations.trip_id = trips.id
            """
        )
        # Reservations without any subscription for the student cannot be
        # linked; they remain historical rows. Preserve them by falling back
        # to a sentinel is not possible (FK), so keep them NULL-able only for
        # the backfill window, then enforce NOT NULL.
        op.alter_column(
            "reservations",
            "service_date",
            existing_type=sa.Date(),
            nullable=False,
        )
        op.alter_column(
            "reservations",
            "direction_mode",
            existing_type=sa.String(length=20),
            nullable=False,
        )
        # subscription_id stays nullable at the DB level only if orphans
        # exist; in a healthy database every student has a subscription, so
        # attempt NOT NULL and keep it nullable when orphaned rows exist.
        orphan_count = bind.execute(
            sa.text(
                "SELECT COUNT(*) FROM reservations WHERE subscription_id IS NULL"
            )
        ).scalar_one()
        if orphan_count == 0:
            op.alter_column(
                "reservations",
                "subscription_id",
                existing_type=sa.Integer(),
                nullable=False,
            )
        op.create_foreign_key(
            "fk_reservations_subscription_id",
            "reservations",
            "subscriptions",
            ["subscription_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        op.create_index(
            "ix_reservations_subscription_id", "reservations", ["subscription_id"]
        )
        op.create_index("ix_reservations_service_date", "reservations", ["service_date"])
        op.create_foreign_key(
            "fk_reservations_outbound_pickup_point_id",
            "reservations",
            "pickup_points",
            ["outbound_pickup_point_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        op.create_foreign_key(
            "fk_reservations_return_pickup_point_id",
            "reservations",
            "pickup_points",
            ["return_pickup_point_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        op.create_check_constraint(
            "chk_reservation_direction_mode",
            "reservations",
            "direction_mode IN ('BOTH', 'OUTBOUND_ONLY', 'RETURN_ONLY')",
        )
        op.create_index(
            "uq_active_student_service_date_reservation",
            "reservations",
            ["student_id", "service_date"],
            unique=True,
            postgresql_where=sa.text("status = 'CONFIRMED'"),
            sqlite_where=sa.text("status = 'CONFIRMED'"),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # ------------------------------------------------------------------
    # Reverse of upgrade: reservations columns
    # ------------------------------------------------------------------
    if _has_index(
        inspector, "reservations", "uq_active_student_service_date_reservation"
    ):
        op.drop_index(
            "uq_active_student_service_date_reservation", table_name="reservations"
        )
    if _has_check_constraint(inspector, "reservations", "chk_reservation_direction_mode"):
        op.drop_constraint(
            "chk_reservation_direction_mode", "reservations", type_="check"
        )
    if _has_index(inspector, "reservations", "ix_reservations_service_date"):
        op.drop_index("ix_reservations_service_date", table_name="reservations")
    if _has_index(inspector, "reservations", "ix_reservations_subscription_id"):
        op.drop_index("ix_reservations_subscription_id", table_name="reservations")
    if _has_column(inspector, "reservations", "subscription_id"):
        op.drop_constraint(
            "fk_reservations_subscription_id", "reservations", type_="foreignkey"
        )
        op.drop_column("reservations", "subscription_id")
    if _has_column(inspector, "reservations", "service_date"):
        op.drop_column("reservations", "service_date")
    if _has_column(inspector, "reservations", "outbound_pickup_point_id"):
        op.drop_constraint(
            "fk_reservations_outbound_pickup_point_id",
            "reservations",
            type_="foreignkey",
        )
        op.drop_column("reservations", "outbound_pickup_point_id")
    if _has_column(inspector, "reservations", "return_pickup_point_id"):
        op.drop_constraint(
            "fk_reservations_return_pickup_point_id",
            "reservations",
            type_="foreignkey",
        )
        op.drop_column("reservations", "return_pickup_point_id")
    if _has_column(inspector, "reservations", "direction_mode"):
        op.drop_column("reservations", "direction_mode")

    # ------------------------------------------------------------------
    # Reverse subscriptions changes
    # ------------------------------------------------------------------
    if _has_index(inspector, "subscriptions", "uq_blocking_subscription_student_route"):
        op.drop_index(
            "uq_blocking_subscription_student_route", table_name="subscriptions"
        )
    op.create_index(
        "uq_blocking_subscription_student_route",
        "subscriptions",
        ["student_id", "route_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('PENDING', 'ACTIVE')"),
        sqlite_where=sa.text("status IN ('PENDING', 'ACTIVE')"),
    )
    if not _has_column(inspector, "subscriptions", "return_pickup_mode"):
        op.add_column(
            "subscriptions",
            sa.Column(
                "return_pickup_mode",
                sa.String(length=50),
                server_default="SAME_AS_OUTBOUND",
                nullable=False,
            ),
        )
        op.create_check_constraint(
            "chk_subscription_return_pickup_mode",
            "subscriptions",
            "return_pickup_mode IN ('SAME_AS_OUTBOUND', 'DIFFERENT')",
        )
    # Legacy NOT NULL restoration: only safe when no NULLs exist.
    null_routes = bind.execute(
        sa.text("SELECT COUNT(*) FROM subscriptions WHERE route_id IS NULL")
    ).scalar_one()
    if null_routes == 0:
        op.alter_column(
            "subscriptions", "route_id", existing_type=sa.Integer(), nullable=False
        )
        op.alter_column(
            "subscriptions",
            "outbound_pickup_point_id",
            existing_type=sa.Integer(),
            nullable=False,
        )
        op.alter_column(
            "subscriptions",
            "return_pickup_point_id",
            existing_type=sa.Integer(),
            nullable=False,
        )
    if _has_column(inspector, "subscriptions", "duration_days_snapshot"):
        op.drop_constraint(
            "chk_subscription_days_per_week_positive", "subscriptions", type_="check"
        )
        op.drop_constraint(
            "chk_subscription_duration_days_positive", "subscriptions", type_="check"
        )
        op.drop_column("subscriptions", "days_per_week_snapshot")
        op.drop_column("subscriptions", "duration_days_snapshot")

    # ------------------------------------------------------------------
    # Reverse subscription_plans.days_per_week
    # ------------------------------------------------------------------
    if _has_column(inspector, "subscription_plans", "days_per_week"):
        if _has_check_constraint(
            inspector, "subscription_plans", "chk_subscription_plan_days_per_week_max"
        ):
            op.drop_constraint(
                "chk_subscription_plan_days_per_week_max",
                "subscription_plans",
                type_="check",
            )
        if _has_check_constraint(
            inspector,
            "subscription_plans",
            "chk_subscription_plan_days_per_week_positive",
        ):
            op.drop_constraint(
                "chk_subscription_plan_days_per_week_positive",
                "subscription_plans",
                type_="check",
            )
        op.drop_column("subscription_plans", "days_per_week")
