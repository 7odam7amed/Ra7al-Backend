"""Shared helpers for building new-model entities in tests.

These helpers construct entities consistent with the post-refactor
transportation model: Route = container of PickupPoints, Trip = directed with
ordered TripStops, Reservation = one row per direction.
"""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import secrets
import uuid

from app.models.bus import Bus
from app.models.enums import (
    BoardingDirection,
    BusStatus,
    GenderEnum,
    RoleEnum,
    SubscriptionPlanType,
    SubscriptionStatus,
    TripDirection,
    TripStatus,
)
from app.models.pickup_point import PickupPoint
from app.models.route import Route
from app.models.subscription import Subscription
from app.models.subscription_plan import SubscriptionPlan
from app.models.trip import Trip
from app.models.trip_stop import TripStop
from app.models.user import User


def unique_suffix() -> str:
    return uuid.uuid4().hex[:8]


def make_route(session, name: str | None = None) -> Route:
    route = Route(name=name or f"Route {unique_suffix()}", is_active=True)
    session.add(route)
    session.commit()
    session.refresh(route)
    return route


def make_pickup_point(
    session, route: Route, name: str | None = None, sequence: int = 1
) -> PickupPoint:
    point = PickupPoint(
        route_id=route.id,
        name=name or f"Point {unique_suffix()}",
        address=None,
        sequence=sequence,
    )
    session.add(point)
    session.commit()
    session.refresh(point)
    return point


def make_bus(session) -> Bus:
    suffix = unique_suffix()
    bus = Bus(
        bus_number=f"BUS-{suffix}",
        license_plate=f"LP-{suffix}",
        capacity=40,
        status=BusStatus.ACTIVE,
    )
    session.add(bus)
    session.commit()
    session.refresh(bus)
    return bus


def make_user(
    session,
    role: RoleEnum = RoleEnum.STUDENT,
    gender: GenderEnum = GenderEnum.MALE,
) -> User:
    suffix = unique_suffix()
    user = User(
        full_name=f"{role.value} {suffix}",
        phone_number=f"+2010{int(suffix, 16) % 100000000:08d}",
        password_hash="hashed",
        gender=gender,
        role=role,
        is_active=True,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def make_supervisor(session) -> User:
    return make_user(session, role=RoleEnum.SUPERVISOR)


def make_student(session) -> User:
    return make_user(session, role=RoleEnum.STUDENT)


def make_subscription(
    session, student: User, days_per_week: int = 7
) -> Subscription:
    plan = SubscriptionPlan(
        name=f"Plan {unique_suffix()}",
        plan_type=SubscriptionPlanType.MONTHLY,
        duration_days=30,
        days_per_week=days_per_week,
        price=Decimal("500.00"),
        is_active=True,
    )
    session.add(plan)
    session.commit()

    raw = secrets.token_urlsafe(16)
    subscription = Subscription(
        student_id=student.id,
        plan_id=plan.id,
        price_snapshot=plan.price,
        duration_days_snapshot=plan.duration_days,
        days_per_week_snapshot=plan.days_per_week,
        start_date=date.today() - timedelta(days=1),
        end_date=date.today() + timedelta(days=29),
        qr_token_hash=hashlib.sha256(raw.encode()).hexdigest(),
        qr_token=raw,
        status=SubscriptionStatus.ACTIVE,
    )
    session.add(subscription)
    session.commit()
    session.refresh(subscription)
    return subscription


def make_trip(
    session,
    route: Route | None = None,
    bus: Bus | None = None,
    supervisor: User | None = None,
    direction: TripDirection = TripDirection.OUTBOUND,
    departure_time: datetime | None = None,
    capacity: int = 30,
    status: TripStatus = TripStatus.SCHEDULED,
    allow_overbooking: bool = False,
    points: list[PickupPoint] | None = None,
) -> Trip:
    """Create a directed trip with ordered stops from optional route points.

    Trip times are derived from the stops: first stop time = departure,
    last stop time = arrival (service-layer convention).
    """
    route = route or make_route(session)
    bus = bus or make_bus(session)
    supervisor = supervisor or make_supervisor(session)

    stop_base = departure_time or (
        datetime.now(timezone.utc) + timedelta(days=1)
    )
    if points is None:
        points = [
            make_pickup_point(session, route, sequence=i + 1) for i in range(2)
        ]
    stop_times = [stop_base + timedelta(minutes=10 * i) for i in range(len(points))]

    trip = Trip(
        route_id=route.id,
        direction=direction,
        bus_id=bus.id,
        supervisor_id=supervisor.id,
        departure_time=stop_times[0],
        estimated_arrival_time=stop_times[-1],
        passenger_capacity=capacity,
        allow_overbooking=allow_overbooking,
        status=status,
    )
    session.add(trip)
    session.commit()
    session.refresh(trip)

    for i, (point, stop_time) in enumerate(zip(points, stop_times), start=1):
        session.add(
            TripStop(
                trip_id=trip.id,
                pickup_point_id=point.id,
                stop_order=i,
                departure_time=stop_time,
            )
        )
    session.commit()
    session.refresh(trip)
    return trip


def make_reservation(
    session,
    trip: Trip,
    student: User,
    subscription: Subscription,
    service_date: date | None = None,
    status=None,
    selected_pickup_point=None,
):
    """Create a directed booking. Direction is derived from the trip."""
    from app.models.enums import ReservationStatus
    from app.models.reservation import Reservation

    direction = (
        BoardingDirection.OUTBOUND
        if trip.direction == TripDirection.OUTBOUND
        else BoardingDirection.RETURN
    )
    point = selected_pickup_point
    if point is None and trip.trip_stops:
        point = sorted(trip.trip_stops, key=lambda s: s.stop_order)[0].pickup_point

    resolved_status = status or ReservationStatus.CONFIRMED
    reservation = Reservation(
        trip_id=trip.id,
        student_id=student.id,
        subscription_id=subscription.id,
        service_date=service_date or trip.departure_time.date(),
        direction=direction,
        selected_pickup_point_id=point.id if point else None,
        status=resolved_status,
    )
    session.add(reservation)
    session.commit()
    session.refresh(reservation)
    return reservation
