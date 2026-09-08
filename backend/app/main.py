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

    if settings.is_production and settings.enable_scheduler and settings.task_runner == "builtin":
        logger.warning(
            "Production environment should use task_runner=celery with a "
            "dedicated beat container; the built-in scheduler is single-process "
            "and will NOT run across replicas."
        )

    sf = get_session_factory()
    async with sf() as db:
        if settings.database_url.startswith("sqlite"):
            # dev convenience: build schema when running without alembic
            from app.database import init_db

            await init_db()
        await ensure_defaults(db)
        await seeder.run_seeder(db)

    # Only start the built-in scheduler when using the builtin runner. When
    # task_runner=celery the beat container is responsible for scheduling.
    if settings.enable_scheduler and settings.task_runner == "builtin":
        scheduler.start_scheduler()
        logger.info("built-in scheduler started")
    elif settings.task_runner == "celery":
        logger.info(
            "task_runner=celery; built-in scheduler is disabled (beat container drives scheduling)."
        )

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
