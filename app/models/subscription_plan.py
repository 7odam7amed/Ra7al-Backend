from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, Enum, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel
from app.models.enums import SubscriptionPlanType

# Upper bound for CEO-defined plan durations (about 2 years).
# Prevents accidental absurd values; the CEO enters the duration freely within this bound.
MAX_PLAN_DURATION_DAYS = 730

# Upper bound for CEO-defined weekly usage days (a week has 7 days).
MAX_PLAN_DAYS_PER_WEEK = 7

if TYPE_CHECKING:
    from app.models.subscription import Subscription


class SubscriptionPlan(BaseModel):
    """SubscriptionPlan model representing available student subscription offerings."""

    __tablename__ = "subscription_plans"
    __table_args__ = (
        CheckConstraint("price > 0", name="chk_subscription_plan_price_positive"),
        CheckConstraint("duration_days > 0", name="chk_subscription_plan_duration_positive"),
        CheckConstraint(
            f"duration_days <= {MAX_PLAN_DURATION_DAYS}",
            name="chk_subscription_plan_duration_max",
        ),
        # DAILY is flexible: duration_days is CEO-defined for every plan type
        # (no plan-type pins duration; bounds are enforced by the constraints
        # above and by the schema/service layers).
        CheckConstraint(
            "days_per_week > 0",
            name="chk_subscription_plan_days_per_week_positive",
        ),
        CheckConstraint(
            f"days_per_week <= {MAX_PLAN_DAYS_PER_WEEK}",
            name="chk_subscription_plan_days_per_week_max",
        ),
    )

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    plan_type: Mapped[SubscriptionPlanType] = mapped_column(
        Enum(
            SubscriptionPlanType,
            name="subscription_plan_type_enum",
            native_enum=False,
            values_callable=lambda obj: [e.value for e in obj],
        ),
        index=True,
        nullable=False,
    )
    duration_days: Mapped[int] = mapped_column(Integer, nullable=False)
    # Maximum number of DISTINCT usage days the student may consume per
    # calendar week (Mon-Sun, UTC). Outbound + return QR scans on the same
    # calendar day count as ONE usage day. NOT the number of QR scans.
    days_per_week: Mapped[int] = mapped_column(Integer, nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    currency: Mapped[str] = mapped_column(
        String(3),
        default="EGP",
        server_default="EGP",
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        server_default="true",
        nullable=False,
    )

    # Relationships
    subscriptions: Mapped[list["Subscription"]] = relationship(
        "Subscription", back_populates="plan"
    )

    def __repr__(self) -> str:
        return (
            f"<SubscriptionPlan id={self.id} name='{self.name}' "
            f"type={self.plan_type} price={self.price} is_active={self.is_active}>"
        )
