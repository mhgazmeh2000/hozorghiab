"""Configured networks (CRUD + scan) and discovery jobs."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import Audit
from app.core.deps import get_current_user, require_roles
from app.database import get_session
from app.models import DeviceNetwork, SystemUser
from app.models.jobs import DiscoveryJob, DiscoveryResult
from app.schemas.schemas import (
    DiscoveryJobOut,
    DiscoveryResultOut,
    NetworkCreate,
    NetworkOut,
    NetworkUpdate,
)
from app.services import discovery_service

router = APIRouter(prefix="/networks", tags=["networks"])


@router.get("", response_model=list[NetworkOut])
async def list_networks(
    db: AsyncSession = Depends(get_session),
    user: SystemUser = Depends(get_current_user),
):
    return await discovery_service.list_networks(db)


@router.post("", response_model=NetworkOut, status_code=201)
async def create_network(
    body: NetworkCreate,
    request: Request,
    db: AsyncSession = Depends(get_session),
    user: SystemUser = Depends(require_roles("admin", "operator")),
):
    try:
        net = await discovery_service.add_network(
            db, body.cidr, body.label, body.exclude_ips, body.note
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    audit = Audit(db)
    await audit.record(
        "network_config", result="success",
        details={"action": "add", "cidr": body.cidr}, actor={"username": user.username},
    )
    await db.commit()
    return net


@router.put("/{network_id}", response_model=NetworkOut)
async def update_network(
    network_id: str,
    body: NetworkUpdate,
    request: Request,
    db: AsyncSession = Depends(get_session),
    user: SystemUser = Depends(require_roles("admin", "operator")),
):
    try:
        net = await discovery_service.update_network(
            db,
            network_id,
            cidr=body.cidr,
            label=body.label,
            exclude_ips=body.exclude_ips,
            enabled=body.enabled,
            note=body.note,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404 if "not found" in str(exc) else 400, detail=str(exc)) from exc
    audit = Audit(db)
    await audit.record(
        "network_config", result="success",
        details={"action": "update", "cidr": net.cidr}, actor={"username": user.username},
    )
    await db.commit()
    return net


@router.delete("/{network_id}")
async def delete_network(
    network_id: str,
    request: Request,
    db: AsyncSession = Depends(get_session),
    user: SystemUser = Depends(require_roles("admin")),
):
    try:
        await discovery_service.delete_network(db, network_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    audit = Audit(db)
    await audit.record(
        "network_config", result="success",
        details={"action": "delete", "network_id": network_id},
        actor={"username": user.username},
    )
    await db.commit()
    return {"ok": True}


@router.post("/{network_id}/scan", response_model=DiscoveryJobOut, status_code=202)
async def scan_network(
    network_id: str,
    request: Request,
    db: AsyncSession = Depends(get_session),
    user: SystemUser = Depends(require_roles("admin", "operator")),
):
    net = await db.get(DeviceNetwork, network_id)
    if net is None:
        raise HTTPException(status_code=404, detail="network not found")
    job = await discovery_service.create_discovery_job(
        db, f"network:{network_id}", requested_by=user.username
    )
    net.last_scan_at = datetime.now()
    await db.commit()
    discovery_service.start_job_in_background(job.id)
    audit = Audit(db)
    await audit.record(
        "scan", device_ip=None,
        details={"target": net.cidr, "job_id": job.id},
        actor={"username": user.username},
    )
    await db.commit()
    return job


# --------------------------------------------------------------------------
# Jobs / results
# --------------------------------------------------------------------------


@router.delete("/discovery/jobs")
async def delete_discovery_jobs(
    request: Request,
    db: AsyncSession = Depends(get_session),
    user: SystemUser = Depends(require_roles("admin", "operator")),
):
    running = (
        await db.scalars(
            select(DiscoveryJob).where(DiscoveryJob.status.in_(["PENDING", "RUNNING"]))
        )
    ).all()
    if running:
        raise HTTPException(
            status_code=409,
            detail="ابتدا کارهای در حال اجرا را لغو کنید",
        )
    result = await db.execute(delete(DiscoveryJob))
    await db.commit()
    return {"ok": True, "deleted": result.rowcount or 0}


@router.get("/discovery/jobs", response_model=list[DiscoveryJobOut])
async def list_jobs(
    limit: int = Query(50, le=200),
    db: AsyncSession = Depends(get_session),
    user: SystemUser = Depends(get_current_user),
):
    rows = (
        await db.scalars(
            select(DiscoveryJob).order_by(DiscoveryJob.created_at.desc()).limit(limit)
        )
    ).all()
    return rows


@router.get("/discovery/jobs/{job_id}", response_model=DiscoveryJobOut)
async def get_job(
    job_id: str,
    db: AsyncSession = Depends(get_session),
    user: SystemUser = Depends(get_current_user),
):
    job = await db.get(DiscoveryJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return job


@router.post("/discovery/jobs/{job_id}/cancel")
async def cancel_job(
    job_id: str,
    request: Request,
    db: AsyncSession = Depends(get_session),
    user: SystemUser = Depends(require_roles("admin", "operator")),
):
    job = await db.get(DiscoveryJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    job.cancel_requested = True
    from app.services import job_runner

    job_runner.cancel(job_id)
    await db.commit()
    audit = Audit(db)
    await audit.record(
        "discovery", result="success",
        details={"action": "cancel", "job_id": job_id},
        actor={"username": user.username},
    )
    await db.commit()
    return {"ok": True}


@router.delete("/discovery/results")
async def delete_discovery_results(
    request: Request,
    db: AsyncSession = Depends(get_session),
    user: SystemUser = Depends(require_roles("admin", "operator")),
):
    result = await db.execute(delete(DiscoveryResult))
    await db.commit()
    return {"ok": True, "deleted": result.rowcount or 0}


@router.get("/discovery/results", response_model=list[DiscoveryResultOut])
async def list_results(
    job_id: Optional[str] = None,
    reachable: Optional[bool] = None,
    limit: int = Query(100, le=500),
    db: AsyncSession = Depends(get_session),
    user: SystemUser = Depends(get_current_user),
):
    stmt = select(DiscoveryResult)
    if job_id:
        stmt = stmt.where(DiscoveryResult.discovery_job_id == job_id)
    if reachable is not None:
        stmt = stmt.where(DiscoveryResult.reachable == reachable)
    stmt = stmt.order_by(DiscoveryResult.probed_at.desc()).limit(limit)
    return list((await db.scalars(stmt)).all())
