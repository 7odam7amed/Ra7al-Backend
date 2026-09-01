import logging

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class HealthService:
    """Service for application and infrastructure health checks."""

    @staticmethod
    def get_api_health() -> dict[str, str]:
        return {"status": "ok"}

    @staticmethod
    def check_database(db: Session) -> dict[str, str]:
        try:
            db.execute(text("SELECT 1"))
            return {"status": "ok", "database": "connected"}
        except SQLAlchemyError:
            logger.exception("Database health check failed")
            return {"status": "error", "database": "disconnected"}
