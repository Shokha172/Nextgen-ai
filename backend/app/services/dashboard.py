"""Executive dashboard summary.

Assembled exclusively from services that read the database. If the organization has
no data yet, the response says so (`has_data: false`) instead of showing zeros that
look like measurements.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import func, select

from app.core.tenant import Tenant
from app.core.timeutil import period_bounds, previous_period, same_period_last_year, to_local
from app.models import Anomaly, ImportJob, Meter, MeterReading, Tariff
from app.services import analytics
from app.services.anomalies import list_stored


def summary(tenant: Tenant, *, period: str = "month",
            meter_id: uuid.UUID | None = None) -> dict:
    start, end = period_bounds(period)
    filters = {"meter_id": meter_id} if meter_id else {}
    current = analytics.totals(tenant, start=start, end=end, filters=filters)

    prev_start, prev_end = previous_period(start, end)
    previous = analytics.totals(tenant, start=prev_start, end=prev_end, filters=filters)
    ly_start, ly_end = same_period_last_year(start, end)
    last_year = analytics.totals(tenant, start=ly_start, end=ly_end, filters=filters)

    def pct(cur: Decimal, base: Decimal):
        if not base:
            return None
        return round(float((cur - base) / base * 100), 2)

    active_meters = tenant.db.scalar(select(func.count()).select_from(Meter).where(
        Meter.organization_id == tenant.org_id, Meter.status == "active")) or 0
    total_meters = tenant.db.scalar(select(func.count()).select_from(Meter).where(
        Meter.organization_id == tenant.org_id)) or 0
    last_reading_at = tenant.db.scalar(select(func.max(MeterReading.ts)).where(
        MeterReading.organization_id == tenant.org_id))
    anomalies_total = tenant.db.scalar(select(func.count()).select_from(Anomaly).where(
        Anomaly.organization_id == tenant.org_id,
        Anomaly.ts >= start, Anomaly.ts < end)) or 0
    anomalies_open = tenant.db.scalar(select(func.count()).select_from(Anomaly).where(
        Anomaly.organization_id == tenant.org_id, Anomaly.acknowledged.is_(False))) or 0
    severity_rows = tenant.db.execute(
        select(Anomaly.severity, func.count()).where(
            Anomaly.organization_id == tenant.org_id,
            Anomaly.ts >= start, Anomaly.ts < end).group_by(Anomaly.severity)).all()
    imports_recent = tenant.db.scalar(select(func.count()).select_from(ImportJob).where(
        ImportJob.organization_id == tenant.org_id,
        ImportJob.created_at >= start)) or 0
    tariffs = tenant.db.scalar(select(func.count()).select_from(Tariff).where(
        Tariff.organization_id == tenant.org_id)) or 0

    trend_series = analytics.series(tenant, start=start, end=end, filters=filters)
    by_department = analytics.by_department(tenant, start=start, end=end)
    top_anomalies = list_stored(tenant, start=start, end=end, limit=5)["items"]

    has_data = current["readings"] > 0
    completeness_notes = []
    if not has_data:
        completeness_notes.append(
            "No readings exist for this period. Import meter data to populate the dashboard.")
    if tariffs == 0:
        completeness_notes.append(
            "No tariff is configured, so monetary figures are unavailable. "
            "Metrics shown are energy-only (kWh).")
    if current["data_coverage_pct"] < 90 and has_data:
        completeness_notes.append(
            f"Data coverage is {current['data_coverage_pct']}% for this period; "
            f"trend and comparison figures are based on the readings that exist.")

    return {
        "period": {"name": period, "start": start, "end": end,
                   "start_local": to_local(start), "end_local": to_local(end),
                   "timezone": tenant.org.timezone},
        "has_data": has_data,
        "consumption": {
            "total_kwh": current["consumption_kwh"],
            "readings": current["readings"],
            "average_power_kw": current["average_power_kw"],
            "peak_power_kw": current["peak_power_kw"],
            "meters_contributing": current["meters"],
            "data_coverage_pct": current["data_coverage_pct"],
        },
        "cost": {
            "estimated": current["estimated_cost"],
            "currency": current["currency"],
            "tariff": current["tariff"],
        },
        "trend": {
            "vs_previous_period_pct": pct(current["consumption_kwh"],
                                          previous["consumption_kwh"]),
            "previous_period_kwh": previous["consumption_kwh"],
            "vs_last_year_pct": pct(current["consumption_kwh"], last_year["consumption_kwh"]),
            "last_year_kwh": last_year["consumption_kwh"],
            "previous_period_range": {"start": prev_start, "end": prev_end},
        },
        "efficiency": {
            # kWh per meter-day is a comparable intensity indicator across periods.
            "kwh_per_meter_day": _per_meter_day(current["consumption_kwh"], start, end,
                                               max(1, current["meters"])),
            "peak_to_average_ratio": _ratio(current["peak_power_kw"], current["average_power_kw"]),
        },
        "anomalies": {
            "count": anomalies_total,
            "unacknowledged": anomalies_open,
            "critical": dict(severity_rows).get("critical", 0),
            "by_severity": {sev: count for sev, count in severity_rows},
            "top": top_anomalies,
            "latest": top_anomalies,
        },
        "meters": {"active": active_meters, "total": total_meters,
                   "last_reading_at": last_reading_at},
        "imports_this_period": imports_recent,
        "series": trend_series,
        "by_department": by_department,
        "notes": completeness_notes,
        "generated_at": datetime.now(UTC),
    }


def _per_meter_day(kwh: Decimal, start: datetime, end: datetime, meters: int) -> Decimal | None:
    days = max(1, (end - start).days)
    if not kwh:
        return None
    return (Decimal(kwh) / Decimal(days * meters)).quantize(Decimal("0.0001"))


def _ratio(peak: Decimal, average: Decimal) -> Decimal | None:
    if not average:
        return None
    return (Decimal(peak) / Decimal(average)).quantize(Decimal("0.01"))
