"""API router aggregation."""
from fastapi import APIRouter

from app.api import attendance, auth, dashboard, devices, imports_exports, misc, networks

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(dashboard.router)
api_router.include_router(networks.router)
api_router.include_router(devices.router)
api_router.include_router(attendance.router)
api_router.include_router(imports_exports.router)
api_router.include_router(misc.router)
