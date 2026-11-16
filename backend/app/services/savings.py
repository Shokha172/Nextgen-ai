"""Savings reports.

A savings figure is only produced when **both** the baseline and the current
period are adequately covered by real readings. Otherwise the report is created
with `quality='insufficient'`, no kWh and no money — the platform states what it
cannot prove instead of estimating a saving.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from sqlalchemy import select

from app.core.errors import NotFound, ValidationFailed
from app.core.tenant import Tenant
from app.core.timeutil import TZ, to_local
from app.models import SavingsReport
from app.models.enums import AuditAction
from app.services import analytics, audit, org_service

VERIFIED_COVERAGE = Decimal("90")
INDICATIVE_COVERAGE = Decimal("60")


def _window(day_from: date, day_to: date) -> tuple[datetime, datetime]:
    start = datetime.combine(day_from, time.min, tzinfo=TZ)
    end = datetime.combine(day_to + timedelta(days=1), time.min, tzinfo=TZ)
    return start, end


def _baseline_window(period_start: date, period_end: date,
                     method: str) -> tuple[date, date]:
    days = (period_end - period_start).days + 1
    if method == "same_period_last_year":
        try:
            return (period_start.replace(year=period_start.year - 1),
                    period_end.replace(year=period_end.year - 1))
        except ValueError:  # 29 February
            return (period_start.replace(year=period_start.year - 1, day=28),
                    period_end.replace(year=period_end.year - 1, day=28))
    baseline_end = period_start - timedelta(days=1)
    baseline_start = baseline_end - timedelta(days=days - 1)
    return baseline_start, baseline_end


def create(tenant: Tenant, *, name: str, period_start: date, period_end: date,
           baseline_method: str = "previous_period", language: str = "uz") -> dict:
    if period_end < period_start:
        raise ValidationFailed("period_end must not be before period_start", code="invalid_period")
    if (period_end - period_start).days > 366:
        raise ValidationFailed("A savings period may cover at most 366 days", code="period_too_large")
    if baseline_method not in {"previous_period", "same_period_last_year"}:
        raise ValidationFailed("Unknown baseline method", code="invalid_baseline_method")

    baseline_start, baseline_end = _baseline_window(period_start, period_end, baseline_method)
    cur_start, cur_end = _window(period_start, period_end)
    base_start, base_end = _window(baseline_start, baseline_end)

    current = analytics.totals(tenant, start=cur_start, end=cur_end, filters={})
    baseline = analytics.totals(tenant, start=base_start, end=base_end, filters={})

    actual_kwh = Decimal(str(current["consumption_kwh"]))
    baseline_kwh = Decimal(str(baseline["consumption_kwh"]))
    coverage_current = Decimal(str(current["data_coverage_pct"] or 0))
    coverage_baseline = Decimal(str(baseline["data_coverage_pct"] or 0))
    coverage_min = min(coverage_current, coverage_baseline)

    reasons: list[str] = []
    if baseline["readings"] == 0:
        quality, savings_kwh = "insufficient", None
        reasons.append("Baseline period has no readings, so no baseline can be established.")
    elif current["readings"] == 0:
        quality, savings_kwh = "insufficient", None
        reasons.append("Current period has no readings.")
    elif coverage_min >= VERIFIED_COVERAGE:
        quality = "verified"
        savings_kwh = (baseline_kwh - actual_kwh).quantize(Decimal("0.0001"))
    elif coverage_min >= INDICATIVE_COVERAGE:
        quality = "indicative"
        savings_kwh = (baseline_kwh - actual_kwh).quantize(Decimal("0.0001"))
        reasons.append(
            f"Coverage is {coverage_min}% (below {VERIFIED_COVERAGE}%): the saving is indicative "
            f"and is not confirmed.")
    else:
        quality, savings_kwh = "insufficient", None
        reasons.append(
            f"Coverage is {coverage_min}% (below {INDICATIVE_COVERAGE}%): not enough data to "
            f"quantify a saving.")

    tariff = org_service.default_tariff(tenant.db, tenant.org_id, period_end)
    savings_amount = None
    if quality == "verified" and savings_kwh is not None and tariff is not None:
        savings_amount = (savings_kwh * Decimal(str(tariff.price_per_kwh))).quantize(Decimal("0.0001"))
    elif quality != "insufficient" and tariff is None:
        reasons.append("No tariff is configured, so no monetary value is stated.")

    verified = quality == "verified"
    narration = (f"Baseline ({baseline_start.isoformat()} – {baseline_end.isoformat()}): "
                 f"{baseline_kwh} kWh at {coverage_baseline}% coverage. "
                 f"Current ({period_start.isoformat()} – {period_end.isoformat()}): "
                 f"{actual_kwh} kWh at {coverage_current}% coverage. "
                 + (f"Difference: {savings_kwh} kWh." if savings_kwh is not None else
                    "Difference not quantified."))

    methodology = {
        "method": baseline_method,
        "baseline_window": {"start": baseline_start.isoformat(), "end": baseline_end.isoformat()},
        "current_window": {"start": period_start.isoformat(), "end": period_end.isoformat()},
        "formula": "savings_kwh = baseline_kwh - actual_kwh",
        "coverage_current_pct": float(coverage_current),
        "coverage_baseline_pct": float(coverage_baseline),
        "verified_cutoff_pct": float(VERIFIED_COVERAGE),
        "indicative_cutoff_pct": float(INDICATIVE_COVERAGE),
        "tariff": {"name": tariff.name, "price_per_kwh": str(tariff.price_per_kwh),
                   "currency": tariff.currency} if tariff else None,
        "reasons": reasons,
        "narration": narration,
    }

    advice = {"answer": narration, "facts": {
        "baseline_kwh": baseline_kwh, "actual_kwh": actual_kwh,
        "savings_kwh": savings_kwh, "currency": current["currency"]}, "suggestions": []}
    try:
        from app.services import ai
        advice = ai.savings_advice(tenant, baseline_kwh=baseline_kwh, actual_kwh=actual_kwh,
                                   savings_kwh=savings_kwh, currency=current["currency"],
                                   language=language) or advice
    except Exception:  # narration is optional; the report itself is the deliverable
        pass

    status_reason = (
        "No savings are claimed: the baseline or current period is not adequately covered by "
        "readings, so no reduction can be substantiated."
        if quality == "insufficient" else
        (f"Verified reduction of {savings_kwh} kWh against a baseline period that is "
         f"covered at {coverage_baseline}% and a current period covered at {coverage_current}%."
         if quality == "verified" else
         f"Indicative reduction of {savings_kwh} kWh; coverage below the verified threshold, "
         f"so the figure is not confirmed."))

    methodology = {
        "method": baseline_method,
        "baseline_window": {"start": baseline_start.isoformat(), "end": baseline_end.isoformat()},
        "current_window": {"start": period_start.isoformat(), "end": period_end.isoformat()},
        "formula": "savings_kwh = baseline_kwh - actual_kwh; savings_amount = savings_kwh × tariff",
        "baseline_kwh": str(baseline_kwh),
        "actual_kwh": str(actual_kwh),
        "coverage_baseline_pct": float(coverage_baseline),
        "coverage_current_pct": float(coverage_current),
        "verified_cutoff_pct": float(VERIFIED_COVERAGE),
        "indicative_cutoff_pct": float(INDICATIVE_COVERAGE),
        "tariff": ({"name": tariff.name, "price_per_kwh": str(tariff.price_per_kwh),
                    "currency": tariff.currency} if tariff else None),
        "reasons": reasons,
        "status_reason": status_reason,
    }

    row = SavingsReport(
        organization_id=tenant.org_id, name=name, period_start=period_start,
        period_end=period_end, baseline_start=baseline_start, baseline_end=baseline_end,
        baseline_method=baseline_method, baseline_kwh=baseline_kwh, actual_kwh=actual_kwh,
        savings_kwh=savings_kwh, savings_amount=savings_amount,
        currency=current["currency"], data_coverage_pct=coverage_min, quality=quality,
        verified=verified, methodology=methodology, notes=narration, created_by=tenant.user_id)
    tenant.db.add(row)
    tenant.db.commit()
    tenant.db.refresh(row)
    audit.record(AuditAction.REPORT_EXPORT, org_id=tenant.org_id, user_id=tenant.user_id,
                 target_type="savings_report", target_id=str(row.id),
                 meta={"quality": quality, "verified": verified})
    return {
        "report": serialize(row),
        "methodology": methodology,
        "narration": advice,
        "disclaimer": (
            "This is an analytical estimate derived from the organization's own meter readings "
            "and its configured tariff. It is not an audit, not a certified measurement and "
            "verification (M&V) result, and not a financial guarantee."),
    }


def serialize(row: SavingsReport) -> dict:
    return {
        "id": row.id, "name": row.name,
        "period_start": row.period_start, "period_end": row.period_end,
        "baseline_start": row.baseline_start, "baseline_end": row.baseline_end,
        "baseline_method": row.baseline_method,
        "baseline_kwh": row.baseline_kwh, "actual_kwh": row.actual_kwh,
        "savings_kwh": row.savings_kwh, "savings_amount": row.savings_amount,
        "currency": row.currency, "data_coverage_pct": row.data_coverage_pct,
        "quality": row.quality, "verified": row.verified,
        "explanation": row.notes, "methodology": row.methodology,
        "created_at": row.created_at,
    }


def list_reports(tenant: Tenant, *, limit: int = 50, offset: int = 0) -> list[dict]:
    rows = tenant.db.scalars(select(SavingsReport).where(
        SavingsReport.organization_id == tenant.org_id).order_by(
        SavingsReport.created_at.desc()).limit(limit).offset(offset))
    return [serialize(row) for row in rows]


def get_report(tenant: Tenant, report_id: uuid.UUID) -> dict:
    row = tenant.db.scalar(select(SavingsReport).where(
        SavingsReport.id == report_id, SavingsReport.organization_id == tenant.org_id))
    if row is None:
        raise NotFound("Savings report not found")
    return serialize(row)
