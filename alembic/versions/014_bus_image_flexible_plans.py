"""Add buses.image_url and enable CEO-defined subscription plan durations.

- Adds nullable image_url column to buses (storage reference, not binary data).
- Adds WEEKLY to the subscription plan type vocabulary (plan_type is a VARCHAR
  with a non-native enum, so no PostgreSQL enum alteration is required).
- Drops the canonical duration check constraint that forced
  DAILY=1/MONTHLY=30/TERM=90 so MONTHLY/TERM/WEEKLY durations are CEO-defined.
- Drops the unique constraint on subscription_plans.plan_type so multiple
  packages per type can coexist (e.g. Monthly Standard 30d + Monthly Plus 45d).
- Re-adds the canonical constraint in a relaxed form (DAILY pinned to 1 day).
- Adds a duration upper bound check (730 days).

Revision ID: 014_bus_image_flexible_plans
Revises: 013_remove_otp_verification
Create Date: 2026-09-12
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "014_bus_image_flexible_plans"
down_revision: Union[str, None] = "013_remove_otp_verification"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

MAX_PLAN_DURATION_DAYS = 730


def _has_check_constraint(inspector, table_name: str, constraint_name: str) -> bool:
    return any(
        c.get("name") == constraint_name
        for c in inspector.get_check_constraints(table_name)
    )


def _has_unique_constraint(inspector, table_name: str, constraint_name: str) -> bool:
    return any(
        c.get("name") == constraint_name
        for c in inspector.get_unique_constraints(table_name)
    )


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # 1. Add buses.image_url
    bus_columns = [c["name"] for c in inspector.get_columns("buses")]
    if "image_url" not in bus_columns:
        op.add_column(
            "buses",
            sa.Column("image_url", sa.String(length=500), nullable=True),
        )

    # 2. Relax subscription plan duration constraints
    plan_constraints = inspector.get_check_constraints("subscription_plans")
    has_canonical = any(
        c.get("name") == "chk_subscription_plan_canonical_duration"
        for c in plan_constraints
    )
    has_max = any(
        c.get("name") == "chk_subscription_plan_duration_max"
        for c in plan_constraints
    )

    if has_canonical:
        op.drop_constraint(
            "chk_subscription_plan_canonical_duration",
            "subscription_plans",
            type_="check",
        )
    op.create_check_constraint(
        "chk_subscription_plan_canonical_duration",
        "subscription_plans",
        "(plan_type = 'DAILY' AND duration_days = 1) OR "
        "(plan_type IN ('WEEKLY', 'MONTHLY', 'TERM'))",
    )

    if not has_max:
        op.create_check_constraint(
            "chk_subscription_plan_duration_max",
            "subscription_plans",
            f"duration_days <= {MAX_PLAN_DURATION_DAYS}",
        )

    # 3. Allow multiple plans per type (duplicate packages prevented at service level)
    if _has_unique_constraint(
        inspector, "subscription_plans", "uq_subscription_plans_plan_type"
    ):
        op.drop_constraint(
            "uq_subscription_plans_plan_type",
            "subscription_plans",
            type_="unique",
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # 1. Restore one-plan-per-type uniqueness (requires no duplicate plan_types)
    if not _has_unique_constraint(
        inspector, "subscription_plans", "uq_subscription_plans_plan_type"
    ):
        op.create_unique_constraint(
            "uq_subscription_plans_plan_type",
            "subscription_plans",
            ["plan_type"],
        )

    # 2. Restore canonical fixed-duration constraint (fails if non-canonical rows exist)
    if _has_check_constraint(
        inspector, "subscription_plans", "chk_subscription_plan_duration_max"
    ):
        op.drop_constraint(
            "chk_subscription_plan_duration_max",
            "subscription_plans",
            type_="check",
        )
    if _has_check_constraint(
        inspector, "subscription_plans", "chk_subscription_plan_canonical_duration"
    ):
        op.drop_constraint(
            "chk_subscription_plan_canonical_duration",
            "subscription_plans",
            type_="check",
        )
        op.create_check_constraint(
            "chk_subscription_plan_canonical_duration",
            "subscription_plans",
            "(plan_type = 'DAILY' AND duration_days = 1) OR "
            "(plan_type = 'MONTHLY' AND duration_days = 30) OR "
            "(plan_type = 'TERM' AND duration_days = 90)",
        )

    # 3. Drop buses.image_url
    bus_columns = [c["name"] for c in inspector.get_columns("buses")]
    if "image_url" in bus_columns:
        op.drop_column("buses", "image_url")
