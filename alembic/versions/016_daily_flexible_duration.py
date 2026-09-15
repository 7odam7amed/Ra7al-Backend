"""Make DAILY subscription plans fully flexible.

Business change:
- DAILY no longer means "validity = 1 calendar day". A DAILY plan is a
  flexible subscription: duration_days is the CEO-defined validity window and
  days_per_week caps the DISTINCT transportation usage days per calendar week
  (Mon-Sun, UTC) the student may select via daily reservations.
- The DB-level pinning CHECK constraint ``chk_subscription_plan_canonical_duration``
  (plan_type = 'DAILY' AND duration_days = 1) is dropped. Bounds stay enforced
  by ``chk_subscription_plan_duration_positive`` / ``chk_subscription_plan_duration_max``
  and the schema/service layers.

No columns are added or removed; no data migration is required. Existing
DAILY rows (all duration_days = 1) remain valid.

Revision ID: 016_daily_flexible_duration
Revises: 015_subscription_selection
Create Date: 2026-09-15
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "016_daily_flexible_duration"
down_revision: Union[str, None] = "015_subscription_selection"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_check_constraint(inspector, table_name: str, constraint_name: str) -> bool:
    return any(
        c.get("name") == constraint_name
        for c in inspector.get_check_constraints(table_name)
    )


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # Drop the plan-type duration pinning (DAILY is CEO-defined now).
    if _has_check_constraint(
        inspector, "subscription_plans", "chk_subscription_plan_canonical_duration"
    ):
        op.drop_constraint(
            "chk_subscription_plan_canonical_duration",
            "subscription_plans",
            type_="check",
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # Re-add the pinning constraint (fails if non-canonical DAILY rows exist).
    if not _has_check_constraint(
        inspector, "subscription_plans", "chk_subscription_plan_canonical_duration"
    ):
        op.create_check_constraint(
            "chk_subscription_plan_canonical_duration",
            "subscription_plans",
            "(plan_type = 'DAILY' AND duration_days = 1) OR "
            "(plan_type IN ('WEEKLY', 'MONTHLY', 'TERM'))",
        )
