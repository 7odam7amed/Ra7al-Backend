import enum


class RoleEnum(enum.StrEnum):
    """User role enumeration for RBAC."""

    CEO = "CEO"
    SUPERVISOR = "SUPERVISOR"
    STUDENT = "STUDENT"


class GenderEnum(enum.StrEnum):
    """User gender enumeration."""

    MALE = "MALE"
    FEMALE = "FEMALE"


class BusStatus(enum.StrEnum):
    """Operational status of a bus."""

    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    MAINTENANCE = "MAINTENANCE"


class TripStatus(enum.StrEnum):
    """Operational status of a scheduled trip."""

    SCHEDULED = "SCHEDULED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


# Canonical alias for compatibility
TripStatusEnum = TripStatus


class ReservationStatus(enum.StrEnum):
    """Operational status of a seat reservation."""

    CONFIRMED = "CONFIRMED"
    CANCELLED = "CANCELLED"


# Canonical alias for compatibility
ReservationStatusEnum = ReservationStatus


class PaymentMethod(enum.StrEnum):
    """Supported payment methods."""

    VODAFONE_CASH = "VODAFONE_CASH"
    INSTAPAY = "INSTAPAY"
    CASH = "CASH"


# Canonical alias for compatibility
PaymentMethodEnum = PaymentMethod


class PaymentStatus(enum.StrEnum):
    """Operational status of a reservation payment."""

    PENDING = "PENDING"
    SUBMITTED = "SUBMITTED"
    VERIFIED = "VERIFIED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


# Canonical alias for compatibility
PaymentStatusEnum = PaymentStatus


class SubscriptionPlanType(enum.StrEnum):
    """Supported student subscription plan durations/types."""

    DAILY = "DAILY"
    MONTHLY = "MONTHLY"
    TERM = "TERM"


class SubscriptionStatus(enum.StrEnum):
    """Lifecycle status of a student subscription."""

    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"


class BoardingDirection(enum.StrEnum):
    """Direction of travel for trip boarding validation."""

    OUTBOUND = "OUTBOUND"
    RETURN = "RETURN"


class ReturnPickupMode(enum.StrEnum):
    """Selection mode for return trip pickup point."""

    SAME_AS_OUTBOUND = "SAME_AS_OUTBOUND"
    DIFFERENT = "DIFFERENT"


