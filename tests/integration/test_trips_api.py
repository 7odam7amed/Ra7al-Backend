from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient
import pytest
from sqlalchemy.orm import Session
from uuid import uuid4

from app.core.security import create_access_token, hash_password
from app.models.bus import Bus
from app.models.enums import BusStatus, GenderEnum, RoleEnum, TripDirection
from app.models.pickup_point import PickupPoint
from app.models.route import Route
from app.models.trip_stop import TripStop
from app.models.user import User


def _create_user_and_token(
    session: Session,
    identifier: str,
    role: RoleEnum,
    is_active: bool = True,
) -> tuple[User, str]:
    phone_digits = f"{abs(hash(identifier)) % 100000000:08d}"
    phone_number = f"+2010{phone_digits}"
    user = User(
        full_name=f"{role.value} User",
        phone_number=phone_number,
        password_hash=hash_password("Password123!"),
        gender=GenderEnum.MALE,
        role=role,
        is_active=is_active,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    token = create_access_token(subject=user.id, role=user.role.value)
    return user, token


def _setup_api_prerequisites(
    session: Session, with_points: bool = True
) -> tuple[Route, Bus, User]:
    suffix = uuid4().hex[:8]
    route = Route(name=f"Route API {suffix}", is_active=True)
    bus = Bus(
        bus_number=f"BUS-API-{suffix}",
        license_plate=f"API-{suffix}",
        capacity=50,
        status=BusStatus.ACTIVE,
    )
    supervisor = User(
        full_name="Supervisor API",
        phone_number=f"+2010{int(suffix, 16) % 100000000:08d}",
        password_hash=hash_password("Password123!"),
        gender=GenderEnum.MALE,
        role=RoleEnum.SUPERVISOR,
        is_active=True,
    )
    session.add_all([route, bus, supervisor])
    session.commit()

    if with_points:
        p1 = PickupPoint(route_id=route.id, name="Point API 1", sequence=1)
        p2 = PickupPoint(route_id=route.id, name="Point API 2", sequence=2)
        session.add_all([p1, p2])
        session.commit()
    return route, bus, supervisor


def _trip_payload(
    route: Route,
    bus: Bus,
    supervisor: User,
    start_hour: int = 10,
    end_hour: int = 12,
    direction: TripDirection = TripDirection.OUTBOUND,
) -> dict:
    """Stops reference the route's own points; times derive departure/arrival."""
    day = datetime(2026, 8, 20, tzinfo=timezone.utc)
    points = sorted(route.pickup_points, key=lambda p: p.sequence) or []
    assert len(points) >= 2, "prerequisite route needs two pickup points"
    return {
        "route_id": route.id,
        "direction": direction.value,
        "bus_id": bus.id,
        "supervisor_id": supervisor.id,
        "stops": [
            {
                "pickup_point_id": points[0].id,
                "stop_order": 1,
                "departure_time": day.replace(hour=start_hour).isoformat(),
            },
            {
                "pickup_point_id": points[1].id,
                "stop_order": 2,
                "departure_time": day.replace(hour=end_hour).isoformat(),
            },
        ],
    }


def test_unauthenticated_requests_rejected(client_with_db: TestClient) -> None:
    assert client_with_db.post("/api/v1/trips", json={}).status_code == 401
    assert client_with_db.get("/api/v1/trips").status_code == 401
    assert client_with_db.get("/api/v1/trips/1").status_code == 401
    assert client_with_db.patch("/api/v1/trips/1", json={}).status_code == 401
    assert client_with_db.patch("/api/v1/trips/1/status", json={}).status_code == 401
    assert client_with_db.delete("/api/v1/trips/1").status_code == 401


def test_rbac_access_control(
    client_with_db: TestClient, db_session: Session
) -> None:
    route, bus, supervisor = _setup_api_prerequisites(db_session)
    _, ceo_token = _create_user_and_token(db_session, "ceo_trip@test.edu", RoleEnum.CEO)
    _, sup_token = _create_user_and_token(
        db_session, "sup_trip@test.edu", RoleEnum.SUPERVISOR
    )
    _, std_token = _create_user_and_token(
        db_session, "std_trip@test.edu", RoleEnum.STUDENT
    )

    payload = _trip_payload(route, bus, supervisor)

    # Student forbidden from creating trip (403)
    res_std = client_with_db.post(
        "/api/v1/trips",
        json=payload,
        headers={"Authorization": f"Bearer {std_token}"},
    )
    assert res_std.status_code == 403

    # Supervisor forbidden from creating trip (403 - CEO only)
    res_sup = client_with_db.post(
        "/api/v1/trips",
        json=payload,
        headers={"Authorization": f"Bearer {sup_token}"},
    )
    assert res_sup.status_code == 403

    # CEO allowed to create trip (201)
    res_ceo = client_with_db.post(
        "/api/v1/trips",
        json=payload,
        headers={"Authorization": f"Bearer {ceo_token}"},
    )
    assert res_ceo.status_code == 201
    data = res_ceo.json()
    assert data["direction"] == "OUTBOUND"
    # Derived times: first stop = departure, last stop = arrival.
    assert data["departure_time"].startswith("2026-08-20T10:00")
    assert data["estimated_arrival_time"].startswith("2026-08-20T12:00")
    # No fare exists on trips.
    assert "fare_amount" not in data

    # Supervisor allowed to list trips (200)
    res_sup_list = client_with_db.get(
        "/api/v1/trips",
        headers={"Authorization": f"Bearer {sup_token}"},
    )
    assert res_sup_list.status_code == 200


def test_create_trip_validations(
    client_with_db: TestClient, db_session: Session
) -> None:
    route, bus, supervisor = _setup_api_prerequisites(db_session)
    _, ceo_token = _create_user_and_token(db_session, "ceo_val@test.edu", RoleEnum.CEO)
    headers = {"Authorization": f"Bearer {ceo_token}"}

    # 1. Nonexistent route -> 404
    foreign_route_payload = _trip_payload(route, bus, supervisor)
    foreign_route_payload["route_id"] = 999999
    res1 = client_with_db.post("/api/v1/trips", json=foreign_route_payload, headers=headers)
    assert res1.status_code == 404

    # 2. Inactive route -> 422
    route.is_active = False
    db_session.commit()
    res2 = client_with_db.post(
        "/api/v1/trips", json=_trip_payload(route, bus, supervisor), headers=headers
    )
    assert res2.status_code == 422
    route.is_active = True
    db_session.commit()

    # 3. Nonexistent bus -> 404
    payload = _trip_payload(route, bus, supervisor)
    payload["bus_id"] = 999999
    res3 = client_with_db.post("/api/v1/trips", json=payload, headers=headers)
    assert res3.status_code == 404

    # 4. Inactive bus -> 422
    bus.status = BusStatus.INACTIVE
    db_session.commit()
    res4 = client_with_db.post(
        "/api/v1/trips", json=_trip_payload(route, bus, supervisor), headers=headers
    )
    assert res4.status_code == 422
    bus.status = BusStatus.ACTIVE
    db_session.commit()

    # 5. Nonexistent supervisor -> 404
    payload = _trip_payload(route, bus, supervisor)
    payload["supervisor_id"] = 999999
    res5 = client_with_db.post("/api/v1/trips", json=payload, headers=headers)
    assert res5.status_code == 404

    # 6. Student as supervisor -> 422
    student, _ = _create_user_and_token(
        db_session, "student_as_sup@test.edu", RoleEnum.STUDENT
    )
    payload = _trip_payload(route, bus, supervisor)
    payload["supervisor_id"] = student.id
    res6 = client_with_db.post("/api/v1/trips", json=payload, headers=headers)
    assert res6.status_code == 422

    # 7. Inactive supervisor -> 422
    inactive_sup, _ = _create_user_and_token(
        db_session, "inact_sup@test.edu", RoleEnum.SUPERVISOR, is_active=False
    )
    payload = _trip_payload(route, bus, supervisor)
    payload["supervisor_id"] = inactive_sup.id
    res_inact_sup = client_with_db.post("/api/v1/trips", json=payload, headers=headers)
    assert res_inact_sup.status_code == 422

    # 8. Stop from another route -> 422
    other_route, other_bus, other_sup = _setup_api_prerequisites(db_session)
    foreign_point = db_session.query(PickupPoint).filter(
        PickupPoint.route_id == other_route.id
    ).first()
    payload = _trip_payload(route, bus, supervisor)
    payload["stops"][0]["pickup_point_id"] = foreign_point.id
    res_foreign = client_with_db.post("/api/v1/trips", json=payload, headers=headers)
    assert res_foreign.status_code == 422
    assert "does not belong to route" in res_foreign.json()["detail"]

    # 9. Duplicate stop order -> 422
    payload = _trip_payload(route, bus, supervisor)
    payload["stops"][1]["stop_order"] = 1
    res_dup_order = client_with_db.post("/api/v1/trips", json=payload, headers=headers)
    assert res_dup_order.status_code == 422

    # 10. Missing direction -> 422
    payload = _trip_payload(route, bus, supervisor)
    payload.pop("direction")
    res_no_dir = client_with_db.post("/api/v1/trips", json=payload, headers=headers)
    assert res_no_dir.status_code == 422


def test_bus_and_supervisor_conflicts_via_api(
    client_with_db: TestClient, db_session: Session
) -> None:
    route, bus, supervisor = _setup_api_prerequisites(db_session)
    _, ceo_token = _create_user_and_token(
        db_session, "ceo_conf@test.edu", RoleEnum.CEO
    )
    headers = {"Authorization": f"Bearer {ceo_token}"}

    # Initial Trip: 10:00 -> 12:00 (via stop times)
    res_init = client_with_db.post(
        "/api/v1/trips",
        json=_trip_payload(route, bus, supervisor, start_hour=10, end_hour=12),
        headers=headers,
    )
    assert res_init.status_code == 201

    # Overlapping Bus Trip: 11:00 -> 13:00 -> 409 Conflict
    supervisor2, _ = _create_user_and_token(
        db_session, "supervisor2_api@test.edu", RoleEnum.SUPERVISOR
    )
    res_bus_conf = client_with_db.post(
        "/api/v1/trips",
        json=_trip_payload(route, bus, supervisor2, start_hour=11, end_hour=13),
        headers=headers,
    )
    assert res_bus_conf.status_code == 409

    # Overlapping Supervisor Trip: 09:00 -> 11:00 -> 409 Conflict
    bus2 = Bus(
        bus_number="BUS-API-2",
        license_plate="API-002",
        capacity=40,
        status=BusStatus.ACTIVE,
    )
    db_session.add(bus2)
    db_session.commit()

    res_sup_conf = client_with_db.post(
        "/api/v1/trips",
        json=_trip_payload(
            route, bus2, supervisor, start_hour=9, end_hour=11
        ),
        headers=headers,
    )
    assert res_sup_conf.status_code == 409

    # Adjacent Trip: 12:00 -> 14:00 -> 201 Created (No conflict)
    res_adj = client_with_db.post(
        "/api/v1/trips",
        json=_trip_payload(
            route, bus, supervisor, start_hour=12, end_hour=14
        ),
        headers=headers,
    )
    assert res_adj.status_code == 201


def test_trip_crud_and_status_lifecycle_via_api(
    client_with_db: TestClient, db_session: Session
) -> None:
    route, bus, supervisor = _setup_api_prerequisites(db_session)
    _, ceo_token = _create_user_and_token(
        db_session, "ceo_crud@test.edu", RoleEnum.CEO
    )
    _, sup_token = _create_user_and_token(
        db_session, "sup_crud@test.edu", RoleEnum.SUPERVISOR
    )
    headers = {"Authorization": f"Bearer {ceo_token}"}

    # 1. Create Trip (capacity + allow_overbooking per spec §12)
    res_create = client_with_db.post(
        "/api/v1/trips",
        json={
            **_trip_payload(route, bus, supervisor, start_hour=10, end_hour=12),
            "passenger_capacity": 45,
            "allow_overbooking": True,
        },
        headers=headers,
    )
    assert res_create.status_code == 201
    trip_id = res_create.json()["id"]
    assert len(res_create.json()["trip_stops"]) == 2
    assert res_create.json()["allow_overbooking"] is True
    assert [s["stop_order"] for s in res_create.json()["trip_stops"]] == [1, 2]
    assert all(s["departure_time"] for s in res_create.json()["trip_stops"])

    # 2. Get Trip Details (Supervisor can view)
    res_get = client_with_db.get(
        f"/api/v1/trips/{trip_id}",
        headers={"Authorization": f"Bearer {sup_token}"},
    )
    assert res_get.status_code == 200
    data = res_get.json()
    assert data["id"] == trip_id
    assert data["route"]["id"] == route.id
    assert data["bus"]["id"] == bus.id
    assert data["supervisor"]["id"] == supervisor.id
    assert "password_hash" not in data["supervisor"]
    assert len(data["trip_stops"]) == 2

    # 3. List Trips
    res_list = client_with_db.get(
        f"/api/v1/trips?status=SCHEDULED&route_id={route.id}", headers=headers
    )
    assert res_list.status_code == 200
    list_data = res_list.json()
    assert list_data["total"] >= 1
    assert len(list_data["items"]) >= 1

    # 4. Patch Trip (Update capacity + overbooking)
    res_patch = client_with_db.patch(
        f"/api/v1/trips/{trip_id}",
        json={"passenger_capacity": 38, "allow_overbooking": False},
        headers=headers,
    )
    assert res_patch.status_code == 200
    assert res_patch.json()["passenger_capacity"] == 38
    assert res_patch.json()["allow_overbooking"] is False

    # 5. Status Transitions: SCHEDULED -> IN_PROGRESS -> COMPLETED
    res_prog = client_with_db.patch(
        f"/api/v1/trips/{trip_id}/status",
        json={"status": "IN_PROGRESS"},
        headers=headers,
    )
    assert res_prog.status_code == 200
    assert res_prog.json()["status"] == "IN_PROGRESS"

    res_comp = client_with_db.patch(
        f"/api/v1/trips/{trip_id}/status",
        json={"status": "COMPLETED"},
        headers=headers,
    )
    assert res_comp.status_code == 200
    assert res_comp.json()["status"] == "COMPLETED"

    # Invalid transition: COMPLETED -> SCHEDULED -> 422
    res_inv = client_with_db.patch(
        f"/api/v1/trips/{trip_id}/status",
        json={"status": "SCHEDULED"},
        headers=headers,
    )
    assert res_inv.status_code == 422

    # 6. Get Deleted Trip -> 404 (trips remain; only CEO hard-delete here)
    res_del = client_with_db.delete(f"/api/v1/trips/{trip_id}", headers=headers)
    assert res_del.status_code == 204
    res_after_del = client_with_db.get(
        f"/api/v1/trips/{trip_id}", headers=headers
    )
    assert res_after_del.status_code == 404


def test_route_points_endpoint(
    client_with_db: TestClient, db_session: Session
) -> None:
    """CEO retrieves a route's registered points before creating a trip."""
    route, _bus, _supervisor = _setup_api_prerequisites(db_session)
    _, ceo_token = _create_user_and_token(
        db_session, "ceo_pts@test.edu", RoleEnum.CEO
    )
    headers = {"Authorization": f"Bearer {ceo_token}"}

    res_points = client_with_db.get(
        f"/api/v1/routes/{route.id}/pickup-points", headers=headers
    )
    assert res_points.status_code == 200
    points = res_points.json()
    assert len(points) == 2
    assert [p["sequence"] for p in points] == [1, 2]
