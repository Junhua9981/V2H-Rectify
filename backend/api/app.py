"""FastAPI application factory with lifespan-managed services."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config.settings import get_settings
from api.deps import clear_services, set_services
from api.routes import health, corner, ocr
from api.ws import router as ws_router
from services.craft_service import CRAFTService
from services.vlm_service import VLMService
from services.ocr_pipeline import OCRPipeline

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start / stop heavy services once, share across requests."""
    settings = get_settings()

    # ---- Startup ----
    logger.info("Loading CRAFT model on %s …", settings.cuda_device)
    craft_svc = CRAFTService(device=settings.cuda_device, craft_settings=settings.craft)
    craft_svc.start()

    vlm_svc = VLMService.from_settings(settings.vlm)

    pipeline = OCRPipeline(craft_svc, vlm_svc, settings.pipeline)

    set_services(craft_svc, vlm_svc, pipeline)
    logger.info("All services ready.")

    yield

    # ---- Shutdown ----
    logger.info("Shutting down services …")
    craft_svc.stop()
    clear_services()
    logger.info("Shutdown complete.")


def create_app() -> FastAPI:
    settings = get_settings()
    
    app = FastAPI(
        title="Traditional Chinese Handwriting OCR",
        version="3.0.0",
        lifespan=lifespan,
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Routes
    prefix = "/api/v1"
    app.include_router(health.router, prefix=prefix)
    app.include_router(corner.router, prefix=prefix)
    app.include_router(ocr.router, prefix=prefix)
    app.include_router(ws_router, prefix=prefix)

    return app


# uvicorn api.app:app --host 0.0.0.0 --port 8000
app = create_app()
