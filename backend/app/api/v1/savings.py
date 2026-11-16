from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.core.deps import TenantAnalyst, TenantViewer
from app.services import savings

router = APIRouter(tags=["savings"])


class SavingsRequest(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    period_start: date
    period_end: date
    baseline_method: str = Field(default="previous_period",
                                 pattern="^(previous_period|same_period_last_year)$")
    language: str = Field(default="uz", pattern="^(uz|ru|en)$")


@router.post("/savings", summary="Create a savings report (verified baseline required)")
def create(payload: SavingsRequest, tenant: TenantAnalyst):
    return savings.create(tenant, name=payload.name, period_start=payload.period_start,
                          period_end=payload.period_end,
                          baseline_method=payload.baseline_method, language=payload.language)


@router.get("/savings", summary="List savings reports")
def list_reports(tenant: TenantViewer, limit: int = 50, offset: int = 0):
    items = savings.list_reports(tenant, limit=limit, offset=offset)
    return {"items": items, "total": len(items)}


@router.get("/savings/{report_id}", summary="Savings report detail")
def get_report(report_id: uuid.UUID, tenant: TenantViewer):
    return savings.get_report(tenant, report_id)
