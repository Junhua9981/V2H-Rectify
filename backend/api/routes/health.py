"""Health check route."""

from fastapi import APIRouter, Depends

from api.deps import get_craft, get_vlm
from api.schemas import HealthResponse
from services.craft_service import CRAFTService
from services.vlm_service import VLMService

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health(
    craft: CRAFTService = Depends(get_craft),
    vlm: VLMService = Depends(get_vlm),
) -> HealthResponse:
    return HealthResponse(
        status="ok",
        craft_loaded=craft.is_ready,
        vlm_backend=vlm.backend_name,
    )
