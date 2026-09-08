"""FastAPI application entrypoint."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.router import api_router
from app.core.config import settings
from app.database import get_session_factory

logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("freebuff")


@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.services import scheduler, seeder
    from app.services.settings_store import ensure_defaults

    sf = get_session_factory()
    async with sf() as db:
        if settings.database_url.startswith("sqlite"):
            # dev convenience: build schema when running without alembic
            from app.database import init_db

            await init_db()
        await ensure_defaults(db)
        await seeder.run_seeder(db)
    if settings.enable_scheduler and settings.task_runner == "builtin":
        scheduler.start_scheduler()
        logger.info("built-in scheduler started")
    yield
    scheduler.stop_scheduler()


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description=(
        "Management & monitoring for network time-attendance devices. "
        "Discovery results follow the UNKNOWN/POSSIBLE/DETECTED/VERIFIED "
        "evidence model - nothing is ever fabricated."
    ),
    lifespan=lifespan,
    docs_url=f"{settings.api_prefix}/docs",
    redoc_url=f"{settings.api_prefix}/redoc",
    openapi_url=f"{settings.api_prefix}/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError):
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.get("/health")
async def health():
    return {"status": "ok", "app": settings.app_name, "version": settings.app_version}


app.include_router(api_router, prefix=settings.api_prefix)
