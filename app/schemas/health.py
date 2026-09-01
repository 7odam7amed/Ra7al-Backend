from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str = Field(..., examples=["ok"])


class DatabaseHealthResponse(BaseModel):
    status: str = Field(..., examples=["ok", "error"])
    database: str = Field(..., examples=["connected", "disconnected"])
