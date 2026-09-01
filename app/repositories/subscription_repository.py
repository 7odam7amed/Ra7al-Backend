from datetime import date
from decimal import Decimal
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.models.enums import (
    ReturnPickupMode,
    SubscriptionPlanType,
    SubscriptionStatus,
)
from app.models.subscription import Subscription
from app.models.subscription_plan import SubscriptionPlan
from app.models.user import User


class SubscriptionRepository:
    """Repository handling database operations for student route subscriptions."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(
        self, subscription_id: int, eager: bool = True
    ) -> Subscription | None:
        """Fetch a single subscription by ID with optional eager loading."""
        if not eager:
            return self.db.get(Subscription, subscription_id)

        stmt = (
            select(Subscription)
            .options(
                joinedload(Subscription.student),
                joinedload(Subscription.route),
                joinedload(Subscription.plan),
                joinedload(Subscription.payment),
                joinedload(Subscription.outbound_pickup_point),
                joinedload(Subscription.return_pickup_point),
            )
            .where(Subscription.id == subscription_id)
        )
        return self.db.execute(stmt).scalars().first()

    def get_by_qr_hash(self, qr_token_hash: str) -> Subscription | None:
        """Find a subscription by its SHA-256 QR token hash."""
        stmt = (
            select(Subscription)
            .options(
                joinedload(Subscription.student),
                joinedload(Subscription.route),
                joinedload(Subscription.plan),
                joinedload(Subscription.payment),
                joinedload(Subscription.outbound_pickup_point),
                joinedload(Subscription.return_pickup_point),
            )
            .where(Subscription.qr_token_hash == qr_token_hash)
        )
        return self.db.execute(stmt).scalars().first()

    def find_overlapping_active_subscription(
        self,
        student_id: int,
        route_id: int,
        start_date: date,
        end_date: date,
        exclude_id: int | None = None,
    ) -> Subscription | None:
        """Check if an active subscription exists for student and route overlapping the date range."""
        stmt = (
            select(Subscription)
            .where(
                Subscription.student_id == student_id,
                Subscription.route_id == route_id,
                Subscription.status.in_(
                    [SubscriptionStatus.ACTIVE, SubscriptionStatus.PENDING]
                ),
                Subscription.start_date <= end_date,
                Subscription.end_date >= start_date,
            )
        )
        if exclude_id is not None:
            stmt = stmt.where(Subscription.id != exclude_id)
        return self.db.execute(stmt).scalars().first()

    def list_for_student(
        self,
        student_id: int,
        page: int = 1,
        page_size: int = 20,
        status: SubscriptionStatus | None = None,
        route_id: int | None = None,
    ) -> tuple[list[Subscription], int]:
        """Retrieve paginated subscriptions for a specific student."""
        stmt = select(Subscription).where(Subscription.student_id == student_id)
        if status is not None:
            stmt = stmt.where(Subscription.status == status)
        if route_id is not None:
            stmt = stmt.where(Subscription.route_id == route_id)

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = self.db.execute(count_stmt).scalar_one()

        offset = (page - 1) * page_size
        items = list(
            self.db.execute(
                stmt.options(
                    joinedload(Subscription.student),
                    joinedload(Subscription.route),
                    joinedload(Subscription.plan),
                    joinedload(Subscription.payment),
                    joinedload(Subscription.outbound_pickup_point),
                    joinedload(Subscription.return_pickup_point),
                )
                .order_by(Subscription.id.desc())
                .offset(offset)
                .limit(page_size)
            )
            .scalars()
            .all()
        )
        return items, total

    def list_all(
        self,
        page: int = 1,
        page_size: int = 20,
        student_id: int | None = None,
        university_id: int | None = None,
        route_id: int | None = None,
        plan_type: SubscriptionPlanType | None = None,
        status: SubscriptionStatus | None = None,
        start_date_from: date | None = None,
        start_date_to: date | None = None,
        end_date_from: date | None = None,
        end_date_to: date | None = None,
    ) -> tuple[list[Subscription], int]:
        """Retrieve paginated subscriptions for CEO administration with multi-field filters."""
        stmt = select(Subscription)

        if student_id is not None:
            stmt = stmt.where(Subscription.student_id == student_id)
        if university_id is not None:
            stmt = stmt.join(Subscription.student).where(
                User.university_id == university_id
            )
        if route_id is not None:
            stmt = stmt.where(Subscription.route_id == route_id)
        if plan_type is not None:
            stmt = stmt.join(Subscription.plan).where(
                SubscriptionPlan.plan_type == plan_type
            )
        if status is not None:
            stmt = stmt.where(Subscription.status == status)
        if start_date_from is not None:
            stmt = stmt.where(Subscription.start_date >= start_date_from)
        if start_date_to is not None:
            stmt = stmt.where(Subscription.start_date <= start_date_to)
        if end_date_from is not None:
            stmt = stmt.where(Subscription.end_date >= end_date_from)
        if end_date_to is not None:
            stmt = stmt.where(Subscription.end_date <= end_date_to)

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = self.db.execute(count_stmt).scalar_one()

        offset = (page - 1) * page_size
        items = list(
            self.db.execute(
                stmt.options(
                    joinedload(Subscription.student),
                    joinedload(Subscription.route),
                    joinedload(Subscription.plan),
                    joinedload(Subscription.payment),
                    joinedload(Subscription.outbound_pickup_point),
                    joinedload(Subscription.return_pickup_point),
                )
                .order_by(Subscription.id.desc())
                .offset(offset)
                .limit(page_size)
            )
            .scalars()
            .all()
        )
        return items, total

    def list_active_for_route_on_date(
        self, route_id: int, service_date: date
    ) -> list[Subscription]:
        """Retrieve active subscriptions for a given route valid on a specific date."""
        stmt = (
            select(Subscription)
            .options(
                joinedload(Subscription.student),
                joinedload(Subscription.route),
                joinedload(Subscription.plan),
                joinedload(Subscription.payment),
                joinedload(Subscription.outbound_pickup_point),
                joinedload(Subscription.return_pickup_point),
            )
            .where(
                Subscription.route_id == route_id,
                Subscription.status == SubscriptionStatus.ACTIVE,
                Subscription.start_date <= service_date,
                Subscription.end_date >= service_date,
            )
            .order_by(Subscription.id.asc())
        )
        return list(self.db.execute(stmt).scalars().all())

    def create(
        self,
        student_id: int,
        route_id: int,
        plan_id: int,
        price_snapshot: Decimal,
        start_date: date,
        end_date: date,
        outbound_pickup_point_id: int,
        return_pickup_point_id: int,
        return_pickup_mode: ReturnPickupMode,
        qr_token_hash: str,
        qr_token: str | None = None,
        currency: str = "EGP",
        payment_id: int | None = None,
        status: SubscriptionStatus = SubscriptionStatus.PENDING,
    ) -> Subscription:
        """Persist a new subscription."""
        sub = Subscription(
            student_id=student_id,
            route_id=route_id,
            plan_id=plan_id,
            price_snapshot=price_snapshot,
            currency=currency,
            start_date=start_date,
            end_date=end_date,
            outbound_pickup_point_id=outbound_pickup_point_id,
            return_pickup_point_id=return_pickup_point_id,
            return_pickup_mode=return_pickup_mode,
            qr_token_hash=qr_token_hash,
            qr_token=qr_token,
            payment_id=payment_id,
            status=status,
        )
        self.db.add(sub)
        self.db.commit()
        self.db.refresh(sub)
        return sub

    def update_status(
        self, subscription: Subscription, status: SubscriptionStatus
    ) -> Subscription:
        """Update subscription status."""
        subscription.status = status
        self.db.commit()
        self.db.refresh(subscription)
        return subscription

    def update_payment(
        self, subscription: Subscription, payment_id: int
    ) -> Subscription:
        """Link a payment to the subscription."""
        subscription.payment_id = payment_id
        self.db.commit()
        self.db.refresh(subscription)
        return subscription
