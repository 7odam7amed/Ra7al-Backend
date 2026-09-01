"""Create subscription_plans, subscriptions, and boarding_records tables and link payments.

Revision ID: 009_create_subscriptions_and_boarding
Revises: 008_domain_refactor
Create Date: 2026-08-21
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "009_subscriptions_boarding"
down_revision: Union[str, None] = "008_domain_refactor"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create subscription_plans table
    op.create_table(
        "subscription_plans",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("plan_type", sa.String(length=50), nullable=False),
        sa.Column("duration_days", sa.Integer(), nullable=False),
        sa.Column("price", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column(
            "currency",
            sa.String(length=3),
            server_default="EGP",
            nullable=False,
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("price > 0", name="chk_subscription_plan_price_positive"),
        sa.CheckConstraint(
            "duration_days > 0",
            name="chk_subscription_plan_duration_positive",
        ),
        sa.CheckConstraint(
            "(plan_type = 'DAILY' AND duration_days = 1) OR "
            "(plan_type = 'MONTHLY' AND duration_days = 30) OR "
            "(plan_type = 'TERM' AND duration_days = 90)",
            name="chk_subscription_plan_canonical_duration",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("plan_type", name="uq_subscription_plans_plan_type"),
    )
    op.create_index(
        op.f("ix_subscription_plans_plan_type"),
        "subscription_plans",
        ["plan_type"],
        unique=False,
    )

    # 2. Create subscriptions table
    op.create_table(
        "subscriptions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("student_id", sa.Integer(), nullable=False),
        sa.Column("route_id", sa.Integer(), nullable=False),
        sa.Column("plan_id", sa.Integer(), nullable=False),
        sa.Column("price_snapshot", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column(
            "currency",
            sa.String(length=3),
            server_default="EGP",
            nullable=False,
        ),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("outbound_pickup_point_id", sa.Integer(), nullable=False),
        sa.Column("return_pickup_point_id", sa.Integer(), nullable=False),
        sa.Column(
            "return_pickup_mode",
            sa.String(length=50),
            server_default="SAME_AS_OUTBOUND",
            nullable=False,
        ),
        sa.Column("payment_id", sa.Integer(), nullable=True),
        sa.Column(
            "status",
            sa.String(length=50),
            server_default="PENDING",
            nullable=False,
        ),
        sa.Column("qr_token_hash", sa.String(length=64), nullable=False),
        sa.Column("qr_token", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "end_date >= start_date",
            name="chk_subscription_end_date_after_start_date",
        ),
        sa.CheckConstraint("price_snapshot > 0", name="chk_subscription_price_positive"),
        sa.CheckConstraint(
            "return_pickup_mode IN ('SAME_AS_OUTBOUND', 'DIFFERENT')",
            name="chk_subscription_return_pickup_mode",
        ),
        sa.CheckConstraint(
            "status IN ('PENDING', 'ACTIVE', 'EXPIRED', 'CANCELLED')",
            name="chk_subscription_status",
        ),
        sa.ForeignKeyConstraint(
            ["student_id"],
            ["users.id"],
            name="fk_subscriptions_student_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["route_id"],
            ["routes.id"],
            name="fk_subscriptions_route_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["plan_id"],
            ["subscription_plans.id"],
            name="fk_subscriptions_plan_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["outbound_pickup_point_id"],
            ["pickup_points.id"],
            name="fk_subscriptions_outbound_pickup_point_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["return_pickup_point_id"],
            ["pickup_points.id"],
            name="fk_subscriptions_return_pickup_point_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["payment_id"],
            ["payments.id"],
            name="fk_subscriptions_payment_id",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_subscriptions_student_id"),
        "subscriptions",
        ["student_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_subscriptions_route_id"),
        "subscriptions",
        ["route_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_subscriptions_plan_id"),
        "subscriptions",
        ["plan_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_subscriptions_status"),
        "subscriptions",
        ["status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_subscriptions_start_date"),
        "subscriptions",
        ["start_date"],
        unique=False,
    )
    op.create_index(
        op.f("ix_subscriptions_end_date"),
        "subscriptions",
        ["end_date"],
        unique=False,
    )
    op.create_index(
        op.f("ix_subscriptions_payment_id"),
        "subscriptions",
        ["payment_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_subscriptions_qr_token_hash"),
        "subscriptions",
        ["qr_token_hash"],
        unique=True,
    )
    op.create_index(
        "uq_blocking_subscription_student_route",
        "subscriptions",
        ["student_id", "route_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('PENDING', 'ACTIVE')"),
        sqlite_where=sa.text("status IN ('PENDING', 'ACTIVE')"),
    )

    # 3. Alter payments table to support subscriptions
    with op.batch_alter_table("payments") as batch_op:
        batch_op.alter_column("reservation_id", nullable=True)
        batch_op.add_column(
            sa.Column("subscription_id", sa.Integer(), nullable=True)
        )
        batch_op.create_foreign_key(
            "fk_payments_subscription_id",
            "subscriptions",
            ["subscription_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch_op.create_index(
            op.f("ix_payments_subscription_id"),
            ["subscription_id"],
            unique=False,
        )
        batch_op.create_check_constraint(
            "chk_payment_target_exclusive",
            "(reservation_id IS NOT NULL AND subscription_id IS NULL) "
            "OR (reservation_id IS NULL AND subscription_id IS NOT NULL)",
        )

    op.create_index(
        "uq_active_subscription_payment",
        "payments",
        ["subscription_id"],
        unique=True,
        postgresql_where=sa.text(
            "subscription_id IS NOT NULL AND status IN ('PENDING', 'SUBMITTED', 'VERIFIED')"
        ),
        sqlite_where=sa.text(
            "subscription_id IS NOT NULL AND status IN ('PENDING', 'SUBMITTED', 'VERIFIED')"
        ),
    )

    # 4. Create boarding_records table
    op.create_table(
        "boarding_records",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("subscription_id", sa.Integer(), nullable=False),
        sa.Column("student_id", sa.Integer(), nullable=False),
        sa.Column("trip_id", sa.Integer(), nullable=False),
        sa.Column("supervisor_id", sa.Integer(), nullable=False),
        sa.Column("direction", sa.String(length=50), nullable=False),
        sa.Column("pickup_point_id", sa.Integer(), nullable=False),
        sa.Column(
            "boarded_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["subscription_id"],
            ["subscriptions.id"],
            name="fk_boarding_records_subscription_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["student_id"],
            ["users.id"],
            name="fk_boarding_records_student_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["trip_id"],
            ["trips.id"],
            name="fk_boarding_records_trip_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["supervisor_id"],
            ["users.id"],
            name="fk_boarding_records_supervisor_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["pickup_point_id"],
            ["pickup_points.id"],
            name="fk_boarding_records_pickup_point_id",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "subscription_id",
            "trip_id",
            "direction",
            name="uq_boarding_subscription_trip_direction",
        ),
        sa.CheckConstraint(
            "direction IN ('OUTBOUND', 'RETURN')",
            name="chk_boarding_direction",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_boarding_records_subscription_id"),
        "boarding_records",
        ["subscription_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_boarding_records_student_id"),
        "boarding_records",
        ["student_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_boarding_records_trip_id"),
        "boarding_records",
        ["trip_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_boarding_records_supervisor_id"),
        "boarding_records",
        ["supervisor_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_boarding_records_boarded_at"),
        "boarding_records",
        ["boarded_at"],
        unique=False,
    )


def downgrade() -> None:
    # Drop boarding_records table
    op.drop_index(
        op.f("ix_boarding_records_boarded_at"),
        table_name="boarding_records",
    )
    op.drop_index(
        op.f("ix_boarding_records_supervisor_id"),
        table_name="boarding_records",
    )
    op.drop_index(
        op.f("ix_boarding_records_trip_id"),
        table_name="boarding_records",
    )
    op.drop_index(
        op.f("ix_boarding_records_student_id"),
        table_name="boarding_records",
    )
    op.drop_index(
        op.f("ix_boarding_records_subscription_id"),
        table_name="boarding_records",
    )
    op.drop_table("boarding_records")

    # Revert payments table
    op.drop_index("uq_active_subscription_payment", table_name="payments")
    with op.batch_alter_table("payments") as batch_op:
        batch_op.drop_constraint(
            "chk_payment_target_exclusive", type_="check"
        )
        batch_op.drop_index(op.f("ix_payments_subscription_id"))
        batch_op.drop_constraint(
            "fk_payments_subscription_id", type_="foreignkey"
        )
        batch_op.drop_column("subscription_id")
        batch_op.alter_column("reservation_id", nullable=False)

    # Drop subscriptions table
    op.drop_index(
        "uq_blocking_subscription_student_route", table_name="subscriptions"
    )
    op.drop_index(
        op.f("ix_subscriptions_qr_token_hash"), table_name="subscriptions"
    )
    op.drop_index(
        op.f("ix_subscriptions_payment_id"), table_name="subscriptions"
    )
    op.drop_index(
        op.f("ix_subscriptions_end_date"), table_name="subscriptions"
    )
    op.drop_index(
        op.f("ix_subscriptions_start_date"), table_name="subscriptions"
    )
    op.drop_index(
        op.f("ix_subscriptions_status"), table_name="subscriptions"
    )
    op.drop_index(
        op.f("ix_subscriptions_plan_id"), table_name="subscriptions"
    )
    op.drop_index(
        op.f("ix_subscriptions_route_id"), table_name="subscriptions"
    )
    op.drop_index(
        op.f("ix_subscriptions_student_id"), table_name="subscriptions"
    )
    op.drop_table("subscriptions")

    # Drop subscription_plans table
    op.drop_index(
        op.f("ix_subscription_plans_plan_type"),
        table_name="subscription_plans",
    )
    op.drop_table("subscription_plans")
