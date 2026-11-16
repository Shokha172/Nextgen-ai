"""Forecasting with honest accuracy reporting.

Methods (no heavy dependencies, fully deterministic):
  * moving_average   — mean of the last N days
  * exp_smoothing    — Holt's linear exponential smoothing (level + trend)
  * seasonal         — Holt plus multiplicative day-of-week indices, used only when
                       at least four full weeks of daily history exist

Every response carries a backtest MAPE on a hold-out window, a confidence label
derived from that MAPE and from data coverage, and an explicit limitations list.
A forecast is never presented as a certainty or as an invoice.
"""
from __future__ import annotations

import math
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import numpy as np
from sqlalchemy import func, select

from app.core.config import settings
from app.core.errors import NotFound, ValidationFailed
from app.core.tenant import Tenant
from app.core.timeutil import TZ
from app.models import Forecast, Meter, MeterReading
from app.models.enums import ForecastMethod
from app.services.analytics import estimate_cost
from app.services.org_service import default_tariff

MIN_DAYS_FOR_FORECAST = 7
MIN_DAYS_FOR_SEASONAL = 28
BACKTEST_DAYS = 14


def _daily_series(tenant: Tenant, *, start: datetime, end: datetime,
                  meter_id: uuid.UUID | None = None) -> dict[date, float]:
    day = func.date_trunc("day", func.timezone(settings.DISPLAY_TZ, MeterReading.ts))
    q = (select(day, func.sum(MeterReading.consumption_kwh), func.count(MeterReading.id))
         .where(MeterReading.organization_id == tenant.org_id,
                MeterReading.ts >= start, MeterReading.ts < end)
         .group_by(day).order_by(day))
    if meter_id:
        q = q.where(MeterReading.meter_id == meter_id)
    out: dict[date, float] = {}
    for bucket, kwh, _count in tenant.db.execute(q):
        if hasattr(bucket, "date"):
            b_date = bucket.date()
        elif isinstance(bucket, str):
            b_date = datetime.fromisoformat(bucket.split()[0]).date()
        else:
            b_date = bucket
        out[b_date] = float(kwh or 0)
    return out


def _fill_gaps(series: dict[date, float], start: date, end: date) -> tuple[list[date], np.ndarray]:
    days = [start + timedelta(days=i) for i in range((end - start).days)]
    values = np.array([series.get(d, 0.0) for d in days], dtype=float)
    return days, values


def _holt(values: np.ndarray, horizon: int, alpha: float = 0.4, beta: float = 0.1) -> np.ndarray:
    if len(values) < 2:
        base = float(values[-1]) if len(values) else 0.0
        return np.full(horizon, base)
    level = float(values[0])
    trend = float(values[1] - values[0])
    for v in values[1:]:
        prev_level = level
        level = alpha * float(v) + (1 - alpha) * (level + trend)
        trend = beta * (level - prev_level) + (1 - beta) * trend
    return np.array([level + trend * (i + 1) for i in range(horizon)])


def _moving_average(values: np.ndarray, horizon: int, window: int = 7) -> np.ndarray:
    window = min(window, len(values))
    base = float(np.mean(values[-window:])) if window else 0.0
    return np.full(horizon, base)


def _seasonal(values: np.ndarray, days: list[date], horizon: int) -> np.ndarray:
    """Holt line + multiplicative weekday indices (needs >= 4 weeks)."""
    holt = _holt(values, horizon)
    weekday_means = {}
    for v, d in zip(values, days):
        weekday_means.setdefault(d.weekday(), []).append(float(v))
    overall = float(np.mean(values)) or 1.0
    factors = {wd: (float(np.mean(vals)) / overall if overall else 1.0)
               for wd, vals in weekday_means.items()}
    last = days[-1]
    out = []
    for i in range(horizon):
        target = last + timedelta(days=i + 1)
        factor = factors.get(target.weekday(), 1.0)
        # damp the seasonal factor toward 1.0 as the horizon grows
        damping = max(0.35, 1 - i / (horizon * 2.5))
        out.append(max(0.0, holt[i] * (1 + (factor - 1) * damping)))
    return np.array(out)


def _mape(actual: np.ndarray, predicted: np.ndarray) -> float | None:
    mask = actual > 0
    if mask.sum() == 0:
        return None
    return float(np.mean(np.abs((actual[mask] - predicted[mask]) / actual[mask])) * 100)


def generate(tenant: Tenant, *, horizon_days: int = 30, meter_id: uuid.UUID | None = None,
             history_days: int = 90, method: str | None = None, persist: bool = True) -> dict:
    if not 1 <= horizon_days <= 365:
        raise ValidationFailed("horizon_days must be between 1 and 365", code="invalid_horizon")
    meter = None
    if meter_id:
        meter = tenant.db.scalar(select(Meter).where(Meter.id == meter_id,
                                                      Meter.organization_id == tenant.org_id))
        if meter is None:
            raise NotFound("Meter not found")

    now_local = datetime.now(TZ)
    end_date = now_local.date()
    start_date = end_date - timedelta(days=history_days)
    start_utc = datetime.combine(start_date, datetime.min.time(), tzinfo=TZ).astimezone(UTC)
    end_utc = datetime.combine(end_date, datetime.min.time(), tzinfo=TZ).astimezone(UTC)
    series = _daily_series(tenant, start=start_utc, end=end_utc, meter_id=meter_id)
    if not series:
        raise ValidationFailed(
            "There is no consumption history yet, so a forecast cannot be produced.",
            code="insufficient_history")

    days, values = _fill_gaps(series, start_date, end_date)
    non_zero_days = int((values > 0).sum())
    limitations: list[str] = []

    chosen = (method or "auto").lower()
    if chosen == "auto":
        if non_zero_days >= MIN_DAYS_FOR_SEASONAL:
            chosen = ForecastMethod.SEASONAL.value
        elif non_zero_days >= MIN_DAYS_FOR_FORECAST:
            chosen = ForecastMethod.EXP_SMOOTHING.value
        else:
            chosen = ForecastMethod.MOVING_AVERAGE.value
    if chosen == ForecastMethod.SEASONAL.value and non_zero_days < MIN_DAYS_FOR_SEASONAL:
        limitations.append(
            f"Seasonal model requested but only {non_zero_days} day(s) of history exist; "
            f"at least {MIN_DAYS_FOR_SEASONAL} are needed. Falling back to exponential smoothing.")
        chosen = ForecastMethod.EXP_SMOOTHING.value
    if chosen not in {m.value for m in ForecastMethod}:
        raise ValidationFailed("Unknown forecast method", code="invalid_method")

    def predict(history_days_: list[date], history_values: np.ndarray, horizon: int) -> np.ndarray:
        if chosen == ForecastMethod.MOVING_AVERAGE.value:
            return _moving_average(history_values, horizon)
        if chosen == ForecastMethod.EXP_SMOOTHING.value:
            return _holt(history_values, horizon)
        return _seasonal(history_values, history_days_, horizon)

    # ---------- backtest on the last BACKTEST_DAYS of real history ----------
    accuracy_mape = None
    if non_zero_days >= MIN_DAYS_FOR_FORECAST + 3 and len(values) > BACKTEST_DAYS + 3:
        train_days, train_values = days[:-BACKTEST_DAYS], values[:-BACKTEST_DAYS]
        actual = values[-BACKTEST_DAYS:]
        pred = predict(train_days, train_values, BACKTEST_DAYS)
        accuracy_mape = _mape(actual, pred)
        if accuracy_mape is not None:
            limitations.append(
                f"Backtest: the model was trained on data before the last {BACKTEST_DAYS} days "
                f"and scored {accuracy_mape:.1f}% MAPE against them.")
    else:
        limitations.append("Not enough history to run a backtest, so no accuracy score is shown.")

    forecast_values = np.clip(predict(days, values, horizon_days), a_min=0, a_max=None)

    # ---------- confidence: derived, never asserted ----------
    coverage = non_zero_days / max(1, len(days)) * 100
    if accuracy_mape is None:
        confidence = "low"
        limitations.append("Confidence is low because accuracy could not be measured.")
    elif accuracy_mape <= 10 and coverage >= 80:
        confidence = "high"
    elif accuracy_mape <= 25 and coverage >= 50:
        confidence = "medium"
    else:
        confidence = "low"
    if coverage < 80:
        limitations.append(
            f"Data coverage in the history window is {coverage:.0f}%; missing days make the "
            f"forecast less reliable.")
    if non_zero_days < MIN_DAYS_FOR_SEASONAL:
        limitations.append(
            "Weekly seasonality is not modelled (fewer than 28 days of history); "
            "weekday effects are therefore not reflected.")
    limitations.append("Forecasts extrapolate past behaviour only; they cannot anticipate "
                       "production changes, shutdowns, tariff revisions or weather events.")

    tariff = default_tariff(tenant.db, tenant.org_id, end_date)
    total_kwh = Decimal(str(float(np.sum(forecast_values)))).quantize(Decimal("0.0001"))
    cost = estimate_cost(total_kwh, tariff)

    points = []
    for i, value in enumerate(forecast_values, start=1):
        d = end_date + timedelta(days=i)
        kwh_d = Decimal(str(float(value))).quantize(Decimal("0.0001"))
        day_cost = estimate_cost(kwh_d, tariff)
        # Numeric JSON (not strings) keeps the contract consistent with every other
        # endpoint; the client is responsible for display formatting.
        points.append({"date": d.isoformat(), "consumption_kwh": kwh_d,
                       "estimated_cost": day_cost.amount})

    if persist:
        # JSONB is written through psycopg's stdlib json encoder, so Decimals are
        # stringified for storage (exact) while the API response stays numeric.
        points_json = [{"date": p["date"], "consumption_kwh": str(p["consumption_kwh"]),
                        "estimated_cost": str(p["estimated_cost"])
                        if p["estimated_cost"] is not None else None} for p in points]
        row = Forecast(
            organization_id=tenant.org_id, meter_id=meter.id if meter else None,
            generated_at=datetime.now(UTC), horizon_days=horizon_days, granularity="day",
            method=chosen, points=points_json, total_kwh=total_kwh,
            total_cost=cost.amount, currency=cost.currency,
            accuracy_mape=Decimal(str(round(accuracy_mape, 2))) if accuracy_mape is not None else None,
            confidence=confidence, limitations=limitations,
            params={"history_days": history_days, "non_zero_days": non_zero_days,
                    "coverage_pct": round(coverage, 1)})
        tenant.db.add(row)
        tenant.db.commit()
        tenant.db.refresh(row)
        forecast_id = row.id
    else:
        forecast_id = None

    return {
        "forecast_id": forecast_id,
        "generated_at": datetime.now(UTC),
        "horizon_days": horizon_days,
        "method": chosen,
        "granularity": "day",
        "meter_id": meter.id if meter else None,
        "total_kwh": total_kwh,
        "total_cost": cost.amount,
        "currency": cost.currency,
        "tariff": {"name": cost.tariff_name, "price_per_kwh": cost.price_per_kwh,
                   "note": cost.note},
        "accuracy_mape": round(accuracy_mape, 2) if accuracy_mape is not None else None,
        "confidence": confidence,
        "data_coverage_pct": round(coverage, 1),
        "history_days": len(days),
        "points": points,
        "limitations": limitations,
        "disclaimer": ("This is a statistical estimate, not a commitment. It is not an invoice "
                       "and must not be used as a financial guarantee."),
    }
