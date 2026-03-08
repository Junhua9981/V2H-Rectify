"""FastAPI dependency injection."""

from __future__ import annotations

from functools import lru_cache

from config.settings import Settings, get_settings
from services.craft_service import CRAFTService
from services.vlm_service import VLMService
from services.ocr_pipeline import OCRPipeline

# ---------------------------------------------------------------------------
# Singletons (set during app lifespan)
# ---------------------------------------------------------------------------

_craft_service: CRAFTService | None = None
_vlm_service: VLMService | None = None
_pipeline: OCRPipeline | None = None


def set_services(
    craft: CRAFTService,
    vlm: VLMService,
    pipeline: OCRPipeline,
) -> None:
    global _craft_service, _vlm_service, _pipeline
    _craft_service = craft
    _vlm_service = vlm
    _pipeline = pipeline


def clear_services() -> None:
    global _craft_service, _vlm_service, _pipeline
    _craft_service = None
    _vlm_service = None
    _pipeline = None


# ---------------------------------------------------------------------------
# FastAPI Depends callables
# ---------------------------------------------------------------------------

def get_craft() -> CRAFTService:
    assert _craft_service is not None, "CRAFTService not initialised"
    return _craft_service


def get_vlm() -> VLMService:
    assert _vlm_service is not None, "VLMService not initialised"
    return _vlm_service


def get_pipeline() -> OCRPipeline:
    assert _pipeline is not None, "OCRPipeline not initialised"
    return _pipeline
