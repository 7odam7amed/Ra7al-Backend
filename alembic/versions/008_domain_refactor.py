"""Domain refactor: remove DRIVER, add supervisor to trips, add universities and pickup_points.

Revision ID: 008_domain_refactor
Revises: 007_create_payments
Create Date: 2026-08-20
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "008_domain_refactor"
down_revision: Union[str, None] = "007_create_payments"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create universities table
    op.create_table(
        "universities",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
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
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_universities_name"), "universities", ["name"], unique=True
    )

    # 2. Add student profile fields to users table
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(
            sa.Column("university_id", sa.Integer(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("faculty", sa.String(length=100), nullable=True)
        )
        batch_op.add_column(
            sa.Column("academic_year", sa.String(length=50), nullable=True)
        )
        batch_op.add_column(
            sa.Column(
                "university_id_card_image", sa.String(length=500), nullable=True
            )
        )
        batch_op.add_column(
            sa.Column("phone_number", sa.String(length=20), nullable=True)
        )
        batch_op.create_foreign_key(
            "fk_users_university_id",
            "universities",
            ["university_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch_op.create_index(
            op.f("ix_users_university_id"), ["university_id"], unique=False
        )

    # 3. Refactor trips table: replace driver_id with supervisor_id
    with op.batch_alter_table("trips") as batch_op:
        batch_op.add_column(
            sa.Column("supervisor_id", sa.Integer(), nullable=True)
        )

    # Copy driver_id data to supervisor_id if existing rows exist
    op.execute("UPDATE trips SET supervisor_id = driver_id WHERE supervisor_id IS NULL AND driver_id IS NOT NULL")

    with op.batch_alter_table("trips") as batch_op:
        batch_op.alter_column("supervisor_id", nullable=False)
        batch_op.create_foreign_key(
            "fk_trips_supervisor_id",
            "users",
            ["supervisor_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch_op.create_index(
            op.f("ix_trips_supervisor_id"), ["supervisor_id"], unique=False
        )
        batch_op.drop_index(op.f("ix_trips_driver_id"))
        batch_op.drop_column("driver_id")

    # 4. Create pickup_points table
    op.create_table(
        "pickup_points",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("trip_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("address", sa.String(length=255), nullable=True),
        sa.Column("sequence", sa.Integer(), nullable=False),
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
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_pickup_points_trip_id"),
        "pickup_points",
        ["trip_id"],
        unique=False,
    )


def downgrade() -> None:
    # Drop pickup_points table
    op.drop_index(op.f("ix_pickup_points_trip_id"), table_name="pickup_points")
    op.drop_table("pickup_points")

    # Revert trips table: add back driver_id and drop supervisor_id
    with op.batch_alter_table("trips") as batch_op:
        batch_op.add_column(
            sa.Column("driver_id", sa.Integer(), nullable=True)
        )

    op.execute("UPDATE trips SET driver_id = supervisor_id WHERE driver_id IS NULL AND supervisor_id IS NOT NULL")

    with op.batch_alter_table("trips") as batch_op:
        batch_op.alter_column("driver_id", nullable=False)
        batch_op.create_foreign_key(
            "fk_trips_driver_id",
            "users",
            ["driver_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch_op.create_index(
            op.f("ix_trips_driver_id"), ["driver_id"], unique=False
        )
        batch_op.drop_index(op.f("ix_trips_supervisor_id"))
        batch_op.drop_column("supervisor_id")

    # Revert users table additions
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_index(op.f("ix_users_university_id"))
        batch_op.drop_constraint("fk_users_university_id", type_="foreignkey")
        batch_op.drop_column("phone_number")
        batch_op.drop_column("university_id_card_image")
        batch_op.drop_column("academic_year")
        batch_op.drop_column("faculty")
        batch_op.drop_column("university_id")

    # Drop universities table
    op.drop_index(op.f("ix_universities_name"), table_name="universities")
    op.drop_table("universities")
