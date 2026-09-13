from fastapi import APIRouter
from backend.app.models.schemas import HealthResponse, SectorResponse
from backend.app.services.sector_service import get_sector_rotation

router = APIRouter()

@router.get("/health", response_model=HealthResponse, tags=["system"])
def health():
    return {"status": "ok", "service": "sector-rotation-screener"}

@router.get("/sectors", response_model=list[SectorResponse], tags=["screener"])
def sectors():
    return get_sector_rotation()
