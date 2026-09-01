"""Create payments table and add fare_amount to trips.

Revision ID: 007_create_payments
Revises: 006_create_reservations
Create Date: 2026-08-19
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "007_create_payments"
down_revision: Union[str, None] = "006_create_reservations"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add fare_amount to trips table
    op.add_column(
        "trips",
        sa.Column(
            "fare_amount",
            sa.Numeric(10, 2),
            server_default="50.00",
            nullable=False,
        ),
    )

    # 2. Create payments table
    op.create_table(
        "payments",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("reservation_id", sa.Integer(), nullable=False),
        sa.Column("student_id", sa.Integer(), nullable=False),
        sa.Column("amount", sa.Numeric(10, 2), nullable=False),
        sa.Column(
            "currency",
            sa.String(length=3),
            server_default="EGP",
            nullable=False,
        ),
        sa.Column(
            "method",
            sa.Enum(
                "VODAFONE_CASH",
                "INSTAPAY",
                "CASH",
                name="payment_method_enum",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "PENDING",
                "SUBMITTED",
                "VERIFIED",
                "REJECTED",
                "CANCELLED",
                name="payment_status_enum",
                native_enum=False,
            ),
            server_default="PENDING",
            nullable=False,
        ),
        sa.Column(
            "transaction_reference", sa.String(length=100), nullable=True
        ),
        sa.Column("notes", sa.String(length=500), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verified_by", sa.Integer(), nullable=True),
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
        sa.CheckConstraint("amount > 0", name="chk_payment_amount_positive"),
        sa.ForeignKeyConstraint(
            ["reservation_id"],
            ["reservations.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["student_id"],
            ["users.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["verified_by"],
            ["users.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_payments_reservation_id"),
        "payments",
        ["reservation_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_payments_student_id"),
        "payments",
        ["student_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_payments_method"), "payments", ["method"], unique=False
    )
    op.create_index(
        op.f("ix_payments_status"), "payments", ["status"], unique=False
    )
    op.create_index(
        op.f("ix_payments_created_at"), "payments", ["created_at"], unique=False
    )
    op.create_index(
        "uq_active_reservation_payment",
        "payments",
        ["reservation_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('PENDING', 'SUBMITTED', 'VERIFIED')"),
        sqlite_where=sa.text("status IN ('PENDING', 'SUBMITTED', 'VERIFIED')"),
    )


def downgrade() -> None:
    op.drop_index("uq_active_reservation_payment", table_name="payments")
    op.drop_index(op.f("ix_payments_created_at"), table_name="payments")
    op.drop_index(op.f("ix_payments_status"), table_name="payments")
    op.drop_index(op.f("ix_payments_method"), table_name="payments")
    op.drop_index(op.f("ix_payments_student_id"), table_name="payments")
    op.drop_index(op.f("ix_payments_reservation_id"), table_name="payments")
    op.drop_table("payments")
    op.drop_column("trips", "fare_amount")
