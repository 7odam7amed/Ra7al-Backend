from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, Enum, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel
from app.models.enums import SubscriptionPlanType

if TYPE_CHECKING:
    from app.models.subscription import Subscription


class SubscriptionPlan(BaseModel):
    """SubscriptionPlan model representing available student subscription offerings."""

    __tablename__ = "subscription_plans"
    __table_args__ = (
        CheckConstraint("price > 0", name="chk_subscription_plan_price_positive"),
        CheckConstraint("duration_days > 0", name="chk_subscription_plan_duration_positive"),
        CheckConstraint(
            "(plan_type = 'DAILY' AND duration_days = 1) OR "
            "(plan_type = 'MONTHLY' AND duration_days = 30) OR "
            "(plan_type = 'TERM' AND duration_days = 90)",
            name="chk_subscription_plan_canonical_duration",
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
        unique=True,
        nullable=False,
    )
    duration_days: Mapped[int] = mapped_column(Integer, nullable=False)
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
