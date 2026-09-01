from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.health import DatabaseHealthResponse, HealthResponse
from app.services.health_service import HealthService

health_router = APIRouter(tags=["Health"])


@health_router.get(
    "/health",
    response_model=HealthResponse,
    summary="API health check",
)
def health_check() -> HealthResponse:
    result = HealthService.get_api_health()
    return HealthResponse(**result)


@health_router.get(
    "/health/db",
    response_model=DatabaseHealthResponse,
    summary="Database health check",
)
def database_health_check(
    db: Session = Depends(get_db),
) -> JSONResponse | DatabaseHealthResponse:
    result = HealthService.check_database(db)
    response = DatabaseHealthResponse(**result)

    if result["status"] == "error":
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=response.model_dump(),
        )

    return response
