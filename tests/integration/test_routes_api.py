from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import create_access_token, hash_password
from app.models.enums import GenderEnum, RoleEnum
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


def test_ceo_can_create_route_container(
    client_with_db: TestClient, db_session: Session
) -> None:
    """A Route is only a named container of pickup points: no origin,
    destination, distance, duration, or supervisor (spec §4/§7)."""
    _, ceo_token = _create_user_and_token(db_session, "ceo_route@test.edu", RoleEnum.CEO)

    res_ceo = client_with_db.post(
        "/api/v1/routes",
        json={"name": "Express Route"},
        headers={"Authorization": f"Bearer {ceo_token}"},
    )
    assert res_ceo.status_code == 201
    data_ceo = res_ceo.json()
    assert data_ceo["id"] is not None
    assert data_ceo["name"] == "Express Route"
    assert data_ceo["is_active"] is True

    # Obsolete route fields must not exist on the API.
    for obsolete in (
        "route_number",
        "origin_station_id",
        "destination_station_id",
        "distance_km",
        "estimated_duration_minutes",
        "supervisor_id",
    ):
        assert obsolete not in data_ceo, f"obsolete field {obsolete} exposed"


def test_create_route_validations(
    client_with_db: TestClient, db_session: Session
) -> None:
    _, ceo_token = _create_user_and_token(db_session, "ceo_val_route@test.edu", RoleEnum.CEO)
    _create_user_and_token(db_session, "student_val_route@test.edu", RoleEnum.STUDENT)
    headers = {"Authorization": f"Bearer {ceo_token}"}

    # Missing name -> 422
    res_missing = client_with_db.post(
        "/api/v1/routes", json={}, headers=headers
    )
    assert res_missing.status_code == 422

    # Duplicate route name -> 409
    res_first = client_with_db.post(
        "/api/v1/routes", json={"name": "Unique Route X"}, headers=headers
    )
    assert res_first.status_code == 201
    res_dup = client_with_db.post(
        "/api/v1/routes", json={"name": "Unique Route X"}, headers=headers
    )
    assert res_dup.status_code == 409


def test_route_update_and_status(
    client_with_db: TestClient, db_session: Session
) -> None:
    _, ceo_token = _create_user_and_token(db_session, "ceo_upd_route@test.edu", RoleEnum.CEO)
    headers = {"Authorization": f"Bearer {ceo_token}"}

    created = client_with_db.post(
        "/api/v1/routes",
        json={"name": "Route 201"},
        headers=headers,
    ).json()
    route_id = created["id"]

    # Update name
    patch_res = client_with_db.patch(
        f"/api/v1/routes/{route_id}",
        json={"name": "Route 201 Modified"},
        headers=headers,
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["name"] == "Route 201 Modified"

    # Update status
    status_res = client_with_db.patch(
        f"/api/v1/routes/{route_id}/status",
        json={"is_active": False},
        headers=headers,
    )
    assert status_res.status_code == 200
    assert status_res.json()["is_active"] is False


def test_pickup_points_full_lifecycle(
    client_with_db: TestClient, db_session: Session
) -> None:
    """Pickup points belong to exactly ONE route; no latitude/longitude."""
    _, ceo_token = _create_user_and_token(db_session, "ceo_pp@test.edu", RoleEnum.CEO)
    headers = {"Authorization": f"Bearer {ceo_token}"}

    route = client_with_db.post(
        "/api/v1/routes", json={"name": "Points Route"}, headers=headers
    ).json()
    route_id = route["id"]

    # Add point 1 (no latitude/longitude fields exist)
    p1_res = client_with_db.post(
        f"/api/v1/routes/{route_id}/pickup-points",
        json={"name": "Al-Mahatta", "sequence": 1},
        headers=headers,
    )
    assert p1_res.status_code == 201
    p1 = p1_res.json()
    assert p1["name"] == "Al-Mahatta"
    assert p1["route_id"] == route_id
    assert "latitude" not in p1
    assert "longitude" not in p1

    # Add point 2
    p2_res = client_with_db.post(
        f"/api/v1/routes/{route_id}/pickup-points",
        json={"name": "Al-Walidiyah", "sequence": 2},
        headers=headers,
    )
    assert p2_res.status_code == 201
    p2 = p2_res.json()

    # Duplicate name on the same route -> 409
    dup_res = client_with_db.post(
        f"/api/v1/routes/{route_id}/pickup-points",
        json={"name": "Al-Mahatta", "sequence": 3},
        headers=headers,
    )
    assert dup_res.status_code == 409

    # List points
    list_res = client_with_db.get(
        f"/api/v1/routes/{route_id}/pickup-points", headers=headers
    )
    assert list_res.status_code == 200
    assert [p["id"] for p in list_res.json()] == [p1["id"], p2["id"]]
    assert [p["sequence"] for p in list_res.json()] == [1, 2]

    # Update a point
    patch_res = client_with_db.patch(
        f"/api/v1/routes/{route_id}/pickup-points/{p1['id']}",
        json={"name": "Al-Mahatta Renamed"},
        headers=headers,
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["name"] == "Al-Mahatta Renamed"

    # Delete point 2
    del_res = client_with_db.delete(
        f"/api/v1/routes/{route_id}/pickup-points/{p2['id']}",
        headers=headers,
    )
    assert del_res.status_code == 204

    # Delete whole route
    del_route_res = client_with_db.delete(
        f"/api/v1/routes/{route_id}", headers=headers
    )
    assert del_route_res.status_code == 204


def test_routes_rbac_rejections(
    client_with_db: TestClient, db_session: Session
) -> None:
    """Route management is CEO-only; students get READ access for the
    transportation screens."""
    student, student_token = _create_user_and_token(db_session, "student_r_rbac@test.edu", RoleEnum.STUDENT)
    _, ceo_token = _create_user_and_token(db_session, "ceo_r_rbac@test.edu", RoleEnum.CEO)
    ceo_headers = {"Authorization": f"Bearer {ceo_token}"}

    created = client_with_db.post(
        "/api/v1/routes",
        json={"name": "RBAC Route"},
        headers=ceo_headers,
    )
    assert created.status_code == 201
    route_id = created.json()["id"]

    point = client_with_db.post(
        f"/api/v1/routes/{route_id}/pickup-points",
        json={"name": "RBAC Point", "sequence": 1},
        headers=ceo_headers,
    )
    assert point.status_code == 201
    point_id = point.json()["id"]

    student_headers = {"Authorization": f"Bearer {student_token}"}

    # Student READ access -> allowed (required by the transportation screens)
    assert client_with_db.get("/api/v1/routes", headers=student_headers).status_code == 200
    assert client_with_db.get(f"/api/v1/routes/{route_id}", headers=student_headers).status_code == 200
    assert client_with_db.get(f"/api/v1/routes/{route_id}/pickup-points", headers=student_headers).status_code == 200

    # Student management access -> 403
    assert client_with_db.post("/api/v1/routes", json={}, headers=student_headers).status_code == 403
    assert client_with_db.patch(f"/api/v1/routes/{route_id}", json={}, headers=student_headers).status_code == 403
    assert client_with_db.patch(f"/api/v1/routes/{route_id}/status", json={}, headers=student_headers).status_code == 403
    assert client_with_db.delete(f"/api/v1/routes/{route_id}", headers=student_headers).status_code == 403
    assert client_with_db.post(f"/api/v1/routes/{route_id}/pickup-points", json={}, headers=student_headers).status_code == 403
    assert client_with_db.patch(f"/api/v1/routes/{route_id}/pickup-points/{point_id}", json={}, headers=student_headers).status_code == 403
    assert client_with_db.delete(f"/api/v1/routes/{route_id}/pickup-points/{point_id}", headers=student_headers).status_code == 403

    # Unauthenticated -> 401 (all endpoints, including reads)
    assert client_with_db.get("/api/v1/routes").status_code == 401
    assert client_with_db.get(f"/api/v1/routes/{route_id}").status_code == 401
    assert client_with_db.post("/api/v1/routes", json={}).status_code == 401
    assert client_with_db.patch(f"/api/v1/routes/{route_id}", json={}).status_code == 401
    assert client_with_db.delete(f"/api/v1/routes/{route_id}").status_code == 401
    assert client_with_db.get(f"/api/v1/routes/{route_id}/pickup-points").status_code == 401
    assert client_with_db.post(f"/api/v1/routes/{route_id}/pickup-points", json={}).status_code == 401
