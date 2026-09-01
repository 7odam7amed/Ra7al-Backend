from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import create_access_token, hash_password
from app.models.enums import GenderEnum, RoleEnum
from app.models.user import User


def _create_user_and_token(
    session: Session,
    identifier: str,
    role: RoleEnum,
) -> str:
    phone_digits = f"{abs(hash(identifier)) % 100000000:08d}"
    phone_number = f"+2010{phone_digits}"
    user = User(
        full_name="Station Test User",
        phone_number=phone_number,
        password_hash=hash_password("Password123!"),
        gender=GenderEnum.MALE,
        role=role,
        is_active=True,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return create_access_token(subject=user.id, role=user.role.value)


def test_ceo_and_supervisor_can_create_station(
    client_with_db: TestClient, db_session: Session
) -> None:
    ceo_token = _create_user_and_token(db_session, "ceo_st@test.edu", RoleEnum.CEO)
    sup_token = _create_user_and_token(db_session, "sup_st@test.edu", RoleEnum.SUPERVISOR)

    # CEO creates station
    res_ceo = client_with_db.post(
        "/api/v1/stations",
        json={
            "name": "Main Gate",
            "code": "ST-GATE-01",
            "address": "Campus Ave",
            "latitude": 30.0444,
            "longitude": 31.2357,
        },
        headers={"Authorization": f"Bearer {ceo_token}"},
    )
    assert res_ceo.status_code == 201
    data_ceo = res_ceo.json()
    assert data_ceo["id"] is not None
    assert data_ceo["name"] == "Main Gate"
    assert data_ceo["code"] == "ST-GATE-01"
    assert data_ceo["is_active"] is True

    # Supervisor creates station
    res_sup = client_with_db.post(
        "/api/v1/stations",
        json={
            "name": "Library Stop",
            "code": "ST-LIB-02",
            "latitude": 30.0450,
            "longitude": 31.2360,
        },
        headers={"Authorization": f"Bearer {sup_token}"},
    )
    assert res_sup.status_code == 201
    assert res_sup.json()["code"] == "ST-LIB-02"


def test_create_station_duplicate_code(
    client_with_db: TestClient, db_session: Session
) -> None:
    ceo_token = _create_user_and_token(db_session, "ceo_dup_st@test.edu", RoleEnum.CEO)
    headers = {"Authorization": f"Bearer {ceo_token}"}

    client_with_db.post(
        "/api/v1/stations",
        json={"name": "S1", "code": "ST-DUP", "latitude": 30.0, "longitude": 31.0},
        headers=headers,
    )

    res_dup = client_with_db.post(
        "/api/v1/stations",
        json={"name": "S2", "code": "st-dup", "latitude": 30.1, "longitude": 31.1},
        headers=headers,
    )
    assert res_dup.status_code == 409
    assert "already exists" in res_dup.json()["detail"].lower()


def test_station_get_and_list_with_pagination(
    client_with_db: TestClient, db_session: Session
) -> None:
    ceo_token = _create_user_and_token(db_session, "ceo_list_st@test.edu", RoleEnum.CEO)
    headers = {"Authorization": f"Bearer {ceo_token}"}

    create_res = client_with_db.post(
        "/api/v1/stations",
        json={"name": "Station A", "code": "ST-A", "latitude": 30.0, "longitude": 31.0},
        headers=headers,
    )
    st_id = create_res.json()["id"]

    # Get by ID
    get_res = client_with_db.get(f"/api/v1/stations/{st_id}", headers=headers)
    assert get_res.status_code == 200
    assert get_res.json()["id"] == st_id

    # Not found
    assert client_with_db.get("/api/v1/stations/99999", headers=headers).status_code == 404

    # List
    list_res = client_with_db.get("/api/v1/stations", headers=headers)
    assert list_res.status_code == 200
    assert list_res.json()["total"] >= 1


def test_station_update_and_delete(
    client_with_db: TestClient, db_session: Session
) -> None:
    ceo_token = _create_user_and_token(db_session, "ceo_upd_st@test.edu", RoleEnum.CEO)
    headers = {"Authorization": f"Bearer {ceo_token}"}

    created = client_with_db.post(
        "/api/v1/stations",
        json={"name": "Station Temp", "code": "ST-TEMP", "latitude": 30.0, "longitude": 31.0},
        headers=headers,
    ).json()
    st_id = created["id"]

    # Update
    patch_res = client_with_db.patch(
        f"/api/v1/stations/{st_id}",
        json={"name": "Updated Name", "latitude": 30.5},
        headers=headers,
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["name"] == "Updated Name"
    assert patch_res.json()["latitude"] == 30.5

    # Status update
    status_res = client_with_db.patch(
        f"/api/v1/stations/{st_id}/status",
        json={"is_active": False},
        headers=headers,
    )
    assert status_res.status_code == 200
    assert status_res.json()["is_active"] is False

    # Delete
    del_res = client_with_db.delete(f"/api/v1/stations/{st_id}", headers=headers)
    assert del_res.status_code == 204

    # Verify 404 after delete
    assert client_with_db.get(f"/api/v1/stations/{st_id}", headers=headers).status_code == 404


def test_station_rbac_rejections(
    client_with_db: TestClient, db_session: Session
) -> None:
    student_token = _create_user_and_token(db_session, "student_st@test.edu", RoleEnum.STUDENT)
    headers = {"Authorization": f"Bearer {student_token}"}

    # Student -> 403
    assert client_with_db.post("/api/v1/stations", json={}, headers=headers).status_code == 403
    assert client_with_db.get("/api/v1/stations", headers=headers).status_code == 403
    assert client_with_db.get("/api/v1/stations/1", headers=headers).status_code == 403
    assert client_with_db.patch("/api/v1/stations/1", json={}, headers=headers).status_code == 403
    assert client_with_db.patch("/api/v1/stations/1/status", json={}, headers=headers).status_code == 403
    assert client_with_db.delete("/api/v1/stations/1", headers=headers).status_code == 403

    # Unauthenticated -> 401
    assert client_with_db.post("/api/v1/stations", json={}).status_code == 401
    assert client_with_db.get("/api/v1/stations").status_code == 401
    assert client_with_db.get("/api/v1/stations/1").status_code == 401
    assert client_with_db.patch("/api/v1/stations/1", json={}).status_code == 401
    assert client_with_db.patch("/api/v1/stations/1/status", json={}).status_code == 401
    assert client_with_db.delete("/api/v1/stations/1").status_code == 401
