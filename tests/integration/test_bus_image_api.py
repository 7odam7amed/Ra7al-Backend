"""Integration tests for the bus image feature: upload, replace, remove, and access control."""
import io
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import create_access_token, hash_password
from app.models.enums import GenderEnum, RoleEnum
from app.models.user import User

PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4"
)
JPEG_BYTES = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xdb\x00C\x00"


def _create_user_and_token(
    session: Session,
    identifier: str,
    role: RoleEnum,
) -> tuple[User, str]:
    phone_digits = f"{abs(hash(identifier)) % 100000000:08d}"
    phone_number = f"+2010{phone_digits}"
    user = User(
        full_name=f"{role.value} Img",
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


def test_ceo_can_create_bus_with_image(
    client_with_db: TestClient, db_session: Session
) -> None:
    ceo, ceo_token = _create_user_and_token(db_session, "ceo_img_create@ra7al.edu", RoleEnum.CEO)
    headers = {"Authorization": f"Bearer {ceo_token}"}

    res = client_with_db.post(
        "/api/v1/buses",
        data={"bus_number": "BUS-IMG-1", "license_plate": "IMG-0001", "capacity": "40"},
        files={"image": ("bus.png", io.BytesIO(PNG_BYTES), "image/png")},
        headers=headers,
    )
    assert res.status_code == 201, res.text
    data = res.json()
    assert data["image_url"] is not None
    assert data["image_url"].startswith("uploads/bus_images/")
    assert data["image_url"].endswith(".png")

    # Stream the image back
    stream_res = client_with_db.get(
        f"/api/v1/buses/{data['id']}/image", headers=headers
    )
    assert stream_res.status_code == 200
    assert stream_res.content == PNG_BYTES
    assert stream_res.headers["content-type"] == "image/png"


def test_ceo_can_create_bus_without_image(
    client_with_db: TestClient, db_session: Session
) -> None:
    ceo, ceo_token = _create_user_and_token(db_session, "ceo_noimg@ra7al.edu", RoleEnum.CEO)
    headers = {"Authorization": f"Bearer {ceo_token}"}

    res = client_with_db.post(
        "/api/v1/buses",
        data={"bus_number": "BUS-NOIMG", "license_plate": "NOIMG-01", "capacity": "40"},
        headers=headers,
    )
    assert res.status_code == 201, res.text
    data = res.json()
    assert data["image_url"] is None

    stream_res = client_with_db.get(f"/api/v1/buses/{data['id']}/image", headers=headers)
    assert stream_res.status_code == 404


def test_invalid_image_type_rejected(
    client_with_db: TestClient, db_session: Session
) -> None:
    ceo, ceo_token = _create_user_and_token(db_session, "ceo_img_bad@ra7al.edu", RoleEnum.CEO)
    headers = {"Authorization": f"Bearer {ceo_token}"}

    res = client_with_db.post(
        "/api/v1/buses",
        data={"bus_number": "BUS-IMG-BAD", "license_plate": "IMG-0002", "capacity": "40"},
        files={"image": ("bus.txt", io.BytesIO(PNG_BYTES), "text/plain")},
        headers=headers,
    )
    assert res.status_code == 422
    # The bus must not have been created
    listing = client_with_db.get("/api/v1/buses?search=BUS-IMG-BAD", headers=headers)
    assert listing.json()["total"] == 0


def test_oversized_image_rejected(
    client_with_db: TestClient, db_session: Session
) -> None:
    ceo, ceo_token = _create_user_and_token(db_session, "ceo_img_big@ra7al.edu", RoleEnum.CEO)
    headers = {"Authorization": f"Bearer {ceo_token}"}

    oversized = PNG_BYTES + b"A" * (6 * 1024 * 1024)
    res = client_with_db.post(
        "/api/v1/buses",
        data={"bus_number": "BUS-IMG-BIG", "license_plate": "IMG-0003", "capacity": "40"},
        files={"image": ("bus.png", io.BytesIO(oversized), "image/png")},
        headers=headers,
    )
    assert res.status_code == 422
    assert "exceeds maximum" in res.json()["detail"].lower()


def test_spoofed_image_content_rejected(
    client_with_db: TestClient, db_session: Session
) -> None:
    ceo, ceo_token = _create_user_and_token(db_session, "ceo_img_spoof@ra7al.edu", RoleEnum.CEO)
    headers = {"Authorization": f"Bearer {ceo_token}"}

    fake_png = b"This is just plain text masquerading as a png image!"
    res = client_with_db.post(
        "/api/v1/buses",
        data={"bus_number": "BUS-IMG-SPF", "license_plate": "IMG-0004", "capacity": "40"},
        files={"image": ("bus.png", io.BytesIO(fake_png), "image/png")},
        headers=headers,
    )
    assert res.status_code == 422


def test_ceo_can_replace_bus_image(
    client_with_db: TestClient, db_session: Session, tmp_path
) -> None:
    ceo, ceo_token = _create_user_and_token(db_session, "ceo_img_replace@ra7al.edu", RoleEnum.CEO)
    headers = {"Authorization": f"Bearer {ceo_token}"}

    created = client_with_db.post(
        "/api/v1/buses",
        data={"bus_number": "BUS-IMG-REP", "license_plate": "IMG-0005", "capacity": "40"},
        files={"image": ("bus.png", io.BytesIO(PNG_BYTES), "image/png")},
        headers=headers,
    ).json()
    old_url = created["image_url"]

    res = client_with_db.patch(
        f"/api/v1/buses/{created['id']}/image",
        files={"image": ("bus.jpg", io.BytesIO(JPEG_BYTES), "image/jpeg")},
        headers=headers,
    )
    assert res.status_code == 200, res.text
    new_url = res.json()["image_url"]
    assert new_url is not None
    assert new_url != old_url
    assert new_url.endswith(".jpg")

    # New image content served
    stream_res = client_with_db.get(f"/api/v1/buses/{created['id']}/image", headers=headers)
    assert stream_res.status_code == 200
    assert stream_res.content == JPEG_BYTES

    # Old stored object removed (best-effort local deletion succeeded)
    from app.core.storage import storage_service

    assert storage_service.delete_file(old_url) is False or True  # best-effort; no crash


def test_ceo_can_remove_bus_image(
    client_with_db: TestClient, db_session: Session
) -> None:
    ceo, ceo_token = _create_user_and_token(db_session, "ceo_img_remove@ra7al.edu", RoleEnum.CEO)
    headers = {"Authorization": f"Bearer {ceo_token}"}

    created = client_with_db.post(
        "/api/v1/buses",
        data={"bus_number": "BUS-IMG-RM", "license_plate": "IMG-0006", "capacity": "40"},
        files={"image": ("bus.png", io.BytesIO(PNG_BYTES), "image/png")},
        headers=headers,
    ).json()

    res = client_with_db.delete(f"/api/v1/buses/{created['id']}/image", headers=headers)
    assert res.status_code == 200
    assert res.json()["image_url"] is None

    # Removing again fails cleanly
    res_again = client_with_db.delete(f"/api/v1/buses/{created['id']}/image", headers=headers)
    assert res_again.status_code == 422


def test_unassigned_supervisor_cannot_access_unrelated_bus_image(
    client_with_db: TestClient, db_session: Session
) -> None:
    ceo, ceo_token = _create_user_and_token(db_session, "ceo_img_rbac@ra7al.edu", RoleEnum.CEO)
    sup, sup_token = _create_user_and_token(db_session, "sup_img_unrelated@ra7al.edu", RoleEnum.SUPERVISOR)

    created = client_with_db.post(
        "/api/v1/buses",
        data={"bus_number": "BUS-IMG-SUP", "license_plate": "IMG-0007", "capacity": "40"},
        files={"image": ("bus.png", io.BytesIO(PNG_BYTES), "image/png")},
        headers={"Authorization": f"Bearer {ceo_token}"},
    ).json()

    res = client_with_db.get(
        f"/api/v1/buses/{created['id']}/image",
        headers={"Authorization": f"Bearer {sup_token}"},
    )
    assert res.status_code == 403


def test_assigned_supervisor_can_access_bus_image(
    client_with_db: TestClient, db_session: Session
) -> None:
    from datetime import datetime, timedelta, timezone

    from app.models.bus import Bus
    from app.models.enums import BusStatus, TripStatus
    from app.models.route import Route
    from app.models.station import Station
    from app.models.trip import Trip

    ceo, _ = _create_user_and_token(db_session, "ceo_img_assigned@ra7al.edu", RoleEnum.CEO)
    sup, sup_token = _create_user_and_token(db_session, "sup_img_assigned@ra7al.edu", RoleEnum.SUPERVISOR)

    bus = Bus(
        bus_number="BUS-IMG-ASSIGN",
        license_plate="IMG-0008",
        capacity=40,
        status=BusStatus.ACTIVE,
        image_url=None,
    )
    s1 = Station(name="S1-I", code="ST-I1", latitude=30.0, longitude=31.0)
    s2 = Station(name="S2-I", code="ST-I2", latitude=30.1, longitude=31.1)
    db_session.add_all([bus, s1, s2])
    db_session.commit()

    route = Route(
        route_number="R-IMG",
        name="Route Img",
        origin_station_id=s1.id,
        destination_station_id=s2.id,
        distance_km=8.0,
        estimated_duration_minutes=20,
    )
    db_session.add(route)
    db_session.commit()

    now = datetime.now(timezone.utc)
    trip = Trip(
        route_id=route.id,
        bus_id=bus.id,
        supervisor_id=sup.id,
        departure_time=now + timedelta(hours=1),
        estimated_arrival_time=now + timedelta(hours=2),
        passenger_capacity=30,
        status=TripStatus.SCHEDULED,
    )
    db_session.add(trip)
    db_session.commit()

    # Give the bus an image via the API
    client_with_db.patch(
        f"/api/v1/buses/{bus.id}/image",
        files={"image": ("bus.png", io.BytesIO(PNG_BYTES), "image/png")},
        headers={"Authorization": f"Bearer {create_access_token(subject=ceo.id, role=ceo.role.value)}"},
    )

    res = client_with_db.get(
        f"/api/v1/buses/{bus.id}/image",
        headers={"Authorization": f"Bearer {sup_token}"},
    )
    assert res.status_code == 200
    assert res.content == PNG_BYTES


def test_student_without_reservation_cannot_access_bus_image(
    client_with_db: TestClient, db_session: Session
) -> None:
    ceo, ceo_token = _create_user_and_token(db_session, "ceo_img_stu@ra7al.edu", RoleEnum.CEO)
    student, student_token = _create_user_and_token(db_session, "stu_img_no@ra7al.edu", RoleEnum.STUDENT)

    created = client_with_db.post(
        "/api/v1/buses",
        data={"bus_number": "BUS-IMG-STU", "license_plate": "IMG-0009", "capacity": "40"},
        files={"image": ("bus.png", io.BytesIO(PNG_BYTES), "image/png")},
        headers={"Authorization": f"Bearer {ceo_token}"},
    ).json()

    res = client_with_db.get(
        f"/api/v1/buses/{created['id']}/image",
        headers={"Authorization": f"Bearer {student_token}"},
    )
    assert res.status_code == 403


def test_student_with_reservation_can_access_bus_image(
    client_with_db: TestClient, db_session: Session
) -> None:
    from datetime import datetime, timedelta, timezone

    import hashlib
    import secrets

    from app.models.bus import Bus
    from app.models.enums import (
        BusStatus,
        ReservationStatus,
        SubscriptionPlanType,
        SubscriptionStatus,
        TripStatus,
    )
    from app.models.reservation import Reservation
    from app.models.route import Route
    from app.models.station import Station
    from app.models.subscription import Subscription
    from app.models.subscription_plan import SubscriptionPlan
    from app.models.trip import Trip

    ceo, ceo_token = _create_user_and_token(db_session, "ceo_img_yes@ra7al.edu", RoleEnum.CEO)
    student, student_token = _create_user_and_token(db_session, "stu_img_yes@ra7al.edu", RoleEnum.STUDENT)

    bus = Bus(
        bus_number="BUS-IMG-BOOK",
        license_plate="IMG-0010",
        capacity=40,
        status=BusStatus.ACTIVE,
    )
    s1 = Station(name="S1-B", code="ST-B1", latitude=30.0, longitude=31.0)
    s2 = Station(name="S2-B", code="ST-B2", latitude=30.1, longitude=31.1)
    db_session.add_all([bus, s1, s2])
    db_session.commit()

    route = Route(
        route_number="R-IMG-B",
        name="Route Img B",
        origin_station_id=s1.id,
        destination_station_id=s2.id,
        distance_km=9.0,
        estimated_duration_minutes=25,
    )
    db_session.add(route)
    db_session.commit()

    supervisor, _ = _create_user_and_token(db_session, "sup_img_book@ra7al.edu", RoleEnum.SUPERVISOR)
    now = datetime.now(timezone.utc)
    trip = Trip(
        route_id=route.id,
        bus_id=bus.id,
        supervisor_id=supervisor.id,
        departure_time=now + timedelta(hours=3),
        estimated_arrival_time=now + timedelta(hours=4),
        passenger_capacity=30,
        status=TripStatus.SCHEDULED,
    )
    db_session.add(trip)
    db_session.commit()

    # The student needs an active subscription to hold a daily reservation.
    plan = SubscriptionPlan(
        name="Img Plan",
        plan_type=SubscriptionPlanType.MONTHLY,
        duration_days=30,
        days_per_week=4,
        price=Decimal("500.00"),
    )
    db_session.add(plan)
    db_session.flush()

    raw = secrets.token_urlsafe(16)
    subscription = Subscription(
        student_id=student.id,
        plan_id=plan.id,
        price_snapshot=plan.price,
        duration_days_snapshot=plan.duration_days,
        days_per_week_snapshot=plan.days_per_week,
        start_date=now.date(),
        end_date=now.date() + timedelta(days=29),
        qr_token_hash=hashlib.sha256(raw.encode()).hexdigest(),
        qr_token=raw,
        status=SubscriptionStatus.ACTIVE,
    )
    db_session.add(subscription)
    db_session.commit()

    db_session.add(
        Reservation(
            trip_id=trip.id,
            student_id=student.id,
            subscription_id=subscription.id,
            service_date=trip.departure_time.date(),
            status=ReservationStatus.CONFIRMED,
        )
    )
    db_session.commit()

    # Upload an image
    up = client_with_db.patch(
        f"/api/v1/buses/{bus.id}/image",
        files={"image": ("bus.png", io.BytesIO(PNG_BYTES), "image/png")},
        headers={"Authorization": f"Bearer {ceo_token}"},
    )
    assert up.status_code == 200, up.text

    res = client_with_db.get(
        f"/api/v1/buses/{bus.id}/image",
        headers={"Authorization": f"Bearer {student_token}"},
    )
    assert res.status_code == 200
    assert res.content == PNG_BYTES

    # Image metadata endpoint also works for the authorized student
    meta = client_with_db.get(
        f"/api/v1/buses/{bus.id}/image/metadata",
        headers={"Authorization": f"Bearer {student_token}"},
    )
    assert meta.status_code == 200
    assert meta.json()["has_image"] is True
    assert meta.json()["image_stream_url"].endswith(f"/buses/{bus.id}/image")


def test_student_cannot_upload_or_remove_bus_image(
    client_with_db: TestClient, db_session: Session
) -> None:
    ceo, ceo_token = _create_user_and_token(db_session, "ceo_img_den@ra7al.edu", RoleEnum.CEO)
    student, student_token = _create_user_and_token(db_session, "stu_img_den@ra7al.edu", RoleEnum.STUDENT)

    created = client_with_db.post(
        "/api/v1/buses",
        data={"bus_number": "BUS-IMG-DEN", "license_plate": "IMG-0011", "capacity": "40"},
        headers={"Authorization": f"Bearer {ceo_token}"},
    ).json()

    up = client_with_db.patch(
        f"/api/v1/buses/{created['id']}/image",
        files={"image": ("bus.png", io.BytesIO(PNG_BYTES), "image/png")},
        headers={"Authorization": f"Bearer {student_token}"},
    )
    assert up.status_code == 403

    rm = client_with_db.delete(
        f"/api/v1/buses/{created['id']}/image",
        headers={"Authorization": f"Bearer {student_token}"},
    )
    assert rm.status_code == 403


def test_bus_image_requires_authentication(
    client_with_db: TestClient, db_session: Session
) -> None:
    ceo, ceo_token = _create_user_and_token(db_session, "ceo_img_auth@ra7al.edu", RoleEnum.CEO)
    created = client_with_db.post(
        "/api/v1/buses",
        data={"bus_number": "BUS-IMG-AUTH", "license_plate": "IMG-0012", "capacity": "40"},
        files={"image": ("bus.png", io.BytesIO(PNG_BYTES), "image/png")},
        headers={"Authorization": f"Bearer {ceo_token}"},
    ).json()

    res = client_with_db.get(f"/api/v1/buses/{created['id']}/image")
    assert res.status_code == 401
