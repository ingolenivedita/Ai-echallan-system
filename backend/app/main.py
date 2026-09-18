"""FastAPI application entry point.

Run from the ``backend`` folder with:
    uvicorn app.main:app --reload --port 8000
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import __version__
from .config import settings
from .database import database
from .routers import (
    alerts,
    api_config,
    auth,
    cameras,
    challans,
    dashboard,
    network,
    payments,
    reports,
    rules,
    settings_router,
    users,
    vehicles,
    violations,
)
from .services.app_settings import apply_runtime_overrides, get_settings_document
from .services.pipeline import pipeline
from .services.rules_service import ensure_rules
from .utils import utcnow_iso

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("rto")

DESCRIPTION = """
Backend for the **AI Driven Camera Detected RTO E-Challan System**.

* Multi camera capture (RTSP / demo video / demo image / synthetic) - one worker thread each
* AI violation detection (Groq vision) with an OpenCV heuristic fallback
* ANPR through Plate Recognizer, SMS through Fast2SMS, payments through Razorpay Test Mode
* JWT auth with Administrator and Traffic Officer roles

All API keys are read from `backend/.env` on the server. Missing keys put the
related feature into DEMO MODE instead of faking a third-party response.
"""


@asynccontextmanager
async def lifespan(app: FastAPI):
    await database.connect()
    await ensure_rules()
    apply_runtime_overrides(await get_settings_document())

    from .bootstrap import bootstrap_if_empty

    await bootstrap_if_empty()
    await pipeline.start()
    logger.info(
        "Backend ready | database=%s | AI=%s ANPR=%s SMS=%s Payments=%s",
        database.backend,
        "on" if settings.ai_configured else "demo",
        "on" if settings.anpr_configured else "demo",
        "on" if settings.sms_configured else "demo",
        "on" if settings.payment_configured else "demo",
    )
    try:
        yield
    finally:
        await pipeline.stop()
        await database.close()


app = FastAPI(
    title="AI Driven Camera Detected RTO E-Challan System",
    description=DESCRIPTION,
    version=__version__,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for module in (
    auth,
    dashboard,
    cameras,
    violations,
    challans,
    payments,
    vehicles,
    reports,
    api_config,
    network,
    alerts,
    rules,
    users,
    settings_router,
):
    app.include_router(module.router)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={
            "detail": f"Internal server error: {type(exc).__name__}: {exc}",
            "path": request.url.path,
        },
    )


@app.get("/", tags=["System"])
async def root() -> dict:
    return {
        "application": "AI Driven Camera Detected RTO E-Challan System",
        "version": __version__,
        "docs": "/docs",
        "health": "/api/health",
    }


@app.get("/api/health", tags=["System"])
async def health() -> dict:
    from .services.camera_manager import camera_manager

    return {
        "status": "ok",
        "version": __version__,
        "environment": settings.app_env,
        "database": await database.health(),
        "cameras": camera_manager.summary(),
        "pipeline": pipeline.status(),
        "integrations": {
            "groq_ai": settings.ai_configured,
            "plate_recognizer_anpr": settings.anpr_configured,
            "sms": settings.sms_configured,
            "razorpay": settings.payment_configured,
        },
        "checked_at": utcnow_iso(),
    }
