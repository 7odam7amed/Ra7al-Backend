from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import MagicMock
import pytest

from app.exceptions.base import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ValidationError,
)
from app.models.enums import (
    GenderEnum,
    PaymentMethod,
    PaymentStatus,
    ReservationStatus,
    RoleEnum,
    TripStatus,
)
from app.models.payment import Payment
from app.models.reservation import Reservation
from app.models.trip import Trip
from app.models.user import User
from app.schemas.payment import (
    PaymentCreateRequest,
    PaymentRejectRequest,
    PaymentSubmitRequest,
)
from app.services.payment_service import PaymentService


def _create_mock_user(
    user_id: int, role: RoleEnum = RoleEnum.STUDENT, is_active: bool = True
) -> User:
    return User(
        id=user_id,
        full_name=f"User {user_id}",
        phone_number=f"+2010{user_id:08d}",
        password_hash="hash",
        gender=GenderEnum.MALE,
        role=role,
        is_active=is_active,
    )


def _create_mock_reservation(
    res_id: int,
    student_id: int,
    trip_id: int = 1,
    status: ReservationStatus = ReservationStatus.CONFIRMED,
    fare_amount: Decimal = Decimal("50.00"),
    departure_time: datetime | None = None,
) -> Reservation:
    if departure_time is None:
        departure_time = datetime.now(timezone.utc) + timedelta(hours=2)

    trip = Trip(
        id=trip_id,
        route_id=1,
        bus_id=1,
        supervisor_id=2,
        departure_time=departure_time,
        estimated_arrival_time=departure_time + timedelta(hours=1),
        passenger_capacity=30,
        fare_amount=fare_amount,
        status=TripStatus.SCHEDULED,
    )
    res = Reservation(
        id=res_id,
        trip_id=trip_id,
        student_id=student_id,
        status=status,
    )
    res.trip = trip
    return res


def test_validate_student() -> None:
    payment_repo = MagicMock()
    res_repo = MagicMock()
    trip_repo = MagicMock()
    user_repo = MagicMock()
    service = PaymentService(payment_repo, res_repo, trip_repo, user_repo)

    # Valid student
    student = _create_mock_user(1, RoleEnum.STUDENT)
    user_repo.get_by_id.return_value = student
    assert service.validate_student(1) == student

    # Missing student -> 404
    user_repo.get_by_id.return_value = None
    with pytest.raises(NotFoundError):
        service.validate_student(99)

    # Inactive student -> 422
    inactive = _create_mock_user(2, RoleEnum.STUDENT, is_active=False)
    user_repo.get_by_id.return_value = inactive
    with pytest.raises(ValidationError):
        service.validate_student(2)

    # Non-student -> 403
    supervisor = _create_mock_user(3, RoleEnum.SUPERVISOR)
    user_repo.get_by_id.return_value = supervisor
    with pytest.raises(ForbiddenError):
        service.validate_student(3)


def test_create_payment_success() -> None:
    payment_repo = MagicMock()
    res_repo = MagicMock()
    trip_repo = MagicMock()
    user_repo = MagicMock()
    service = PaymentService(payment_repo, res_repo, trip_repo, user_repo)

    student = _create_mock_user(1, RoleEnum.STUDENT)
    user_repo.get_by_id.return_value = student

    reservation = _create_mock_reservation(
        res_id=10, student_id=1, fare_amount=Decimal("60.00")
    )
    res_repo.get_by_id.return_value = reservation
    payment_repo.get_active_for_reservation_for_update.return_value = None

    expected_payment = Payment(
        id=100,
        reservation_id=10,
        student_id=1,
        amount=Decimal("60.00"),
        currency="EGP",
        method=PaymentMethod.VODAFONE_CASH,
        status=PaymentStatus.SUBMITTED,
        transaction_reference="VC-111",
    )
    payment_repo.create.return_value = expected_payment

    res = service.create_payment(
        student_id=1,
        data=PaymentCreateRequest(
            reservation_id=10,
            method=PaymentMethod.VODAFONE_CASH,
            transaction_reference="VC-111",
        ),
    )
    assert res.id == 100
    assert res.amount == Decimal("60.00")


def test_create_payment_validations() -> None:
    payment_repo = MagicMock()
    res_repo = MagicMock()
    trip_repo = MagicMock()
    user_repo = MagicMock()
    service = PaymentService(payment_repo, res_repo, trip_repo, user_repo)

    student = _create_mock_user(1, RoleEnum.STUDENT)
    user_repo.get_by_id.return_value = student

    # 1. Nonexistent reservation -> 404
    res_repo.get_by_id.return_value = None
    with pytest.raises(NotFoundError):
        service.create_payment(
            1, PaymentCreateRequest(reservation_id=99, method=PaymentMethod.CASH)
        )

    # 2. Other student's reservation -> 403
    other_res = _create_mock_reservation(res_id=10, student_id=2)
    res_repo.get_by_id.return_value = other_res
    with pytest.raises(ForbiddenError):
        service.create_payment(
            1, PaymentCreateRequest(reservation_id=10, method=PaymentMethod.CASH)
        )

    # 3. Cancelled reservation -> 422
    cancelled_res = _create_mock_reservation(
        res_id=11, student_id=1, status=ReservationStatus.CANCELLED
    )
    res_repo.get_by_id.return_value = cancelled_res
    with pytest.raises(ValidationError, match="Cannot create payment for reservation with status"):
        service.create_payment(
            1, PaymentCreateRequest(reservation_id=11, method=PaymentMethod.CASH)
        )

    # 4. Departed trip -> 422
    past_dep = datetime.now(timezone.utc) - timedelta(minutes=5)
    departed_res = _create_mock_reservation(
        res_id=12, student_id=1, departure_time=past_dep
    )
    res_repo.get_by_id.return_value = departed_res
    with pytest.raises(ValidationError, match="already departed"):
        service.create_payment(
            1, PaymentCreateRequest(reservation_id=12, method=PaymentMethod.CASH)
        )

    # 5. Duplicate active payment -> 409
    valid_res = _create_mock_reservation(res_id=13, student_id=1)
    res_repo.get_by_id.return_value = valid_res
    payment_repo.get_active_for_reservation_for_update.return_value = Payment(
        id=1, reservation_id=13, student_id=1, status=PaymentStatus.PENDING
    )
    with pytest.raises(ConflictError, match="An active payment"):
        service.create_payment(
            1, PaymentCreateRequest(reservation_id=13, method=PaymentMethod.CASH)
        )


def test_submit_payment_rules() -> None:
    payment_repo = MagicMock()
    res_repo = MagicMock()
    trip_repo = MagicMock()
    user_repo = MagicMock()
    service = PaymentService(payment_repo, res_repo, trip_repo, user_repo)

    student1 = _create_mock_user(1, RoleEnum.STUDENT)
    student2 = _create_mock_user(2, RoleEnum.STUDENT)

    # 1. Missing payment -> 404
    payment_repo.get_by_id.return_value = None
    with pytest.raises(NotFoundError):
        service.submit_payment(99, student1, PaymentSubmitRequest(transaction_reference="IP-1"))

    # 2. Non-owner student -> 403
    p_pending = Payment(
        id=5,
        reservation_id=1,
        student_id=1,
        amount=Decimal("50.00"),
        method=PaymentMethod.INSTAPAY,
        status=PaymentStatus.PENDING,
    )
    payment_repo.get_by_id.return_value = p_pending
    with pytest.raises(ForbiddenError):
        service.submit_payment(5, student2, PaymentSubmitRequest(transaction_reference="IP-1"))

    # 3. Already submitted/terminal -> 422
    p_submitted = Payment(
        id=6,
        reservation_id=1,
        student_id=1,
        amount=Decimal("50.00"),
        method=PaymentMethod.INSTAPAY,
        status=PaymentStatus.SUBMITTED,
    )
    payment_repo.get_by_id.return_value = p_submitted
    with pytest.raises(ValidationError, match="Cannot submit payment currently in status"):
        service.submit_payment(6, student1, PaymentSubmitRequest(transaction_reference="IP-1"))

    # 4. Missing transaction reference for digital payment -> 422
    payment_repo.get_by_id.return_value = p_pending
    with pytest.raises(ValidationError, match="Transaction reference is required"):
        service.submit_payment(5, student1, PaymentSubmitRequest(transaction_reference=None))

    # 5. Success
    payment_repo.get_by_id.return_value = p_pending
    service.submit_payment(5, student1, PaymentSubmitRequest(transaction_reference="IP-12345"))
    payment_repo.update_status.assert_called_once()


def test_verify_and_reject_payment_rules() -> None:
    payment_repo = MagicMock()
    res_repo = MagicMock()
    trip_repo = MagicMock()
    user_repo = MagicMock()
    service = PaymentService(payment_repo, res_repo, trip_repo, user_repo)

    student = _create_mock_user(1, RoleEnum.STUDENT)
    supervisor = _create_mock_user(2, RoleEnum.SUPERVISOR)

    p_sub = Payment(
        id=10,
        reservation_id=1,
        student_id=1,
        amount=Decimal("50.00"),
        method=PaymentMethod.VODAFONE_CASH,
        status=PaymentStatus.SUBMITTED,
    )
    payment_repo.get_by_id.return_value = p_sub

    # 1. Student cannot verify -> 403
    with pytest.raises(ForbiddenError):
        service.verify_payment(10, student)

    # 2. Supervisor can verify -> success
    service.verify_payment(10, supervisor)
    payment_repo.update_status.assert_called_once()

    # 3. Rejecting terminal payment -> 422
    p_ver = Payment(
        id=11,
        reservation_id=1,
        student_id=1,
        amount=Decimal("50.00"),
        method=PaymentMethod.VODAFONE_CASH,
        status=PaymentStatus.VERIFIED,
    )
    payment_repo.get_by_id.return_value = p_ver
    with pytest.raises(ValidationError, match="Cannot reject payment with terminal status"):
        service.reject_payment(11, supervisor, PaymentRejectRequest(rejection_reason="Fraud"))


def test_cancel_payment_rules() -> None:
    payment_repo = MagicMock()
    res_repo = MagicMock()
    trip_repo = MagicMock()
    user_repo = MagicMock()
    service = PaymentService(payment_repo, res_repo, trip_repo, user_repo)

    student1 = _create_mock_user(1, RoleEnum.STUDENT)
    student2 = _create_mock_user(2, RoleEnum.STUDENT)

    p_pending = Payment(
        id=1,
        reservation_id=1,
        student_id=1,
        status=PaymentStatus.PENDING,
    )
    payment_repo.get_by_id.return_value = p_pending

    # Non-owner student -> 403
    with pytest.raises(ForbiddenError):
        service.cancel_payment(1, student2)

    # Owner student -> OK
    service.cancel_payment(1, student1)
    payment_repo.update_status.assert_called_once()
