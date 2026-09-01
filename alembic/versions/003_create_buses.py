"""Create buses table.

Revision ID: 003_create_buses
Revises: 002_create_users
Create Date: 2026-08-19
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "003_create_buses"
down_revision: Union[str, None] = "002_create_users"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "buses",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("bus_number", sa.String(length=50), nullable=False),
        sa.Column("license_plate", sa.String(length=50), nullable=False),
        sa.Column("capacity", sa.Integer(), nullable=False),
        sa.Column("model", sa.String(length=100), nullable=True),
        sa.Column("year", sa.Integer(), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "ACTIVE",
                "INACTIVE",
                "MAINTENANCE",
                name="bus_status_enum",
                native_enum=False,
            ),
            nullable=False,
            server_default="ACTIVE",
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
        sa.CheckConstraint("capacity > 0", name="chk_bus_capacity_positive"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_buses_bus_number"), "buses", ["bus_number"], unique=True)
    op.create_index(
        op.f("ix_buses_license_plate"), "buses", ["license_plate"], unique=True
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_buses_license_plate"), table_name="buses")
    op.drop_index(op.f("ix_buses_bus_number"), table_name="buses")
    op.drop_table("buses")
