"""Create reservations table.

Revision ID: 006_create_reservations
Revises: 005_create_trips
Create Date: 2026-08-19
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "006_create_reservations"
down_revision: Union[str, None] = "005_create_trips"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "reservations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("trip_id", sa.Integer(), nullable=False),
        sa.Column("student_id", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "CONFIRMED",
                "CANCELLED",
                name="reservation_status_enum",
                native_enum=False,
            ),
            nullable=False,
            server_default="CONFIRMED",
        ),
        sa.Column(
            "booked_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "cancelled_at",
            sa.DateTime(timezone=True),
            nullable=True,
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
            ["trip_id"],
            ["trips.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["student_id"],
            ["users.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_reservations_trip_id"), "reservations", ["trip_id"], unique=False
    )
    op.create_index(
        op.f("ix_reservations_student_id"),
        "reservations",
        ["student_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_reservations_status"), "reservations", ["status"], unique=False
    )
    op.create_index(
        op.f("ix_reservations_booked_at"),
        "reservations",
        ["booked_at"],
        unique=False,
    )
    op.create_index(
        "uq_active_trip_student_reservation",
        "reservations",
        ["trip_id", "student_id"],
        unique=True,
        postgresql_where=sa.text("status = 'CONFIRMED'"),
        sqlite_where=sa.text("status = 'CONFIRMED'"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_active_trip_student_reservation", table_name="reservations"
    )
    op.drop_index(op.f("ix_reservations_booked_at"), table_name="reservations")
    op.drop_index(op.f("ix_reservations_status"), table_name="reservations")
    op.drop_index(op.f("ix_reservations_student_id"), table_name="reservations")
    op.drop_index(op.f("ix_reservations_trip_id"), table_name="reservations")
    op.drop_table("reservations")

