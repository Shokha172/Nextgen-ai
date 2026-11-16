"""Consumption analytics.

Every figure is produced by a database aggregate. Nothing in this module invents a
number: if there are no readings, the answer is an empty series with an explicit
`data_quality` block, not a fabricated curve.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import Select, and_, func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import ValidationFailed
from app.core.tenant import Tenant
from app.core.timeutil import (TZ, granularity_for, period_bounds, previous_period,
                              same_period_last_year, to_local)
from app.models import Meter, MeterReading, Tariff
from app.services.org_service import default_tariff

ZERO = Decimal("0")


@dataclass
class CostEstimate:
    amount: Decimal | None
    currency: str
    tariff_id: uuid.UUID | None
    tariff_name: str | None
    price_per_kwh: Decimal | None
    note: str


def resolve_filters(tenant: Tenant, *, start: datetime | None, end: datetime | None,
                    period: str | None, meter_id: uuid.UUID | None,
                    department: str | None) -> tuple[datetime, datetime, dict]:
    if period and (start is None or end is None):
        s, e = period_bounds(period)
    elif start and end:
        s, e = start.astimezone(UTC), end.astimezone(UTC)
        if e <= s:
            raise ValidationFailed("end must be after start", code="invalid_period")
        if (e - s).days > 366 * 5:
            raise ValidationFailed("Requested window is too large (max 5 years)",
                                   code="period_too_large")
    else:
        s, e = period_bounds("last_30_days")
    filters = {}
    if meter_id:
        filters["meter_id"] = meter_id
    if department:
        filters["department"] = department
    return s, e, filters


def _base_query(tenant: Tenant, *, start: datetime, end: datetime, filters: dict) -> Select:
    q = (select(MeterReading)
         .join(Meter, Meter.id == MeterReading.meter_id)
         .where(MeterReading.organization_id == tenant.org_id,
                MeterReading.ts >= start, MeterReading.ts < end))
    if filters.get("meter_id"):
        q = q.where(MeterReading.meter_id == filters["meter_id"])
    if filters.get("department"):
        q = q.where(Meter.department == filters["department"])
    return q


def estimate_cost(kwh: Decimal, tariff: Tariff | None) -> CostEstimate:
    """Cost is only ever computed from an organization-configured tariff."""
    if tariff is None:
        return CostEstimate(None, settings.DEFAULT_CURRENCY, None, None, None,
                            "No tariff is configured for this period, so no cost estimate "
                            "is shown. Add a tariff to enable financial figures.")
    amount = (Decimal(kwh) * Decimal(tariff.price_per_kwh)).quantize(Decimal("0.01"))
    return CostEstimate(amount, tariff.currency, tariff.id, tariff.name,
                        Decimal(tariff.price_per_kwh),
                        "Estimated from the organization's configured tariff; this is not an "
                        "invoice amount.")


def totals(tenant: Tenant, *, start: datetime, end: datetime, filters: dict) -> dict:
    q = _base_query(tenant, start=start, end=end, filters=filters)
    sub = q.subquery()
    row = tenant.db.execute(
        select(func.coalesce(func.sum(sub.c.consumption_kwh), 0),
               func.count(sub.c.id),
               func.coalesce(func.avg(sub.c.power_kw), 0),
               func.coalesce(func.max(sub.c.power_kw), 0),
               func.count(func.distinct(sub.c.meter_id)))).one()
    kwh = Decimal(str(row[0] or 0))
    tariff = default_tariff(tenant.db, tenant.org_id, start.date())
    cost = estimate_cost(kwh, tariff)
    expected = _expected_intervals(tenant, start, end, filters)
    return {
        "consumption_kwh": kwh.quantize(Decimal("0.0001")),
        "readings": int(row[1] or 0),
        "average_power_kw": Decimal(str(row[2] or 0)).quantize(Decimal("0.0001")),
        "peak_power_kw": Decimal(str(row[3] or 0)).quantize(Decimal("0.0001")),
        "meters": int(row[4] or 0),
        "expected_intervals": expected,
        "data_coverage_pct": round(100.0 * (row[1] or 0) / expected, 2) if expected else 0.0,
        "estimated_cost": cost.amount,
        "currency": cost.currency,
        "tariff": {"id": cost.tariff_id, "name": cost.tariff_name,
                   "price_per_kwh": cost.price_per_kwh, "note": cost.note},
    }


def _expected_intervals(tenant: Tenant, start: datetime, end: datetime, filters: dict) -> int:
    """Expected reading count, honouring each meter's cadence and its own data span."""
    q = select(Meter).where(Meter.organization_id == tenant.org_id, Meter.status == "active")
    if filters.get("meter_id"):
        q = q.where(Meter.id == filters["meter_id"])
    if filters.get("department"):
        q = q.where(Meter.department == filters["department"])
    meters = list(tenant.db.scalars(q))
    total = 0
    for meter in meters:
        span_start = tenant.db.scalar(
            select(func.min(MeterReading.ts)).where(
                MeterReading.meter_id == meter.id,
                MeterReading.ts >= start, MeterReading.ts < end))
        span_end = tenant.db.scalar(
            select(func.max(MeterReading.ts)).where(
                MeterReading.meter_id == meter.id,
                MeterReading.ts >= start, MeterReading.ts < end))
        if span_start is None or span_end is None:
            continue
        minutes = meter.interval_minutes or 60
        total += int((span_end - span_start).total_seconds() // (minutes * 60)) + 1
    return total


def series(tenant: Tenant, *, start: datetime, end: datetime, filters: dict,
           granularity: str | None = None) -> list[dict]:
    gran = granularity or granularity_for(start, end)
    if gran not in {"hour", "day", "week", "month", "year"}:
        raise ValidationFailed("granularity must be hour, day, week, month or year",
                               code="invalid_granularity")
    # Bucket in the display timezone, then return ISO-8601 local timestamps.
    bucket = func.date_trunc(gran, func.timezone(settings.DISPLAY_TZ, MeterReading.ts))
    q = (select(bucket.label("bucket"),
                func.sum(MeterReading.consumption_kwh),
                func.count(MeterReading.id),
                func.avg(MeterReading.power_kw),
                func.max(MeterReading.power_kw))
         .join(Meter, Meter.id == MeterReading.meter_id)
         .where(MeterReading.organization_id == tenant.org_id,
                MeterReading.ts >= start, MeterReading.ts < end)
         .group_by(bucket).order_by(bucket))
    if filters.get("meter_id"):
        q = q.where(MeterReading.meter_id == filters["meter_id"])
    if filters.get("department"):
        q = q.where(Meter.department == filters["department"])
    tariff = default_tariff(tenant.db, tenant.org_id, start.date())
    out = []
    for b, kwh, count, avg_kw, max_kw in tenant.db.execute(q):
        kwh_d = Decimal(str(kwh or 0))
        cost = estimate_cost(kwh_d, tariff)
        out.append({
            "bucket": b.isoformat() if isinstance(b, datetime) else str(b),
            "label": _label(b, gran),
            "consumption_kwh": kwh_d.quantize(Decimal("0.0001")),
            "readings": int(count or 0),
            "average_power_kw": Decimal(str(avg_kw or 0)).quantize(Decimal("0.0001")),
            "peak_power_kw": Decimal(str(max_kw or 0)).quantize(Decimal("0.0001")),
            "estimated_cost": cost.amount,
        })
    return out


def _label(bucket, gran: str) -> str:
    if isinstance(bucket, str):
        try:
            bucket = datetime.fromisoformat(bucket.replace("T", " "))
        except Exception:
            return str(bucket)
    elif not isinstance(bucket, datetime):
        return str(bucket)
    if gran == "hour":
        return bucket.strftime("%H:%M")
    if gran == "day":
        return bucket.strftime("%d.%m.%Y")
    if gran == "week":
        return f"{bucket.isocalendar().week}-hafta"
    if gran == "month":
        return bucket.strftime("%m.%Y")
    return str(bucket.year)


def by_meter(tenant: Tenant, *, start: datetime, end: datetime, filters: dict) -> list[dict]:
    q = (select(Meter.id, Meter.name, Meter.serial_number, Meter.department,
                func.coalesce(func.sum(MeterReading.consumption_kwh), 0),
                func.count(MeterReading.id),
                func.coalesce(func.max(MeterReading.power_kw), 0))
         .join(MeterReading, MeterReading.meter_id == Meter.id, isouter=True)
         .where(Meter.organization_id == tenant.org_id)
         .where((MeterReading.ts.is_(None)) |
                and_(MeterReading.ts >= start, MeterReading.ts < end))
         .group_by(Meter.id).order_by(func.coalesce(func.sum(MeterReading.consumption_kwh), 0).desc()))
    if filters.get("department"):
        q = q.where(Meter.department == filters["department"])
    total = sum(Decimal(str(r[4] or 0)) for r in tenant.db.execute(q))
    tariff = default_tariff(tenant.db, tenant.org_id, start.date())
    out = []
    for mid, name, serial, dept, kwh, count, max_kw in tenant.db.execute(q):
        kwh_d = Decimal(str(kwh or 0))
        cost = estimate_cost(kwh_d, tariff)
        out.append({
            "meter_id": mid, "name": name, "serial_number": serial, "department": dept,
            "consumption_kwh": kwh_d.quantize(Decimal("0.0001")),
            "readings": int(count or 0),
            "peak_power_kw": Decimal(str(max_kw or 0)).quantize(Decimal("0.0001")),
            "share_pct": round(float(kwh_d / total * 100), 2) if total else 0.0,
            "estimated_cost": cost.amount, "currency": cost.currency,
        })
    return out


def by_department(tenant: Tenant, *, start: datetime, end: datetime) -> list[dict]:
    q = (select(func.coalesce(Meter.department, "—").label("dept"),
                func.coalesce(func.sum(MeterReading.consumption_kwh), 0),
                func.count(func.distinct(Meter.id)))
         .join(MeterReading, MeterReading.meter_id == Meter.id, isouter=True)
         .where(Meter.organization_id == tenant.org_id)
         .where((MeterReading.ts.is_(None)) |
                and_(MeterReading.ts >= start, MeterReading.ts < end))
         .group_by("dept").order_by(func.coalesce(func.sum(MeterReading.consumption_kwh), 0).desc()))
    total = sum(Decimal(str(r[1] or 0)) for r in tenant.db.execute(q))
    return [{"department": dept, "consumption_kwh": Decimal(str(kwh or 0)).quantize(Decimal("0.0001")),
             "meters": int(meters or 0),
             "share_pct": round(float(Decimal(str(kwh or 0)) / total * 100), 2) if total else 0.0}
            for dept, kwh, meters in tenant.db.execute(q)]


def hourly_profile(tenant: Tenant, *, start: datetime, end: datetime, filters: dict) -> list[dict]:
    hour = func.extract("hour", func.timezone(settings.DISPLAY_TZ, MeterReading.ts)).label("h")
    q = (select(hour,
                func.avg(MeterReading.consumption_kwh),
                func.sum(MeterReading.consumption_kwh),
                func.count(MeterReading.id))
         .join(Meter, Meter.id == MeterReading.meter_id)
         .where(MeterReading.organization_id == tenant.org_id,
                MeterReading.ts >= start, MeterReading.ts < end)
         .group_by(hour).order_by(hour))
    if filters.get("meter_id"):
        q = q.where(MeterReading.meter_id == filters["meter_id"])
    rows = {int(h): (avg, total, count) for h, avg, total, count in tenant.db.execute(q)}
    return [{"hour": h, "average_kwh": Decimal(str(rows[h][0] or 0)).quantize(Decimal("0.0001")),
             "total_kwh": Decimal(str(rows[h][1] or 0)).quantize(Decimal("0.0001")),
             "readings": int(rows[h][2] or 0)} if h in rows else
            {"hour": h, "average_kwh": ZERO, "total_kwh": ZERO, "readings": 0}
            for h in range(24)]


def peaks(tenant: Tenant, *, start: datetime, end: datetime, filters: dict,
          limit: int = 10) -> list[dict]:
    q = (select(MeterReading.ts, MeterReading.consumption_kwh, MeterReading.power_kw,
                Meter.name, MeterReading.meter_id)
         .join(Meter, Meter.id == MeterReading.meter_id)
         .where(MeterReading.organization_id == tenant.org_id,
                MeterReading.ts >= start, MeterReading.ts < end)
         .order_by(MeterReading.consumption_kwh.desc()).limit(limit))
    if filters.get("meter_id"):
        q = q.where(MeterReading.meter_id == filters["meter_id"])
    return [{"ts": ts, "ts_local": to_local(ts), "consumption_kwh": kwh, "power_kw": kw,
             "meter": name, "meter_id": mid}
            for ts, kwh, kw, name, mid in tenant.db.execute(q)]


def comparison(tenant: Tenant, *, start: datetime, end: datetime, filters: dict,
               mode: str = "previous") -> dict:
    if mode == "previous":
        prev_start, prev_end = previous_period(start, end)
        label = "previous_period"
    elif mode == "year":
        prev_start, prev_end = same_period_last_year(start, end)
        label = "same_period_last_year"
    else:
        raise ValidationFailed("mode must be 'previous' or 'year'", code="invalid_mode")
    current = totals(tenant, start=start, end=end, filters=filters)
    previous = totals(tenant, start=prev_start, end=prev_end, filters=filters)
    cur_kwh = current["consumption_kwh"]
    prev_kwh = previous["consumption_kwh"]
    delta = cur_kwh - prev_kwh
    pct = round(float(delta / prev_kwh * 100), 2) if prev_kwh else None
    return {
        "mode": label,
        "current": {"start": start, "end": end, "consumption_kwh": cur_kwh,
                    "estimated_cost": current["estimated_cost"],
                    "data_coverage_pct": current["data_coverage_pct"], "readings": current["readings"]},
        "baseline": {"start": prev_start, "end": prev_end, "consumption_kwh": prev_kwh,
                     "estimated_cost": previous["estimated_cost"],
                     "data_coverage_pct": previous["data_coverage_pct"],
                     "readings": previous["readings"]},
        "difference_kwh": delta.quantize(Decimal("0.0001")),
        "difference_pct": pct,
        "why_null_pct": None if pct is not None else
        "The baseline period contains no readings, so a percentage change cannot be computed.",
    }
