from __future__ import annotations

import uuid

from fastapi import APIRouter, Query

from app.core.deps import TenantViewer
from app.services import dashboard

router = APIRouter(tags=["dashboard"])


@router.get("/dashboard/summary", summary="Executive dashboard summary for the active organization")
def summary(tenant: TenantViewer,
            period: str = Query(default="month",
                                examples=["today", "week", "month", "last_month", "year"]),
            meter_id: uuid.UUID | None = None):
    return dashboard.summary(tenant, period=period, meter_id=meter_id)
