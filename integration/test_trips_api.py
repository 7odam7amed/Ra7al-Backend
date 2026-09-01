from datetime import datetime, timezone
from decimal import Decimal
from fastapi.testclient import TestClient
import pytest
from sqlalchemy.orm import Session

from app.core.security import create_access_token, hash_password
from app.models.bus import Bus
from app.models.enums import BusStatus, GenderEnum, RoleEnum, TripStatus
from app.models.route import Route
from app.models.station import Station
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
    session: Session,
) -> tuple[Route, Bus, User]:
    s1 = Station(name="Origin API", code="ST-OR-API", latitude=30.0, longitude=31.0)
    s2 = Station(name="Dest API", code="ST-DE-API", latitude=30.1, longitude=31.1)
    session.add_all([s1, s2])
    session.commit()

    route = Route(
        route_number="R-API-01",
        name="Route API",
        origin_station_id=s1.id,
        destination_station_id=s2.id,
        distance_km=18.0,
        estimated_duration_minutes=35,
        is_active=True,
    )
    bus = Bus(
        bus_number="BUS-API-1",
        license_plate="API-001",
        capacity=50,
        status=BusStatus.ACTIVE,
    )
    supervisor = User(
        full_name="Supervisor API",
        phone_number="+201000000001",
        password_hash=hash_password("Password123!"),
        gender=GenderEnum.MALE,
        role=RoleEnum.SUPERVISOR,
        is_active=True,
    )
    session.add_all([route, bus, supervisor])
    session.commit()
    return route, bus, supervisor


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

    t_dep = datetime(2026, 8, 20, 10, 0, tzinfo=timezone.utc).isoformat()
    t_arr = datetime(2026, 8, 20, 11, 0, tzinfo=timezone.utc).isoformat()
    payload = {
        "route_id": route.id,
        "bus_id": bus.id,
        "supervisor_id": supervisor.id,
        "departure_time": t_dep,
        "estimated_arrival_time": t_arr,
    }

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

    t_dep = datetime(2026, 8, 20, 10, 0, tzinfo=timezone.utc).isoformat()
    t_arr = datetime(2026, 8, 20, 11, 0, tzinfo=timezone.utc).isoformat()

    # 1. Nonexistent route -> 404
    res1 = client_with_db.post(
        "/api/v1/trips",
        json={
            "route_id": 999999,
            "bus_id": bus.id,
            "supervisor_id": supervisor.id,
            "departure_time": t_dep,
            "estimated_arrival_time": t_arr,
        },
        headers=headers,
    )
    assert res1.status_code == 404

    # 2. Inactive route -> 422
    route.is_active = False
    db_session.commit()
    res2 = client_with_db.post(
        "/api/v1/trips",
        json={
            "route_id": route.id,
            "bus_id": bus.id,
            "supervisor_id": supervisor.id,
            "departure_time": t_dep,
            "estimated_arrival_time": t_arr,
        },
        headers=headers,
    )
    assert res2.status_code == 422
    route.is_active = True
    db_session.commit()

    # 3. Nonexistent bus -> 404
    res3 = client_with_db.post(
        "/api/v1/trips",
        json={
            "route_id": route.id,
            "bus_id": 999999,
            "supervisor_id": supervisor.id,
            "departure_time": t_dep,
            "estimated_arrival_time": t_arr,
        },
        headers=headers,
    )
    assert res3.status_code == 404

    # 4. Inactive bus -> 422
    bus.status = BusStatus.INACTIVE
    db_session.commit()
    res4 = client_with_db.post(
        "/api/v1/trips",
        json={
            "route_id": route.id,
            "bus_id": bus.id,
            "supervisor_id": supervisor.id,
            "departure_time": t_dep,
            "estimated_arrival_time": t_arr,
        },
        headers=headers,
    )
    assert res4.status_code == 422
    bus.status = BusStatus.ACTIVE
    db_session.commit()

    # 5. Nonexistent supervisor -> 404
    res5 = client_with_db.post(
        "/api/v1/trips",
        json={
            "route_id": route.id,
            "bus_id": bus.id,
            "supervisor_id": 999999,
            "departure_time": t_dep,
            "estimated_arrival_time": t_arr,
        },
        headers=headers,
    )
    assert res5.status_code == 404

    # 6. Student as supervisor -> 422
    student, _ = _create_user_and_token(
        db_session, "student_as_sup@test.edu", RoleEnum.STUDENT
    )
    res6 = client_with_db.post(
        "/api/v1/trips",
        json={
            "route_id": route.id,
            "bus_id": bus.id,
            "supervisor_id": student.id,
            "departure_time": t_dep,
            "estimated_arrival_time": t_arr,
        },
        headers=headers,
    )
    assert res6.status_code == 422

    # 7. Inactive supervisor -> 422
    inactive_sup, _ = _create_user_and_token(
        db_session, "inact_sup@test.edu", RoleEnum.SUPERVISOR, is_active=False
    )
    res_inact_sup = client_with_db.post(
        "/api/v1/trips",
        json={
            "route_id": route.id,
            "bus_id": bus.id,
            "supervisor_id": inactive_sup.id,
            "departure_time": t_dep,
            "estimated_arrival_time": t_arr,
        },
        headers=headers,
    )
    assert res_inact_sup.status_code == 422

    # 8. arrival <= departure -> 422
    res7 = client_with_db.post(
        "/api/v1/trips",
        json={
            "route_id": route.id,
            "bus_id": bus.id,
            "supervisor_id": supervisor.id,
            "departure_time": t_arr,
            "estimated_arrival_time": t_dep,
        },
        headers=headers,
    )
    assert res7.status_code == 422


def test_bus_and_supervisor_conflicts_via_api(
    client_with_db: TestClient, db_session: Session
) -> None:
    route, bus, supervisor = _setup_api_prerequisites(db_session)
    _, ceo_token = _create_user_and_token(
        db_session, "ceo_conf@test.edu", RoleEnum.CEO
    )
    headers = {"Authorization": f"Bearer {ceo_token}"}

    # Initial Trip: 10:00 -> 12:00
    t1_dep = datetime(2026, 8, 20, 10, 0, tzinfo=timezone.utc).isoformat()
    t1_arr = datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc).isoformat()

    res_init = client_with_db.post(
        "/api/v1/trips",
        json={
            "route_id": route.id,
            "bus_id": bus.id,
            "supervisor_id": supervisor.id,
            "departure_time": t1_dep,
            "estimated_arrival_time": t1_arr,
        },
        headers=headers,
    )
    assert res_init.status_code == 201

    # Overlapping Bus Trip: 11:00 -> 13:00 -> 409 Conflict
    supervisor2, _ = _create_user_and_token(
        db_session, "supervisor2_api@test.edu", RoleEnum.SUPERVISOR
    )
    res_bus_conf = client_with_db.post(
        "/api/v1/trips",
        json={
            "route_id": route.id,
            "bus_id": bus.id,
            "supervisor_id": supervisor2.id,
            "departure_time": datetime(
                2026, 8, 20, 11, 0, tzinfo=timezone.utc
            ).isoformat(),
            "estimated_arrival_time": datetime(
                2026, 8, 20, 13, 0, tzinfo=timezone.utc
            ).isoformat(),
        },
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
        json={
            "route_id": route.id,
            "bus_id": bus2.id,
            "supervisor_id": supervisor.id,
            "departure_time": datetime(
                2026, 8, 20, 9, 0, tzinfo=timezone.utc
            ).isoformat(),
            "estimated_arrival_time": datetime(
                2026, 8, 20, 11, 0, tzinfo=timezone.utc
            ).isoformat(),
        },
        headers=headers,
    )
    assert res_sup_conf.status_code == 409

    # Adjacent Trip: 12:00 -> 14:00 -> 201 Created (No conflict)
    res_adj = client_with_db.post(
        "/api/v1/trips",
        json={
            "route_id": route.id,
            "bus_id": bus.id,
            "supervisor_id": supervisor.id,
            "departure_time": datetime(
                2026, 8, 20, 12, 0, tzinfo=timezone.utc
            ).isoformat(),
            "estimated_arrival_time": datetime(
                2026, 8, 20, 14, 0, tzinfo=timezone.utc
            ).isoformat(),
        },
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

    t_dep = datetime(2026, 8, 20, 10, 0, tzinfo=timezone.utc).isoformat()
    t_arr = datetime(2026, 8, 20, 11, 0, tzinfo=timezone.utc).isoformat()

    # 1. Create Trip
    res_create = client_with_db.post(
        "/api/v1/trips",
        json={
            "route_id": route.id,
            "bus_id": bus.id,
            "supervisor_id": supervisor.id,
            "departure_time": t_dep,
            "estimated_arrival_time": t_arr,
            "passenger_capacity": 45,
            "fare_amount": 60.0,
            "pickup_points": [
                {"name": "Pickup 1", "address": "Station 1", "sequence": 1},
                {"name": "Pickup 2", "address": "Station 2", "sequence": 2},
            ],
        },
        headers=headers,
    )
    assert res_create.status_code == 201
    trip_id = res_create.json()["id"]
    assert len(res_create.json()["pickup_points"]) == 2

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
    assert len(data["pickup_points"]) == 2

    # 3. List Trips
    res_list = client_with_db.get(
        f"/api/v1/trips?status=SCHEDULED&route_id={route.id}", headers=headers
    )
    assert res_list.status_code == 200
    list_data = res_list.json()
    assert list_data["total"] >= 1
    assert len(list_data["items"]) >= 1

    # 4. Patch Trip (Update capacity)
    res_patch = client_with_db.patch(
        f"/api/v1/trips/{trip_id}",
        json={"passenger_capacity": 38},
        headers=headers,
    )
    assert res_patch.status_code == 200
    assert res_patch.json()["passenger_capacity"] == 38

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

    # 6. Delete Trip
    res_del = client_with_db.delete(f"/api/v1/trips/{trip_id}", headers=headers)
    assert res_del.status_code == 204

    # 7. Get Deleted Trip -> 404
    res_after_del = client_with_db.get(
        f"/api/v1/trips/{trip_id}", headers=headers
    )
    assert res_after_del.status_code == 404


def test_pickup_points_sub_routes(
    client_with_db: TestClient, db_session: Session
) -> None:
    route, bus, supervisor = _setup_api_prerequisites(db_session)
    _, ceo_token = _create_user_and_token(
        db_session, "ceo_pts@test.edu", RoleEnum.CEO
    )
    _, sup_token = _create_user_and_token(
        db_session, "sup_pts@test.edu", RoleEnum.SUPERVISOR
    )
    headers_ceo = {"Authorization": f"Bearer {ceo_token}"}
    headers_sup = {"Authorization": f"Bearer {sup_token}"}

    t_dep = datetime(2026, 8, 20, 10, 0, tzinfo=timezone.utc).isoformat()
    t_arr = datetime(2026, 8, 20, 11, 0, tzinfo=timezone.utc).isoformat()

    # Create Trip
    res_create = client_with_db.post(
        "/api/v1/trips",
        json={
            "route_id": route.id,
            "bus_id": bus.id,
            "supervisor_id": supervisor.id,
            "departure_time": t_dep,
            "estimated_arrival_time": t_arr,
        },
        headers=headers_ceo,
    )
    trip_id = res_create.json()["id"]

    # 1. Add pickup point (CEO only)
    res_pt1 = client_with_db.post(
        f"/api/v1/trips/{trip_id}/pickup-points",
        json={"name": "Gathering Spot A", "address": "Main St 10", "sequence": 1},
        headers=headers_ceo,
    )
    assert res_pt1.status_code == 201
    pt1_id = res_pt1.json()["id"]
    assert res_pt1.json()["name"] == "Gathering Spot A"
    assert res_pt1.json()["sequence"] == 1

    # Supervisor forbidden to add pickup point (403)
    res_sup_add = client_with_db.post(
        f"/api/v1/trips/{trip_id}/pickup-points",
        json={"name": "Gathering Spot B", "sequence": 2},
        headers=headers_sup,
    )
    assert res_sup_add.status_code == 403

    # Add second pickup point
    res_pt2 = client_with_db.post(
        f"/api/v1/trips/{trip_id}/pickup-points",
        json={"name": "Gathering Spot B", "address": "Campus Gate", "sequence": 2},
        headers=headers_ceo,
    )
    assert res_pt2.status_code == 201
    pt2_id = res_pt2.json()["id"]

    # 2. List pickup points (Supervisor & CEO can view)
    res_list = client_with_db.get(
        f"/api/v1/trips/{trip_id}/pickup-points",
        headers=headers_sup,
    )
    assert res_list.status_code == 200
    points = res_list.json()
    assert len(points) == 2
    assert points[0]["sequence"] == 1
    assert points[1]["sequence"] == 2

    # 3. Patch pickup point (CEO only)
    res_patch = client_with_db.patch(
        f"/api/v1/trips/{trip_id}/pickup-points/{pt1_id}",
        json={"name": "Updated Gathering Spot A"},
        headers=headers_ceo,
    )
    assert res_patch.status_code == 200
    assert res_patch.json()["name"] == "Updated Gathering Spot A"

    # 4. Delete pickup point (CEO only)
    res_del = client_with_db.delete(
        f"/api/v1/trips/{trip_id}/pickup-points/{pt1_id}",
        headers=headers_ceo,
    )
    assert res_del.status_code == 204

    # List remaining points
    res_remaining = client_with_db.get(
        f"/api/v1/trips/{trip_id}/pickup-points",
        headers=headers_sup,
    )
    assert len(res_remaining.json()) == 1
    assert res_remaining.json()[0]["id"] == pt2_id
