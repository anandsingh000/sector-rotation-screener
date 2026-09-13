from pydantic import BaseModel, Field

class HealthResponse(BaseModel):
    status: str
    service: str

class SectorResponse(BaseModel):
    sector: str
    relative_strength: float = Field(..., description="Relative strength score")
    momentum: float
    trend: str
    rank: int
