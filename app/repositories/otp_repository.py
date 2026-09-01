from datetime import datetime, timezone
from sqlalchemy import desc, select, update
from sqlalchemy.orm import Session

from app.models.otp_verification import OTPVerification


class OTPRepository:
    """Repository for OTP verification database operations."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def create_otp(
        self,
        user_id: int,
        phone_number: str,
        otp_hash: str,
        expires_at: datetime,
        max_attempts: int = 5,
    ) -> OTPVerification:
        """Create and persist an OTP verification entry."""
        otp_entry = OTPVerification(
            user_id=user_id,
            phone_number=phone_number.strip(),
            otp_hash=otp_hash,
            expires_at=expires_at,
            max_attempts=max_attempts,
            attempts=0,
            is_used=False,
        )
        self.db.add(otp_entry)
        self.db.commit()
        self.db.refresh(otp_entry)
        return otp_entry

    def get_latest_active_by_phone(self, phone_number: str) -> OTPVerification | None:
        """Retrieve the most recent unused OTP record for a phone number."""
        stmt = (
            select(OTPVerification)
            .where(
                OTPVerification.phone_number == phone_number.strip(),
                OTPVerification.is_used == False,  # noqa: E712
            )
            .order_by(desc(OTPVerification.id))
        )
        return self.db.scalars(stmt).first()

    def get_latest_by_phone(self, phone_number: str) -> OTPVerification | None:
        """Retrieve the latest OTP entry regardless of state."""
        stmt = (
            select(OTPVerification)
            .where(OTPVerification.phone_number == phone_number.strip())
            .order_by(desc(OTPVerification.id))
        )
        return self.db.scalars(stmt).first()

    def increment_attempts(self, otp_id: int) -> int:
        """Increment attempt count for an OTP record."""
        record = self.db.get(OTPVerification, otp_id)
        if record:
            record.attempts += 1
            self.db.commit()
            self.db.refresh(record)
            return record.attempts
        return 0

    def mark_used(self, otp_id: int) -> None:
        """Atomically mark an OTP record as consumed."""
        record = self.db.get(OTPVerification, otp_id)
        if record:
            record.is_used = True
            self.db.commit()
            self.db.refresh(record)

    def invalidate_all_for_phone(self, phone_number: str) -> None:
        """Invalidate all active OTP entries for a phone number upon resend."""
        stmt = (
            update(OTPVerification)
            .where(
                OTPVerification.phone_number == phone_number.strip(),
                OTPVerification.is_used == False,  # noqa: E712
            )
            .values(is_used=True)
        )
        self.db.execute(stmt)
        self.db.commit()
