from __future__ import annotations

import uuid

from fastapi import APIRouter, Query
from sqlalchemy import select

from app.core.deps import TenantViewer
from app.models import Forecast
from app.services import forecast

router = APIRouter(tags=["forecast"])


@router.get("/forecast", summary="Consumption and cost forecast with backtested accuracy")
def get_forecast(tenant: TenantViewer, horizon_days: int = Query(default=30, ge=1, le=365),
                 history_days: int = Query(default=90, ge=14, le=365),
                 meter_id: uuid.UUID | None = None,
                 method: str | None = Query(default=None,
                                            pattern="^(auto|moving_average|exp_smoothing|seasonal)$")):
    return forecast.generate(tenant, horizon_days=horizon_days, meter_id=meter_id,
                             history_days=history_days, method=method)
