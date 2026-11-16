from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Query

from app.core.deps import TenantViewer
from app.services import analytics, anomalies

router = APIRouter(tags=["analytics"])


@router.get("/analytics/consumption", summary="Consumption time series and breakdowns")
def consumption(tenant: TenantViewer,
                period: str | None = Query(default=None, examples=["month"]),
                start: datetime | None = None, end: datetime | None = None,
                granularity: str | None = Query(default=None, examples=["day"]),
                meter_id: uuid.UUID | None = None, department: str | None = None):
    s, e, filters = analytics.resolve_filters(tenant, start=start, end=end, period=period,
                                              meter_id=meter_id, department=department)
    return {
        "window": {"start": s, "end": e, "granularity": granularity or "auto"},
        "totals": analytics.totals(tenant, start=s, end=e, filters=filters),
        "series": analytics.series(tenant, start=s, end=e, filters=filters, granularity=granularity),
        "by_meter": analytics.by_meter(tenant, start=s, end=e, filters=filters),
        "by_department": analytics.by_department(tenant, start=s, end=e),
        "hourly_profile": analytics.hourly_profile(tenant, start=s, end=e, filters=filters),
        "peaks": analytics.peaks(tenant, start=s, end=e, filters=filters, limit=10),
    }


@router.get("/analytics/comparison", summary="Period-over-period comparison")
def comparison(tenant: TenantViewer, period: str = Query(default="month"),
               mode: str = Query(default="previous", pattern="^(previous|year)$"),
               meter_id: uuid.UUID | None = None, department: str | None = None):
    s, e, filters = analytics.resolve_filters(tenant, start=None, end=None, period=period,
                                              meter_id=meter_id, department=department)
    return analytics.comparison(tenant, start=s, end=e, filters=filters, mode=mode)


@router.get("/analytics/meters", summary="Consumption ranked by meter")
def meters_breakdown(tenant: TenantViewer, period: str = Query(default="month"),
                     start: datetime | None = None, end: datetime | None = None,
                     department: str | None = None):
    s, e, filters = analytics.resolve_filters(tenant, start=start, end=end, period=period,
                                              meter_id=None, department=department)
    return {"window": {"start": s, "end": e},
            "items": analytics.by_meter(tenant, start=s, end=e, filters=filters)}


@router.get("/analytics/hourly", summary="Average consumption by hour of day (local time)")
def hourly(tenant: TenantViewer, period: str = Query(default="last_30_days"),
           meter_id: uuid.UUID | None = None):
    s, e, filters = analytics.resolve_filters(tenant, start=None, end=None, period=period,
                                              meter_id=meter_id, department=None)
    return {"window": {"start": s, "end": e},
            "items": analytics.hourly_profile(tenant, start=s, end=e, filters=filters)}


@router.get("/analytics/anomalies", summary="Stored anomalies (explainable)")
def analytics_anomalies(tenant: TenantViewer, severity: str | None = None,
                        meter_id: uuid.UUID | None = None,
                        start: datetime | None = None, end: datetime | None = None,
                        limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0)):
    return anomalies.list_stored(tenant, start=start, end=end, severity=severity,
                                 meter_id=meter_id, limit=limit, offset=offset)
