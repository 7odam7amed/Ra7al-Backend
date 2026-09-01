from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import create_access_token, hash_password
from app.models.enums import GenderEnum, RoleEnum
from app.models.station import Station
from app.models.user import User


def _create_user_and_token(
    session: Session,
    identifier: str,
    role: RoleEnum,
) -> tuple[User, str]:
    phone_digits = f"{abs(hash(identifier)) % 100000000:08d}"
    phone_number = f"+2010{phone_digits}"
    user = User(
        full_name="Route API User",
        phone_number=phone_number,
        password_hash=hash_password("Password123!"),
        gender=GenderEnum.MALE,
        role=role,
        is_active=True,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    token = create_access_token(subject=user.id, role=user.role.value)
    return user, token


def _create_test_stations(session: Session) -> list[Station]:
    stations = [
        Station(name="Station 1", code="ST-R-1", latitude=30.0, longitude=31.0),
        Station(name="Station 2", code="ST-R-2", latitude=30.1, longitude=31.1),
        Station(name="Station 3", code="ST-R-3", latitude=30.2, longitude=31.2),
        Station(name="Station 4", code="ST-R-4", latitude=30.3, longitude=31.3),
    ]
    session.add_all(stations)
    session.commit()
    return stations


def test_ceo_and_supervisor_can_create_route(
    client_with_db: TestClient, db_session: Session
) -> None:
    _, ceo_token = _create_user_and_token(db_session, "ceo_route@test.edu", RoleEnum.CEO)
    sup_user, sup_token = _create_user_and_token(db_session, "sup_route@test.edu", RoleEnum.SUPERVISOR)
    stations = _create_test_stations(db_session)

    # CEO creates route
    res_ceo = client_with_db.post(
        "/api/v1/routes",
        json={
            "route_number": "R-101",
            "name": "Express Route",
            "origin_station_id": stations[0].id,
            "destination_station_id": stations[1].id,
            "distance_km": 15.5,
            "estimated_duration_minutes": 30,
            "supervisor_id": sup_user.id,
        },
        headers={"Authorization": f"Bearer {ceo_token}"},
    )
    assert res_ceo.status_code == 201
    data_ceo = res_ceo.json()
    assert data_ceo["id"] is not None
    assert data_ceo["route_number"] == "R-101"
    assert data_ceo["supervisor_id"] == sup_user.id
    assert data_ceo["is_active"] is True

    # Supervisor creates route
    res_sup = client_with_db.post(
        "/api/v1/routes",
        json={
            "route_number": "R-102",
            "name": "Local Route",
            "origin_station_id": stations[0].id,
            "destination_station_id": stations[2].id,
            "distance_km": 8.0,
            "estimated_duration_minutes": 20,
        },
        headers={"Authorization": f"Bearer {sup_token}"},
    )
    assert res_sup.status_code == 201
    assert res_sup.json()["route_number"] == "R-102"


def test_create_route_validations(
    client_with_db: TestClient, db_session: Session
) -> None:
    _, ceo_token = _create_user_and_token(db_session, "ceo_val_route@test.edu", RoleEnum.CEO)
    student, _ = _create_user_and_token(db_session, "student_val_route@test.edu", RoleEnum.STUDENT)
    stations = _create_test_stations(db_session)
    headers = {"Authorization": f"Bearer {ceo_token}"}

    # Same origin and destination -> 422
    res_same = client_with_db.post(
        "/api/v1/routes",
        json={
            "route_number": "R-INV1",
            "name": "Same",
            "origin_station_id": stations[0].id,
            "destination_station_id": stations[0].id,
            "distance_km": 10.0,
            "estimated_duration_minutes": 20,
        },
        headers=headers,
    )
    assert res_same.status_code == 422

    # Non-supervisor assigned -> 422
    res_student_sup = client_with_db.post(
        "/api/v1/routes",
        json={
            "route_number": "R-INV2",
            "name": "Bad Sup",
            "origin_station_id": stations[0].id,
            "destination_station_id": stations[1].id,
            "distance_km": 10.0,
            "estimated_duration_minutes": 20,
            "supervisor_id": student.id,
        },
        headers=headers,
    )
    assert res_student_sup.status_code == 422

    # Missing station -> 404
    res_missing_st = client_with_db.post(
        "/api/v1/routes",
        json={
            "route_number": "R-INV3",
            "name": "Missing",
            "origin_station_id": 99999,
            "destination_station_id": stations[1].id,
            "distance_km": 10.0,
            "estimated_duration_minutes": 20,
        },
        headers=headers,
    )
    assert res_missing_st.status_code == 404


def test_route_update_and_supervisor_assignment(
    client_with_db: TestClient, db_session: Session
) -> None:
    _, ceo_token = _create_user_and_token(db_session, "ceo_upd_route@test.edu", RoleEnum.CEO)
    sup_user, _ = _create_user_and_token(db_session, "sup_upd_route@test.edu", RoleEnum.SUPERVISOR)
    stations = _create_test_stations(db_session)
    headers = {"Authorization": f"Bearer {ceo_token}"}

    created = client_with_db.post(
        "/api/v1/routes",
        json={
            "route_number": "R-201",
            "name": "Route 201",
            "origin_station_id": stations[0].id,
            "destination_station_id": stations[1].id,
            "distance_km": 10.0,
            "estimated_duration_minutes": 20,
        },
        headers=headers,
    ).json()
    route_id = created["id"]

    # Update metadata
    patch_res = client_with_db.patch(
        f"/api/v1/routes/{route_id}",
        json={"name": "Route 201 Modified", "distance_km": 12.5},
        headers=headers,
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["name"] == "Route 201 Modified"
    assert patch_res.json()["distance_km"] == 12.5

    # Update status
    status_res = client_with_db.patch(
        f"/api/v1/routes/{route_id}/status",
        json={"is_active": False},
        headers=headers,
    )
    assert status_res.status_code == 200
    assert status_res.json()["is_active"] is False

    # Assign supervisor
    sup_res = client_with_db.patch(
        f"/api/v1/routes/{route_id}/supervisor",
        json={"supervisor_id": sup_user.id},
        headers=headers,
    )
    assert sup_res.status_code == 200
    assert sup_res.json()["supervisor_id"] == sup_user.id


def test_route_stops_full_lifecycle(
    client_with_db: TestClient, db_session: Session
) -> None:
    _, ceo_token = _create_user_and_token(db_session, "ceo_stops@test.edu", RoleEnum.CEO)
    stations = _create_test_stations(db_session)
    headers = {"Authorization": f"Bearer {ceo_token}"}

    route = client_with_db.post(
        "/api/v1/routes",
        json={
            "route_number": "R-STOPS-API",
            "name": "Stops Route",
            "origin_station_id": stations[0].id,
            "destination_station_id": stations[1].id,
            "distance_km": 20.0,
            "estimated_duration_minutes": 40,
        },
        headers=headers,
    ).json()
    route_id = route["id"]

    # Add stop 1
    stop1_res = client_with_db.post(
        f"/api/v1/routes/{route_id}/stops",
        json={"station_id": stations[2].id, "stop_order": 1},
        headers=headers,
    )
    assert stop1_res.status_code == 201
    stop1 = stop1_res.json()
    assert stop1["station_id"] == stations[2].id
    assert stop1["stop_order"] == 1

    # Add stop 2
    stop2_res = client_with_db.post(
        f"/api/v1/routes/{route_id}/stops",
        json={"station_id": stations[3].id, "stop_order": 2},
        headers=headers,
    )
    assert stop2_res.status_code == 201
    stop2 = stop2_res.json()

    # List stops
    list_stops_res = client_with_db.get(
        f"/api/v1/routes/{route_id}/stops", headers=headers
    )
    assert list_stops_res.status_code == 200
    assert len(list_stops_res.json()) == 2

    # Reorder stops
    reorder_res = client_with_db.patch(
        f"/api/v1/routes/{route_id}/stops/reorder",
        json={
            "stops": [
                {"route_stop_id": stop1["id"], "stop_order": 2},
                {"route_stop_id": stop2["id"], "stop_order": 1},
            ]
        },
        headers=headers,
    )
    assert reorder_res.status_code == 200
    reordered = reorder_res.json()
    assert reordered[0]["id"] == stop2["id"]
    assert reordered[0]["stop_order"] == 1
    assert reordered[1]["id"] == stop1["id"]
    assert reordered[1]["stop_order"] == 2

    # Update single stop
    patch_stop_res = client_with_db.patch(
        f"/api/v1/routes/{route_id}/stops/{stop1['id']}",
        json={"stop_order": 5},
        headers=headers,
    )
    assert patch_stop_res.status_code == 200
    assert patch_stop_res.json()["stop_order"] == 5

    # Delete stop
    del_stop_res = client_with_db.delete(
        f"/api/v1/routes/{route_id}/stops/{stop1['id']}",
        headers=headers,
    )
    assert del_stop_res.status_code == 204

    # Delete whole route
    del_route_res = client_with_db.delete(
        f"/api/v1/routes/{route_id}", headers=headers
    )
    assert del_route_res.status_code == 204


def test_routes_rbac_rejections(
    client_with_db: TestClient, db_session: Session
) -> None:
    _, student_token = _create_user_and_token(db_session, "student_r_rbac@test.edu", RoleEnum.STUDENT)
    headers = {"Authorization": f"Bearer {student_token}"}

    # Student -> 403
    assert client_with_db.post("/api/v1/routes", json={}, headers=headers).status_code == 403
    assert client_with_db.get("/api/v1/routes", headers=headers).status_code == 403
    assert client_with_db.get("/api/v1/routes/1", headers=headers).status_code == 403
    assert client_with_db.patch("/api/v1/routes/1", json={}, headers=headers).status_code == 403
    assert client_with_db.patch("/api/v1/routes/1/status", json={}, headers=headers).status_code == 403
    assert client_with_db.patch("/api/v1/routes/1/supervisor", json={}, headers=headers).status_code == 403
    assert client_with_db.delete("/api/v1/routes/1", headers=headers).status_code == 403
    assert client_with_db.get("/api/v1/routes/1/stops", headers=headers).status_code == 403
    assert client_with_db.post("/api/v1/routes/1/stops", json={}, headers=headers).status_code == 403
    assert client_with_db.patch("/api/v1/routes/1/stops/reorder", json={"stops": []}, headers=headers).status_code == 403
    assert client_with_db.delete("/api/v1/routes/1/stops/1", headers=headers).status_code == 403

    # Unauthenticated -> 401
    assert client_with_db.post("/api/v1/routes", json={}).status_code == 401
    assert client_with_db.get("/api/v1/routes").status_code == 401
    assert client_with_db.get("/api/v1/routes/1").status_code == 401
    assert client_with_db.patch("/api/v1/routes/1", json={}).status_code == 401
    assert client_with_db.delete("/api/v1/routes/1").status_code == 401
    assert client_with_db.get("/api/v1/routes/1/stops").status_code == 401
    assert client_with_db.post("/api/v1/routes/1/stops", json={}).status_code == 401
