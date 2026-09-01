"""Create trips table.

Revision ID: 005_create_trips
Revises: 004_create_stations_routes
Create Date: 2026-08-19
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "005_create_trips"
down_revision: Union[str, None] = "004_create_stations_routes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "trips",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("route_id", sa.Integer(), nullable=False),
        sa.Column("bus_id", sa.Integer(), nullable=False),
        sa.Column("driver_id", sa.Integer(), nullable=False),
        sa.Column("departure_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "estimated_arrival_time", sa.DateTime(timezone=True), nullable=False
        ),
        sa.Column(
            "status",
            sa.Enum(
                "SCHEDULED",
                "IN_PROGRESS",
                "COMPLETED",
                "CANCELLED",
                name="trip_status_enum",
                native_enum=False,
            ),
            nullable=False,
            server_default="SCHEDULED",
        ),
        sa.Column("passenger_capacity", sa.Integer(), nullable=False),
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
            ["route_id"],
            ["routes.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["bus_id"],
            ["buses.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["driver_id"],
            ["users.id"],
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "estimated_arrival_time > departure_time",
            name="chk_trip_arrival_after_departure",
        ),
        sa.CheckConstraint(
            "passenger_capacity > 0",
            name="chk_trip_passenger_capacity_positive",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_trips_route_id"), "trips", ["route_id"], unique=False)
    op.create_index(op.f("ix_trips_bus_id"), "trips", ["bus_id"], unique=False)
    op.create_index(op.f("ix_trips_driver_id"), "trips", ["driver_id"], unique=False)
    op.create_index(
        op.f("ix_trips_departure_time"), "trips", ["departure_time"], unique=False
    )
    op.create_index(op.f("ix_trips_status"), "trips", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_trips_status"), table_name="trips")
    op.drop_index(op.f("ix_trips_departure_time"), table_name="trips")
    op.drop_index(op.f("ix_trips_driver_id"), table_name="trips")
    op.drop_index(op.f("ix_trips_bus_id"), table_name="trips")
    op.drop_index(op.f("ix_trips_route_id"), table_name="trips")
    op.drop_table("trips")
