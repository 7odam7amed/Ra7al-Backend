from decimal import Decimal
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.enums import SubscriptionPlanType
from app.models.subscription import Subscription
from app.models.subscription_plan import SubscriptionPlan


class SubscriptionPlanRepository:
    """Repository handling database operations for subscription plans."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(self, plan_id: int) -> SubscriptionPlan | None:
        """Fetch a subscription plan by primary key ID."""
        return self.db.get(SubscriptionPlan, plan_id)

    def get_by_type(
        self, plan_type: SubscriptionPlanType, active_only: bool = True
    ) -> SubscriptionPlan | None:
        """Fetch the first plan of a given plan type."""
        stmt = select(SubscriptionPlan).where(SubscriptionPlan.plan_type == plan_type)
        if active_only:
            stmt = stmt.where(SubscriptionPlan.is_active.is_(True))
        return self.db.execute(stmt).scalars().first()

    def get_by_type_name_duration(
        self,
        plan_type: SubscriptionPlanType,
        name: str,
        duration_days: int,
        days_per_week: int,
    ) -> SubscriptionPlan | None:
        """Fetch an exact package duplicate by type, name, duration, and weekly allowance."""
        stmt = select(SubscriptionPlan).where(
            SubscriptionPlan.plan_type == plan_type,
            SubscriptionPlan.name == name.strip(),
            SubscriptionPlan.duration_days == duration_days,
            SubscriptionPlan.days_per_week == days_per_week,
        )
        return self.db.execute(stmt).scalars().first()

    def list_active(self) -> list[SubscriptionPlan]:
        """Retrieve all active subscription plans ordered by duration."""
        stmt = (
            select(SubscriptionPlan)
            .where(SubscriptionPlan.is_active.is_(True))
            .order_by(SubscriptionPlan.duration_days.asc(), SubscriptionPlan.id.asc())
        )
        return list(self.db.execute(stmt).scalars().all())

    def list_all(
        self,
        page: int = 1,
        page_size: int = 20,
        is_active: bool | None = None,
    ) -> tuple[list[SubscriptionPlan], int]:
        """Retrieve paginated subscription plans with optional status filter."""
        stmt = select(SubscriptionPlan)
        if is_active is not None:
            stmt = stmt.where(SubscriptionPlan.is_active.is_(is_active))

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = self.db.execute(count_stmt).scalar_one()

        offset = (page - 1) * page_size
        items = list(
            self.db.execute(
                stmt.order_by(
                    SubscriptionPlan.duration_days.asc(), SubscriptionPlan.id.asc()
                )
                .offset(offset)
                .limit(page_size)
            )
            .scalars()
            .all()
        )
        return items, total

    def create(
        self,
        name: str,
        plan_type: SubscriptionPlanType,
        duration_days: int,
        days_per_week: int,
        price: Decimal,
        currency: str = "EGP",
        is_active: bool = True,
    ) -> SubscriptionPlan:
        """Persist a new subscription plan."""
        plan = SubscriptionPlan(
            name=name.strip(),
            plan_type=plan_type,
            duration_days=duration_days,
            days_per_week=days_per_week,
            price=price,
            currency=currency,
            is_active=is_active,
        )
        self.db.add(plan)
        self.db.commit()
        self.db.refresh(plan)
        return plan

    def update(
        self,
        plan: SubscriptionPlan,
        name: str | None = None,
        price: Decimal | None = None,
        is_active: bool | None = None,
        duration_days: int | None = None,
        days_per_week: int | None = None,
    ) -> SubscriptionPlan:
        """Update an existing subscription plan."""
        if name is not None:
            plan.name = name.strip()
        if price is not None:
            plan.price = price
        if is_active is not None:
            plan.is_active = is_active
        if duration_days is not None:
            plan.duration_days = duration_days
        if days_per_week is not None:
            plan.days_per_week = days_per_week

        self.db.commit()
        self.db.refresh(plan)
        return plan

    def count_subscriptions_for_plan(self, plan_id: int) -> int:
        """Count total subscriptions associated with a plan."""
        stmt = select(func.count(Subscription.id)).where(Subscription.plan_id == plan_id)
        return self.db.execute(stmt).scalar_one()
