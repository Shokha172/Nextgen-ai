from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Query

from app.core.deps import TenantAnalyst, TenantViewer
from app.core.timeutil import period_bounds
from app.services import anomalies

router = APIRouter(tags=["anomalies"])


@router.get("/anomalies", summary="Stored anomalies with explanations")
def list_anomalies(tenant: TenantViewer, severity: str | None = None,
                   meter_id: uuid.UUID | None = None, start: datetime | None = None,
                   end: datetime | None = None, acknowledged: bool | None = None,
                   limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0)):
    return anomalies.list_stored(tenant, start=start, end=end, severity=severity,
                                 meter_id=meter_id, acknowledged=acknowledged,
                                 limit=limit, offset=offset)


@router.post("/anomalies/detect", summary="Run detection now for a window (analyst+)")
def detect(tenant: TenantAnalyst, period: str = Query(default="last_30_days"),
           start: datetime | None = None, end: datetime | None = None,
           meter_id: uuid.UUID | None = None, persist: bool = Query(default=True)):
    """`start`/`end` (UTC) override `period`, which is what backfills and tests use."""
    if start and end:
        from app.core.errors import ValidationFailed
        if end <= start:
            raise ValidationFailed("end must be after start", code="invalid_period")
        window_start, window_end = start, end
    else:
        window_start, window_end = period_bounds(period)
    return anomalies.run_detection(tenant, start=window_start, end=window_end,
                                   meter_id=meter_id, persist=persist)


@router.post("/anomalies/{anomaly_id}/acknowledge", summary="Acknowledge an anomaly")
def acknowledge(tenant: TenantAnalyst, anomaly_id: uuid.UUID):
    row = anomalies.acknowledge(tenant, anomaly_id)
    return {"id": row.id, "acknowledged": row.acknowledged, "acknowledged_at": row.acknowledged_at}
