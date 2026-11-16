from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Query

from app.core.deps import TenantAdmin, TenantAnalyst, TenantViewer
from app.schemas.common import Message
from app.schemas.meter import (MeterCreate, MeterOut, MeterStats, MeterUpdate, ReadingCreate,
                              ReadingOut)
from app.services import meter_service

router = APIRouter(tags=["meters"])


@router.get("/meters", summary="List meters with readings statistics")
def list_meters(tenant: TenantViewer, search: str | None = None, department: str | None = None,
                status: str | None = Query(default=None, pattern="^(active|inactive)$"),
                page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200)):
    if search or department or status:
        rows, total = meter_service.list_meters(
            tenant.db, tenant.org_id, search=search, department=department, status=status,
            limit=page_size, offset=(page - 1) * page_size)
        items = [MeterOut.model_validate(m) for m in rows]
    else:
        stats = meter_service.meter_stats(tenant)
        total = len(stats)
        sliced = stats[(page - 1) * page_size: page * page_size]
        items = [MeterStats.model_validate(s) for s in sliced]
    return {"items": items, "total": total, "page": page, "page_size": page_size,
            "has_next": page * page_size < total}


@router.post("/meters", response_model=MeterOut, status_code=201,
             summary="Register a meter")
def create_meter(payload: MeterCreate, tenant: TenantAnalyst):
    return MeterOut.model_validate(meter_service.create_meter(tenant, payload))


@router.get("/meters/{meter_id}", response_model=MeterOut, summary="Meter detail")
def get_meter(meter_id: uuid.UUID, tenant: TenantViewer):
    return MeterOut.model_validate(meter_service.get_meter(tenant, meter_id))


@router.patch("/meters/{meter_id}", response_model=MeterOut, summary="Update a meter")
def update_meter(meter_id: uuid.UUID, payload: MeterUpdate, tenant: TenantAnalyst):
    return MeterOut.model_validate(meter_service.update_meter(tenant, meter_id, payload))


@router.delete("/meters/{meter_id}", response_model=Message, summary="Delete a meter and its readings")
def delete_meter(meter_id: uuid.UUID, tenant: TenantAdmin):
    meter_service.delete_meter(tenant, meter_id)
    return {"message": "Meter deleted"}


@router.get("/readings", summary="List readings (interval consumption in kWh)")
def list_readings(tenant: TenantViewer, meter_id: uuid.UUID | None = None,
                  start: datetime | None = None, end: datetime | None = None,
                  page: int = Query(1, ge=1), page_size: int = Query(100, ge=1, le=1000)):
    rows, total = meter_service.list_readings(
        tenant, meter_id=meter_id, start=start, end=end,
        limit=page_size, offset=(page - 1) * page_size)
    return {"items": [ReadingOut.model_validate(r) for r in rows], "total": total,
            "page": page, "page_size": page_size, "has_next": page * page_size < total}


@router.post("/meters/{meter_id}/readings", response_model=ReadingOut, status_code=201,
             summary="Add a manual interval reading (kWh)")
def add_reading(meter_id: uuid.UUID, payload: ReadingCreate, tenant: TenantAnalyst):
    return ReadingOut.model_validate(meter_service.add_manual_reading(tenant, meter_id, payload))


@router.get("/meters/{meter_id}/coverage", summary="Data coverage for a period")
def coverage(meter_id: uuid.UUID, start: datetime, end: datetime, tenant: TenantViewer):
    return meter_service.data_coverage(tenant, meter_id, start, end)
