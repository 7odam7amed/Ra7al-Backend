"""Transportation refactor: route containers, trip direction + stops, per-direction reservations.

Business refactor (all changes are additive or preserve history):

- routes: becomes a logical container of pickup points. Drops origin/destination
  station links, distance, duration, route_number, supervisor_id, and the
  origin!=destination / positive-distance / positive-duration CHECK constraints.
- pickup_points: re-scoped from trips to routes (one route per point). Gains
  route_id (NOT NULL after backfill) and unique (route_id, name); drops trip_id.
- route_stops: DROPPED (redundant: pickup points are the route's stops).
- trip_stops: NEW table: ordered selection of route points per trip with a
  per-stop departure time (nullable only for migrated historical rows).
- trips: gains direction (OUTBOUND/RETURN, backfilled OUTBOUND) and
  allow_overbooking (default False). Drops fare_amount (pricing left the trip
  model; transportation is subscription-covered). Existing trips keep their
  departure/arrival; historical trips without stop times keep NULL stop times.
- reservations: one row per direction. Gains direction (backfilled from
  context) and selected_pickup_point_id (backfilled per direction_mode);
  drops outbound_pickup_point_id, return_pickup_point_id, direction_mode.
  The (student_id, service_date) unique index becomes (student_id, service_date,
  direction) so one outbound + one return are allowed per date.

Revision ID: 017_transportation_refactor
Revises: 016_daily_flexible_duration
Create Date: 2026-09-15
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "017_transportation_refactor"
down_revision: Union[str, None] = "016_daily_flexible_duration"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(inspector, table_name: str, column_name: str) -> bool:
    return any(
        c["name"] == column_name for c in inspector.get_columns(table_name)
    )


def _has_table(inspector, table_name: str) -> bool:
    return table_name in inspector.get_table_names()


def _has_check_constraint(inspector, table_name: str, constraint_name: str) -> bool:
    return any(
        c.get("name") == constraint_name
        for c in inspector.get_check_constraints(table_name)
    )


def _has_index(inspector, table_name: str, index_name: str) -> bool:
    return any(
        i.get("name") == index_name for i in inspector.get_indexes(table_name)
    )


def _has_unique_constraint(inspector, table_name: str, constraint_name: str) -> bool:
    return any(
        c.get("name") == constraint_name
        for c in inspector.get_unique_constraints(table_name)
    )


def _has_foreign_key(inspector, table_name: str, fk_name: str) -> bool:
    return any(
        fk.get("name") == fk_name
        for fk in inspector.get_foreign_keys(table_name)
    )


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # ------------------------------------------------------------------
    # 1. routes: strip to a container of pickup points
    # ------------------------------------------------------------------
    # 1. routes: legacy columns are dropped AFTER pickup_points re-scoping
    #    (step 3) because the synthetic-route backfill for orphan points must
    #    satisfy the legacy NOT NULL constraints while they still exist.
    # ------------------------------------------------------------------
    route_cols = {c["name"] for c in inspector.get_columns("routes")}

    # ------------------------------------------------------------------
    # 2. trip_stops: NEW ordered per-trip stop selection.
    #    Created BEFORE pickup_points are re-scoped so the historical
    #    trip -> point links (pickup_points.trip_id) can be copied while
    #    the legacy column still exists. departure_time stays NULL for
    #    historical rows (legacy points had no times; we never invent data).
    # ------------------------------------------------------------------
    if not _has_table(inspector, "trip_stops"):
        op.create_table(
            "trip_stops",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column(
                "trip_id",
                sa.Integer(),
                sa.ForeignKey("trips.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "pickup_point_id",
                sa.Integer(),
                sa.ForeignKey("pickup_points.id", ondelete="RESTRICT"),
                nullable=False,
            ),
            sa.Column("stop_order", sa.Integer(), nullable=False),
            sa.Column("departure_time", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.CheckConstraint(
                "stop_order > 0", name="chk_trip_stop_order_positive"
            ),
            sa.UniqueConstraint(
                "trip_id", "pickup_point_id", name="uq_trip_stop_trip_point"
            ),
            sa.UniqueConstraint(
                "trip_id", "stop_order", name="uq_trip_stop_trip_order"
            ),
        )
        op.create_index("ix_trip_stops_trip_id", "trip_stops", ["trip_id"])

        # Backfill from the legacy trip -> pickup_points links BEFORE the
        # legacy column is dropped.
        op.execute(
            """
            INSERT INTO trip_stops (trip_id, pickup_point_id, stop_order, departure_time)
            SELECT pp.trip_id, pp.id, pp.sequence, NULL
            FROM pickup_points pp
            WHERE pp.trip_id IS NOT NULL
            """
        )

    # ------------------------------------------------------------------
    # 3. pickup_points: re-scope to routes (one route per point)
    # ------------------------------------------------------------------
    if not _has_column(inspector, "pickup_points", "route_id"):
        op.add_column(
            "pickup_points",
            sa.Column("route_id", sa.Integer(), nullable=True),
        )
        op.create_foreign_key(
            "fk_pickup_points_route_id",
            "pickup_points",
            "routes",
            ["route_id"],
            ["id"],
            ondelete="CASCADE",
        )
        op.create_index(
            "ix_pickup_points_route_id", "pickup_points", ["route_id"]
        )

        # Backfill: each legacy trip-scoped point moves to its trip's route.
        # Duplicate (route, name) pairs keep the FIRST (lowest id) point; later
        # duplicates are deleted AFTER re-pointing trip stops that reference
        # them (see step 4), so no trip/reservation loses its reference.
        op.execute(
            """
            UPDATE pickup_points
            SET route_id = trips.route_id
            FROM trips
            WHERE pickup_points.trip_id = trips.id
              AND pickup_points.route_id IS NULL
            """
        )
        # Points without any owning trip (orphan rows from cancelled trips)
        # get a synthetic container route so they survive the NOT NULL switch.
        # Legacy routes carried strict NOT NULLs (route_number, station links,
        # distance/duration) that are dropped later in this revision, so the
        # synthetic row satisfies them inline. HAVING guards against the
        # aggregate-insert-creates-a-row-even-with-zero-orphans pitfall.
        op.execute(
            """
            INSERT INTO routes (
                name, route_number, origin_station_id, destination_station_id,
                distance_km, estimated_duration_minutes, is_active,
                created_at, updated_at
            )
            SELECT
                'Migrated legacy points',
                'MIG-' || COALESCE(MAX(pickup_points.route_id), 0) || '-' ||
                    COALESCE(MAX(pickup_points.id), 0),
                (SELECT MIN(id) FROM stations),
                (SELECT MIN(id) FROM stations),
                0.0,
                0,
                true,
                COALESCE(MIN(pickup_points.created_at), NOW()),
                NOW()
            FROM pickup_points
            WHERE pickup_points.route_id IS NULL
            HAVING COUNT(*) > 0
            """
        )
        op.execute(
            """
            UPDATE pickup_points
            SET route_id = (
                SELECT r.id FROM routes r
                WHERE r.name = 'Migrated legacy points'
                ORDER BY r.id ASC
                LIMIT 1
            )
            WHERE pickup_points.route_id IS NULL
            """
        )
        # De-duplicate (route_id, name): keep the lowest id per pair. History
        # is preserved by re-pointing trip_stops / boarding_records /
        # reservations/subscriptions legacy columns to the surviving point
        # BEFORE deleting the duplicates.
        repoint_tpl = """
            UPDATE {table}
            SET {col} = (
                SELECT keep.id FROM pickup_points keep
                WHERE keep.id = (
                    SELECT MIN(pp2.id) FROM pickup_points pp2
                    WHERE pp2.route_id = pp_old.route_id AND pp2.name = pp_old.name
                )
            )
            FROM pickup_points pp_old
            WHERE {table}.{col} = pp_old.id
              AND pp_old.id <> (
                  SELECT MIN(pp2.id) FROM pickup_points pp2
                  WHERE pp2.route_id = pp_old.route_id AND pp2.name = pp_old.name
              )
        """
        op.execute(repoint_tpl.format(table="trip_stops", col="pickup_point_id"))
        op.execute(repoint_tpl.format(table="boarding_records", col="pickup_point_id"))
        op.execute(
            repoint_tpl.format(table="reservations", col="outbound_pickup_point_id")
        )
        op.execute(
            repoint_tpl.format(table="reservations", col="return_pickup_point_id")
        )
        op.execute(
            repoint_tpl.format(
                table="subscriptions", col="outbound_pickup_point_id"
            )
        )
        op.execute(
            repoint_tpl.format(
                table="subscriptions", col="return_pickup_point_id"
            )
        )
        op.execute(
            """
            DELETE FROM pickup_points
            WHERE id NOT IN (
                SELECT MIN(id) FROM pickup_points GROUP BY route_id, name
            )
            """
        )
        op.alter_column(
            "pickup_points", "route_id", existing_type=sa.Integer(), nullable=False
        )
        op.create_unique_constraint(
            "uq_pickup_point_route_name", "pickup_points", ["route_id", "name"]
        )

    if _has_column(inspector, "pickup_points", "trip_id"):
        op.drop_column("pickup_points", "trip_id")

    # ------------------------------------------------------------------
    # 3b. routes: strip to a container of pickup points (safe now that no
    #     synthetic route rows are inserted anymore).
    # ------------------------------------------------------------------
    # Historical station/distance/duration/supervisor data is intentionally
    # dropped: the new Route model stores none of it and Trips already carry
    # their own derived departure/arrival times.
    if "supervisor_id" in route_cols:
        # Drop FK first when it exists (naming varies across revisions).
        for fk in inspector.get_foreign_keys("routes"):
            if fk.get("name"):
                op.drop_constraint(fk["name"], "routes", type_="foreignkey")
        op.drop_column("routes", "supervisor_id")
    for col in (
        "route_number",
        "origin_station_id",
        "destination_station_id",
        "distance_km",
        "estimated_duration_minutes",
    ):
        if col in route_cols:
            op.drop_column("routes", col)

    # CHECK constraints tied to dropped columns.
    for cname in (
        "chk_route_origin_dest_diff",
        "chk_route_distance_positive",
        "chk_route_duration_positive",
    ):
        if _has_check_constraint(inspector, "routes", cname):
            op.drop_constraint(cname, "routes", type_="check")

    # ------------------------------------------------------------------
    # 4. route_stops: dropped (pickup points are the route's stops now)
    # ------------------------------------------------------------------
    if _has_table(inspector, "route_stops"):
        op.drop_table("route_stops")

    # ------------------------------------------------------------------
    # 5. trips: direction + allow_overbooking; drop fare_amount
    # ------------------------------------------------------------------
    if not _has_column(inspector, "trips", "direction"):
        op.add_column(
            "trips",
            sa.Column(
                "direction",
                sa.String(20),
                nullable=True,
            ),
        )
        # Direction is derived from context: legacy trips predate the
        # direction concept and are preserved as OUTBOUND (documented
        # migration convention). Existing reservations/boarding data treat
        # them as the student's daily selections either way.
        op.execute("UPDATE trips SET direction = 'OUTBOUND' WHERE direction IS NULL")
        op.alter_column("trips", "direction", existing_type=sa.String(20), nullable=False)
        op.create_index("ix_trips_direction", "trips", ["direction"])
        op.create_check_constraint(
            "chk_trip_direction",
            "trips",
            "direction IN ('OUTBOUND', 'RETURN')",
        )

    if not _has_column(inspector, "trips", "allow_overbooking"):
        op.add_column(
            "trips",
            sa.Column(
                "allow_overbooking",
                sa.Boolean(),
                server_default=sa.text("false"),
                nullable=False,
            ),
        )

    if _has_column(inspector, "trips", "fare_amount"):
        op.drop_column("trips", "fare_amount")

    # Relax arrival strictly-after to arrival >= departure (single-stop trips
    # have equal first/last times).
    if _has_check_constraint(inspector, "trips", "chk_trip_arrival_after_departure"):
        op.drop_constraint(
            "chk_trip_arrival_after_departure", "trips", type_="check"
        )
    op.create_check_constraint(
        "chk_trip_arrival_after_departure",
        "trips",
        "estimated_arrival_time >= departure_time",
    )

    # ------------------------------------------------------------------
    # 6. reservations: one row per direction
    # ------------------------------------------------------------------
    if not _has_column(inspector, "reservations", "direction"):
        op.add_column(
            "reservations",
            sa.Column("direction", sa.String(20), nullable=True),
        )
        op.add_column(
            "reservations",
            sa.Column("selected_pickup_point_id", sa.Integer(), nullable=True),
        )

        # The legacy uniqueness model must be relaxed BEFORE the split:
        # splitting a BOTH-day row creates two CONFIRMED rows for the same
        # (trip_id, student_id), which the legacy per-trip index forbids.
        # Every trip now carries exactly one direction, so the new
        # per-date-per-direction index (created after the split) is the
        # correct uniqueness guarantee.
        if _has_index(inspector, "reservations", "uq_active_trip_student_reservation"):
            op.drop_index(
                "uq_active_trip_student_reservation", table_name="reservations"
            )
        if _has_index(inspector, "reservations", "uq_active_student_service_date_reservation"):
            op.drop_index(
                "uq_active_student_service_date_reservation", table_name="reservations"
            )

        # Backfill direction + selected point per legacy direction_mode:
        #   BOTH           -> split into TWO rows (outbound + return) so each
        #                     historical journey is queryable per direction.
        #   OUTBOUND_ONLY  -> one OUTBOUND row.
        #   RETURN_ONLY    -> one RETURN row.
        # Selected point falls back per direction; when the legacy row only
        # had the opposite direction's point, it is still used (the student's
        # actual point on that trip) because legacy trips served both roles.
        op.execute(
            """
            INSERT INTO reservations (
                trip_id, student_id, subscription_id, service_date, direction,
                selected_pickup_point_id, status, booked_at, cancelled_at,
                created_at, updated_at
            )
            SELECT trip_id, student_id, subscription_id, service_date, 'OUTBOUND',
                   COALESCE(outbound_pickup_point_id, return_pickup_point_id),
                   status, booked_at, cancelled_at, created_at, updated_at
            FROM reservations
            WHERE direction IS NULL
              AND direction_mode IN ('BOTH', 'OUTBOUND_ONLY')
            """
        )
        op.execute(
            """
            INSERT INTO reservations (
                trip_id, student_id, subscription_id, service_date, direction,
                selected_pickup_point_id, status, booked_at, cancelled_at,
                created_at, updated_at
            )
            SELECT trip_id, student_id, subscription_id, service_date, 'RETURN',
                   COALESCE(return_pickup_point_id, outbound_pickup_point_id),
                   status, booked_at, cancelled_at, created_at, updated_at
            FROM reservations
            WHERE direction IS NULL
              AND direction_mode IN ('BOTH', 'RETURN_ONLY')
            """
        )
        # The split INSERTs copied every legacy row into per-direction rows.
        # The originals (still carrying direction_mode, direction IS NULL) are
        # now redundant — keeping them would double-count bookings and violate
        # the new per-date-per-direction uniqueness. Delete them BEFORE the
        # catch-all backfills below (those set direction on remaining rows).
        # The per-direction copies preserve all historical attributes (status,
        # booked_at, points). Boarding records reference subscriptions, not
        # reservation rows, so no historical link is lost.
        op.execute(
            """
            DELETE FROM reservations
            WHERE direction IS NULL
            """
        )
        # Any remaining rows (legacy rows with no direction_mode value at all)
        # are backfilled from the trip's FIRST configured trip stop so no
        # historical row is lost.
        op.execute(
            """
            UPDATE reservations
            SET direction = COALESCE(direction, 'OUTBOUND'),
                selected_pickup_point_id = COALESCE(
                    selected_pickup_point_id,
                    (
                        SELECT ts.pickup_point_id FROM trip_stops ts
                        WHERE ts.trip_id = reservations.trip_id
                        ORDER BY ts.stop_order ASC, ts.id ASC
                        LIMIT 1
                    )
                )
            WHERE direction IS NULL OR selected_pickup_point_id IS NULL
            """
        )
        # Rows whose trip has NO configured stops at all (legacy data with no
        # pickup points): fall back to any point on the trip's route so the
        # historical booking still references a real, route-owned point.
        op.execute(
            """
            UPDATE reservations
            SET selected_pickup_point_id = COALESCE(
                    selected_pickup_point_id,
                    (
                        SELECT MIN(pp.id) FROM pickup_points pp
                        WHERE pp.route_id = (
                            SELECT t.route_id FROM trips t WHERE t.id = reservations.trip_id
                        )
                    )
                )
            WHERE selected_pickup_point_id IS NULL
            """
        )
        op.alter_column(
            "reservations", "direction", existing_type=sa.String(20), nullable=False
        )
        op.alter_column(
            "reservations",
            "selected_pickup_point_id",
            existing_type=sa.Integer(),
            nullable=False,
        )
        op.create_foreign_key(
            "fk_reservations_selected_pickup_point_id",
            "reservations",
            "pickup_points",
            ["selected_pickup_point_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        op.create_index(
            "ix_reservations_direction", "reservations", ["direction"]
        )
        op.create_check_constraint(
            "chk_reservation_direction",
            "reservations",
            "direction IN ('OUTBOUND', 'RETURN')",
        )

    # New uniqueness guarantee: one OUTBOUND + one RETURN per student per
    # service date (per-trip guard is obsolete — see the pre-split drop above).
    if not _has_index(inspector, "reservations", "uq_student_date_direction_reservation"):
        op.create_index(
            "uq_student_date_direction_reservation",
            "reservations",
            ["student_id", "service_date", "direction"],
            unique=True,
            postgresql_where=sa.text("status = 'CONFIRMED'"),
            sqlite_where=sa.text("status = 'CONFIRMED'"),
        )

    # Drop legacy direction columns/indexes.
    if _has_column(inspector, "reservations", "direction_mode"):
        if _has_check_constraint(inspector, "reservations", "chk_reservation_direction_mode"):
            op.drop_constraint(
                "chk_reservation_direction_mode", "reservations", type_="check"
            )
        op.drop_column("reservations", "direction_mode")
    for col, fk_name in (
        ("outbound_pickup_point_id", "fk_reservations_outbound_pickup_point_id"),
        ("return_pickup_point_id", "fk_reservations_return_pickup_point_id"),
    ):
        if _has_column(inspector, "reservations", col):
            if _has_foreign_key(inspector, "reservations", fk_name):
                op.drop_constraint(fk_name, "reservations", type_="foreignkey")
            op.drop_column("reservations", col)

    # ------------------------------------------------------------------
    # 6. payments: digital payment receipt image (private bucket object ref)
    # ------------------------------------------------------------------
    if not _has_column(inspector, "payments", "receipt_image_path"):
        op.add_column(
            "payments",
            sa.Column("receipt_image_path", sa.String(length=500), nullable=True),
        )


def downgrade() -> None:
    """Downgrade is best-effort: legacy columns are recreated NULL-able and
    historical per-direction rows that cannot be represented (a BOTH day) are
    collapsed by keeping the OUTBOUND row."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # reservations: restore legacy columns
    if not _has_column(inspector, "reservations", "direction_mode"):
        op.add_column(
            "reservations",
            sa.Column(
                "direction_mode",
                sa.String(20),
                server_default="BOTH",
                nullable=True,
            ),
        )
        op.execute(
            "UPDATE reservations SET direction_mode = 'BOTH' WHERE direction_mode IS NULL"
        )
        op.alter_column(
            "reservations", "direction_mode", existing_type=sa.String(20), nullable=False
        )
        op.create_check_constraint(
            "chk_reservation_direction_mode",
            "reservations",
            "direction_mode IN ('BOTH', 'OUTBOUND_ONLY', 'RETURN_ONLY')",
        )
    if not _has_column(inspector, "reservations", "outbound_pickup_point_id"):
        op.add_column(
            "reservations",
            sa.Column("outbound_pickup_point_id", sa.Integer(), nullable=True),
        )
        op.add_column(
            "reservations",
            sa.Column("return_pickup_point_id", sa.Integer(), nullable=True),
        )
        op.execute(
            """
            UPDATE reservations
            SET outbound_pickup_point_id = CASE WHEN direction = 'OUTBOUND'
                    THEN selected_pickup_point_id ELSE NULL END,
                return_pickup_point_id = CASE WHEN direction = 'RETURN'
                    THEN selected_pickup_point_id ELSE NULL END
            """
        )
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

    if _has_index(inspector, "reservations", "uq_student_date_direction_reservation"):
        op.drop_index(
            "uq_student_date_direction_reservation", table_name="reservations"
        )

    # Collapse per-direction rows that the legacy model cannot represent: for
    # a student/date with both an OUTBOUND and a RETURN row on the SAME trip,
    # keep the OUTBOUND row (merged points) so the legacy per-date and per-trip
    # unique indexes can be recreated without data loss of the primary row.
    op.execute(
        """
        UPDATE reservations r
        SET outbound_pickup_point_id = COALESCE(
                r.outbound_pickup_point_id,
                (SELECT ret.selected_pickup_point_id FROM reservations ret
                 WHERE ret.student_id = r.student_id
                   AND ret.service_date = r.service_date
                   AND ret.direction = 'RETURN'
                 ORDER BY ret.id ASC LIMIT 1)
            )
        WHERE r.direction = 'OUTBOUND'
          AND EXISTS (
              SELECT 1 FROM reservations ret
              WHERE ret.student_id = r.student_id
                AND ret.service_date = r.service_date
                AND ret.direction = 'RETURN'
          )
        """
    )
    op.execute(
        """
        DELETE FROM reservations
        WHERE direction = 'RETURN'
          AND EXISTS (
              SELECT 1 FROM reservations ob
              WHERE ob.student_id = reservations.student_id
                AND ob.service_date = reservations.service_date
                AND ob.direction = 'OUTBOUND'
          )
        """
    )
    if not _has_index(inspector, "reservations", "uq_active_student_service_date_reservation"):
        op.create_index(
            "uq_active_student_service_date_reservation",
            "reservations",
            ["student_id", "service_date"],
            unique=True,
            postgresql_where=sa.text("status = 'CONFIRMED'"),
            sqlite_where=sa.text("status = 'CONFIRMED'"),
        )
    # Legacy per-trip guard restored; BOTH-day splits are collapsed first by
    # the direction_mode restore above, so the index can be recreated safely.
    if not _has_index(inspector, "reservations", "uq_active_trip_student_reservation"):
        op.create_index(
            "uq_active_trip_student_reservation",
            "reservations",
            ["trip_id", "student_id"],
            unique=True,
            postgresql_where=sa.text("status = 'CONFIRMED'"),
            sqlite_where=sa.text("status = 'CONFIRMED'"),
        )
    if _has_column(inspector, "reservations", "direction"):
        if _has_index(inspector, "reservations", "ix_reservations_direction"):
            op.drop_index("ix_reservations_direction", table_name="reservations")
        if _has_check_constraint(inspector, "reservations", "chk_reservation_direction"):
            op.drop_constraint(
                "chk_reservation_direction", "reservations", type_="check"
            )
        if _has_foreign_key(inspector, "reservations", "fk_reservations_selected_pickup_point_id"):
            op.drop_constraint(
                "fk_reservations_selected_pickup_point_id",
                "reservations",
                type_="foreignkey",
            )
        op.drop_column("reservations", "selected_pickup_point_id")
        op.drop_column("reservations", "direction")

    # trips: restore fare_amount and strict arrival constraint
    if not _has_column(inspector, "trips", "fare_amount"):
        op.add_column(
            "trips",
            sa.Column(
                "fare_amount",
                sa.Numeric(10, 2),
                server_default="50.00",
                nullable=False,
            ),
        )
    if _has_check_constraint(inspector, "trips", "chk_trip_arrival_after_departure"):
        op.drop_constraint(
            "chk_trip_arrival_after_departure", "trips", type_="check"
        )
    op.create_check_constraint(
        "chk_trip_arrival_after_departure",
        "trips",
        "estimated_arrival_time > departure_time",
    )
    if _has_column(inspector, "trips", "allow_overbooking"):
        op.drop_column("trips", "allow_overbooking")
    if _has_column(inspector, "trips", "direction"):
        if _has_index(inspector, "trips", "ix_trips_direction"):
            op.drop_index("ix_trips_direction", table_name="trips")
        if _has_check_constraint(inspector, "trips", "chk_trip_direction"):
            op.drop_constraint("chk_trip_direction", "trips", type_="check")
        op.drop_column("trips", "direction")

    # pickup_points: restore trip scoping (points map back to one trip each
    # via trip_stops) — must run BEFORE trip_stops is dropped below.
    if not _has_column(inspector, "pickup_points", "trip_id"):
        op.add_column(
            "pickup_points",
            sa.Column("trip_id", sa.Integer(), nullable=True),
        )
        op.create_foreign_key(
            "fk_pickup_points_trip_id",
            "pickup_points",
            "trips",
            ["trip_id"],
            ["id"],
            ondelete="CASCADE",
        )
        op.execute(
            """
            UPDATE pickup_points
            SET trip_id = (
                SELECT ts.trip_id FROM trip_stops ts
                WHERE ts.pickup_point_id = pickup_points.id
                ORDER BY ts.id ASC LIMIT 1
            )
            """
        )

    # trip_stops: dropped on downgrade
    if _has_table(inspector, "trip_stops"):
        op.drop_table("trip_stops")

    # route_stops: recreated empty (historical stop data is not reconstructible)
    if not _has_table(inspector, "route_stops"):
        op.create_table(
            "route_stops",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column(
                "route_id",
                sa.Integer(),
                sa.ForeignKey("routes.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "station_id",
                sa.Integer(),
                sa.ForeignKey("stations.id", ondelete="RESTRICT"),
                nullable=False,
            ),
            sa.Column("stop_order", sa.Integer(), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.UniqueConstraint(
                "route_id", "station_id", name="uq_route_stop_route_station"
            ),
            sa.UniqueConstraint(
                "route_id", "stop_order", name="uq_route_stop_route_order"
            ),
            sa.CheckConstraint(
                "stop_order > 0", name="chk_route_stop_order_positive"
            ),
        )

        op.drop_column("pickup_points", "route_id")

    # routes: legacy columns restored NULL-able without data recovery
    if not _has_column(inspector, "routes", "route_number"):
        op.add_column(
            "routes", sa.Column("route_number", sa.String(50), nullable=True)
        )
        op.execute("UPDATE routes SET route_number = 'R-MIGRATED-' || id")
        op.create_unique_constraint(
            "uq_routes_route_number", "routes", ["route_number"]
        )
    for col, coltype in (
        ("origin_station_id", sa.Integer()),
        ("destination_station_id", sa.Integer()),
    ):
        if not _has_column(inspector, "routes", col):
            op.add_column("routes", sa.Column(col, coltype, nullable=True))
    if not _has_column(inspector, "routes", "distance_km"):
        op.add_column(
            "routes", sa.Column("distance_km", sa.Float(), nullable=True)
        )
    if not _has_column(inspector, "routes", "estimated_duration_minutes"):
        op.add_column(
            "routes",
            sa.Column("estimated_duration_minutes", sa.Integer(), nullable=True),
        )
    if not _has_column(inspector, "routes", "supervisor_id"):
        op.add_column(
            "routes",
            sa.Column(
                "supervisor_id",
                sa.Integer(),
                sa.ForeignKey("users.id", ondelete="RESTRICT"),
                nullable=True,
            ),
        )
    if not _has_column(inspector, "payments", "receipt_image_path"):
        op.drop_column("payments", "receipt_image_path")
