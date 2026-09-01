from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import create_access_token, hash_password
from app.models.enums import GenderEnum, RoleEnum
from app.models.user import User


def _create_user_and_token(
    session: Session,
    identifier: str,
    role: RoleEnum,
    is_active: bool = True,
) -> str:
    phone_digits = f"{abs(hash(identifier)) % 100000000:08d}"
    phone_number = f"+2010{phone_digits}"
    user = User(
        full_name="API User",
        phone_number=phone_number,
        password_hash=hash_password("Password123!"),
        gender=GenderEnum.MALE,
        role=role,
        is_active=is_active,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return create_access_token(subject=user.id, role=user.role.value)


def test_ceo_can_create_bus(
    client_with_db: TestClient, db_session: Session
) -> None:
    ceo_token = _create_user_and_token(db_session, "ceo_bus@test.edu", RoleEnum.CEO)
    sup_token = _create_user_and_token(db_session, "sup_bus@test.edu", RoleEnum.SUPERVISOR)

    # CEO creates bus
    res_ceo = client_with_db.post(
        "/api/v1/buses",
        json={
            "name": "Ra7al Bus 01",
            "plate_number": "ABC-1234",
            "type": "Coaster",
            "capacity": 50,
            "year": 2022,
        },
        headers={"Authorization": f"Bearer {ceo_token}"},
    )
    assert res_ceo.status_code == 201
    data_ceo = res_ceo.json()
    assert data_ceo["id"] is not None
    assert data_ceo["bus_number"] == "Ra7al Bus 01"
    assert data_ceo["license_plate"] == "ABC-1234"
    assert data_ceo["capacity"] == 50
    assert data_ceo["status"] == "ACTIVE"

    # Supervisor is forbidden from creating buses (403)
    res_sup = client_with_db.post(
        "/api/v1/buses",
        json={
            "bus_number": "BUS-102",
            "license_plate": "XYZ-789",
            "capacity": 40,
        },
        headers={"Authorization": f"Bearer {sup_token}"},
    )
    assert res_sup.status_code == 403

    # Supervisor can view buses (200)
    res_sup_view = client_with_db.get(
        "/api/v1/buses",
        headers={"Authorization": f"Bearer {sup_token}"},
    )
    assert res_sup_view.status_code == 200


def test_create_bus_duplicate_validation(
    client_with_db: TestClient, db_session: Session
) -> None:
    ceo_token = _create_user_and_token(db_session, "ceo_dup@test.edu", RoleEnum.CEO)
    headers = {"Authorization": f"Bearer {ceo_token}"}

    client_with_db.post(
        "/api/v1/buses",
        json={"bus_number": "BUS-201", "license_plate": "PLATE-201", "capacity": 50},
        headers=headers,
    )

    # Duplicate bus number
    res_dup_num = client_with_db.post(
        "/api/v1/buses",
        json={"bus_number": "BUS-201", "license_plate": "PLATE-202", "capacity": 50},
        headers=headers,
    )
    assert res_dup_num.status_code == 409
    assert "already exists" in res_dup_num.json()["detail"].lower()

    # Duplicate license plate
    res_dup_plate = client_with_db.post(
        "/api/v1/buses",
        json={"bus_number": "BUS-203", "license_plate": "PLATE-201", "capacity": 50},
        headers=headers,
    )
    assert res_dup_plate.status_code == 409
    assert "already exists" in res_dup_plate.json()["detail"].lower()


def test_create_bus_invalid_inputs(
    client_with_db: TestClient, db_session: Session
) -> None:
    ceo_token = _create_user_and_token(db_session, "ceo_invalid@test.edu", RoleEnum.CEO)
    headers = {"Authorization": f"Bearer {ceo_token}"}

    # Capacity <= 0
    res_cap_0 = client_with_db.post(
        "/api/v1/buses",
        json={"bus_number": "BUS-INV1", "license_plate": "INV-1", "capacity": 0},
        headers=headers,
    )
    assert res_cap_0.status_code == 422

    # Capacity > 150
    res_cap_big = client_with_db.post(
        "/api/v1/buses",
        json={"bus_number": "BUS-INV2", "license_plate": "INV-2", "capacity": 151},
        headers=headers,
    )
    assert res_cap_big.status_code == 422

    # Empty bus_number
    res_empty_num = client_with_db.post(
        "/api/v1/buses",
        json={"bus_number": "   ", "license_plate": "INV-3", "capacity": 50},
        headers=headers,
    )
    assert res_empty_num.status_code == 422


def test_get_bus_by_id(client_with_db: TestClient, db_session: Session) -> None:
    ceo_token = _create_user_and_token(db_session, "ceo_getbus@test.edu", RoleEnum.CEO)
    headers = {"Authorization": f"Bearer {ceo_token}"}

    create_res = client_with_db.post(
        "/api/v1/buses",
        json={"bus_number": "BUS-301", "license_plate": "PLATE-301", "capacity": 45},
        headers=headers,
    )
    bus_id = create_res.json()["id"]

    # Found
    get_res = client_with_db.get(f"/api/v1/buses/{bus_id}", headers=headers)
    assert get_res.status_code == 200
    assert get_res.json()["id"] == bus_id
    assert get_res.json()["bus_number"] == "BUS-301"

    # Not Found
    get_404 = client_with_db.get("/api/v1/buses/99999", headers=headers)
    assert get_404.status_code == 404


def test_list_buses_pagination_filtering_search(
    client_with_db: TestClient, db_session: Session
) -> None:
    ceo_token = _create_user_and_token(db_session, "ceo_listbuses@test.edu", RoleEnum.CEO)
    headers = {"Authorization": f"Bearer {ceo_token}"}

    # Seed buses
    client_with_db.post(
        "/api/v1/buses",
        json={"bus_number": "BUS-A", "license_plate": "P-11", "capacity": 50, "model": "Mercedes"},
        headers=headers,
    )
    b2 = client_with_db.post(
        "/api/v1/buses",
        json={"bus_number": "BUS-B", "license_plate": "P-22", "capacity": 40, "model": "Volvo"},
        headers=headers,
    ).json()
    client_with_db.patch(
        f"/api/v1/buses/{b2['id']}/status",
        json={"status": "MAINTENANCE"},
        headers=headers,
    )

    # List all
    res_all = client_with_db.get("/api/v1/buses", headers=headers)
    assert res_all.status_code == 200
    assert res_all.json()["total"] == 2
    assert res_all.json()["page"] == 1
    assert res_all.json()["page_size"] == 20
    assert res_all.json()["total_pages"] == 1

    # Filter status
    res_maint = client_with_db.get("/api/v1/buses?status=MAINTENANCE", headers=headers)
    assert res_maint.status_code == 200
    assert res_maint.json()["total"] == 1
    assert res_maint.json()["items"][0]["bus_number"] == "BUS-B"

    # Search
    res_search = client_with_db.get("/api/v1/buses?search=volvo", headers=headers)
    assert res_search.status_code == 200
    assert res_search.json()["total"] == 1
    assert res_search.json()["items"][0]["bus_number"] == "BUS-B"


def test_update_bus_and_status(
    client_with_db: TestClient, db_session: Session
) -> None:
    ceo_token = _create_user_and_token(db_session, "ceo_updatebus@test.edu", RoleEnum.CEO)
    headers = {"Authorization": f"Bearer {ceo_token}"}

    created = client_with_db.post(
        "/api/v1/buses",
        json={"bus_number": "BUS-401", "license_plate": "PLATE-401", "capacity": 30},
        headers=headers,
    ).json()
    bus_id = created["id"]

    # Update info
    patch_res = client_with_db.patch(
        f"/api/v1/buses/{bus_id}",
        json={"capacity": 55, "model": "Scania Touring"},
        headers=headers,
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["capacity"] == 55
    assert patch_res.json()["model"] == "Scania Touring"

    # Update status
    status_res = client_with_db.patch(
        f"/api/v1/buses/{bus_id}/status",
        json={"status": "INACTIVE"},
        headers=headers,
    )
    assert status_res.status_code == 200
    assert status_res.json()["status"] == "INACTIVE"


def test_delete_bus(client_with_db: TestClient, db_session: Session) -> None:
    ceo_token = _create_user_and_token(db_session, "ceo_deletebus@test.edu", RoleEnum.CEO)
    headers = {"Authorization": f"Bearer {ceo_token}"}

    created = client_with_db.post(
        "/api/v1/buses",
        json={"bus_number": "BUS-501", "license_plate": "PLATE-501", "capacity": 30},
        headers=headers,
    ).json()
    bus_id = created["id"]

    del_res = client_with_db.delete(f"/api/v1/buses/{bus_id}", headers=headers)
    assert del_res.status_code == 204

    # Verification: GET returns 404
    get_res = client_with_db.get(f"/api/v1/buses/{bus_id}", headers=headers)
    assert get_res.status_code == 404


def test_delete_bus_fails_when_assigned_to_active_trip(
    client_with_db: TestClient, db_session: Session
) -> None:
    from datetime import datetime, timezone, timedelta
    from app.models.route import Route
    from app.models.station import Station
    from app.models.trip import Trip

    ceo_token = _create_user_and_token(db_session, "ceo_del_active@test.edu", RoleEnum.CEO)
    headers = {"Authorization": f"Bearer {ceo_token}"}

    # Create bus
    created = client_with_db.post(
        "/api/v1/buses",
        json={"bus_number": "BUS-ACT-1", "license_plate": "PLATE-ACT-1", "capacity": 30},
        headers=headers,
    ).json()
    bus_id = created["id"]

    # Create supervisor, stations, route, trip
    sup = User(
        full_name="Sup Active",
        phone_number="+201011119999",
        password_hash=hash_password("Password123!"),
        gender=GenderEnum.MALE,
        role=RoleEnum.SUPERVISOR,
        is_active=True,
    )
    s1 = Station(name="S1", code="ST-S1-BUS", latitude=30.0, longitude=31.0)
    s2 = Station(name="S2", code="ST-S2-BUS", latitude=30.1, longitude=31.1)
    db_session.add_all([sup, s1, s2])
    db_session.commit()

    route = Route(
        route_number="R-BUS-ACT",
        name="Route Bus Act",
        origin_station_id=s1.id,
        destination_station_id=s2.id,
        distance_km=10.0,
        estimated_duration_minutes=20,
    )
    db_session.add(route)
    db_session.commit()

    dep = datetime.now(timezone.utc) + timedelta(hours=2)
    trip = Trip(
        route_id=route.id,
        bus_id=bus_id,
        supervisor_id=sup.id,
        departure_time=dep,
        estimated_arrival_time=dep + timedelta(hours=1),
        passenger_capacity=30,
    )
    db_session.add(trip)
    db_session.commit()

    # Deleting bus assigned to active trip returns 409 Conflict
    del_res = client_with_db.delete(f"/api/v1/buses/{bus_id}", headers=headers)
    assert del_res.status_code == 409
    assert "active scheduled trips" in del_res.json()["detail"].lower()


def test_rbac_student_rejected_with_403(
    client_with_db: TestClient, db_session: Session
) -> None:
    student_token = _create_user_and_token(db_session, "student_bus@test.edu", RoleEnum.STUDENT)
    headers = {"Authorization": f"Bearer {student_token}"}

    assert client_with_db.post("/api/v1/buses", json={}, headers=headers).status_code == 403
    assert client_with_db.get("/api/v1/buses", headers=headers).status_code == 403
    assert client_with_db.get("/api/v1/buses/1", headers=headers).status_code == 403
    assert client_with_db.patch("/api/v1/buses/1", json={}, headers=headers).status_code == 403
    assert client_with_db.patch("/api/v1/buses/1/status", json={}, headers=headers).status_code == 403
    assert client_with_db.delete("/api/v1/buses/1", headers=headers).status_code == 403


def test_unauthenticated_requests_rejected_with_401(
    client_with_db: TestClient,
) -> None:
    assert client_with_db.post("/api/v1/buses", json={}).status_code == 401
    assert client_with_db.get("/api/v1/buses").status_code == 401
    assert client_with_db.get("/api/v1/buses/1").status_code == 401
    assert client_with_db.patch("/api/v1/buses/1", json={}).status_code == 401
    assert client_with_db.patch("/api/v1/buses/1/status", json={}).status_code == 401
    assert client_with_db.delete("/api/v1/buses/1").status_code == 401
