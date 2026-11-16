"""Synthetic industrial dataset generator — DEMO ONLY.

Every row produced here is fabricated. It exists so the product can be demonstrated
end-to-end without a real plant, and it is created only inside organizations flagged
`is_demo = true`, which the platform refuses to serve in production.

The generator is deterministic for a given seed, which makes the demo reproducible
and lets tests assert on real numbers instead of tolerances.
"""
from __future__ import annotations

import math
import random
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.core.timeutil import TZ


@dataclass
class MeterSpec:
    name: str
    serial: str
    department: str
    base_kwh: float          # base consumption per hour
    day_factor: float        # multiplier during production hours
    weekend_factor: float
    night_factor: float
    noise_pct: float = 0.06
    max_power_kw: float | None = None
    meter_type: str = "interval"


DEFAULT_METERS: list[MeterSpec] = [
    MeterSpec("Asosiy ishlab chiqarish liniyasi", "DEMO-1001", "Ishlab chiqarish",
              420.0, 2.4, 0.35, 0.30, 0.05, 1400),
    MeterSpec("Eritish pechi", "DEMO-1002", "Metallurgiya", 610.0, 1.25, 0.80, 0.90, 0.04, 950),
    MeterSpec("Kompressor stansiyasi", "DEMO-1003", "Metallurgiya", 185.0, 1.15, 0.70, 0.75, 0.05, 300),
    MeterSpec("Konditsioner va ventilyatsiya", "DEMO-1004", "Infratuzilma", 40.0, 3.4, 0.25, 0.15, 0.08, None),
    MeterSpec("Ofis binosi", "DEMO-1005", "Administratsiya", 14.0, 3.0, 0.30, 0.20, 0.10, None),
    MeterSpec("Ombor majmuasi", "DEMO-1006", "Logistika", 22.0, 2.6, 0.45, 0.35, 0.09, None),
]

PRODUCTION_HOURS = range(8, 21)   # 08:00–20:59 local


@dataclass
class InjectedEvent:
    """A deliberately planted pattern so the demo can show detection working."""
    serial: str
    kind: str
    day_offset: int            # days before the last generated day
    start_hour: int
    hours: int
    factor: float
    label: str
    extra: dict = field(default_factory=dict)


DEFAULT_EVENTS: list[InjectedEvent] = [
    InjectedEvent("DEMO-1001", "spike", 12, 14, 3, 2.1,
                  "Uskuna nosozligi sababli asosiy liniyada keskin o'sish"),
    InjectedEvent("DEMO-1004", "outage", 8, 10, 4, 0.02,
                  "Konditsioner tizimida uzilish (iste'mol deyarli nolga tushdi)"),
    InjectedEvent("DEMO-1002", "spike", 3, 19, 2, 1.9,
                  "Eritish pechida quvvat chegarasidan oshib ketish"),
    InjectedEvent("DEMO-1003", "level_shift", 5, 0, 16, 1.55,
                  "Kompressorda uzoq muddatli rejim o'zgarishi (anomaliya emas)"),
    InjectedEvent("DEMO-1006", "night_waste", 2, 1, 5, 4.5,
                  "Omborda tungi vaqtda ortiqcha iste'mol"),
]


def hourly_kwh(spec: MeterSpec, ts: datetime, rng: random.Random,
               season_boost: float = 1.0) -> float:
    # Patterns must follow the *local* clock (Asia/Tashkent), not UTC: a plant's
    # night shift is at 02:00 local regardless of how the timestamp is stored.
    local = ts.astimezone(TZ)
    hour = local.hour
    weekday = local.weekday()
    value = spec.base_kwh
    if hour in PRODUCTION_HOURS:
        value *= spec.day_factor
    else:
        value *= spec.night_factor
    if weekday >= 5:
        value *= spec.weekend_factor
    # mild seasonal drift so the series is not flat
    value *= 1.0 + 0.08 * math.sin(local.timetuple().tm_yday / 58.0)
    value *= season_boost
    value *= 1.0 + rng.uniform(-spec.noise_pct, spec.noise_pct)
    return max(0.0, value)


def generate_readings(specs: list[MeterSpec], *, meter_ids: dict[str, uuid.UUID],
                      org_id: uuid.UUID, days: int = 120, end: datetime | None = None,
                      seed: int = 20260101,
                      events: list[InjectedEvent] | None = DEFAULT_EVENTS) -> list[dict]:
    """Return ready-to-insert meter_readings rows (UTC timestamps, hourly cadence)."""
    rng = random.Random(seed)
    end = (end or datetime.now(UTC)).replace(minute=0, second=0, microsecond=0)
    start = end - timedelta(days=days)
    events = events if events is not None else []
    event_map: dict[tuple[str, int, int], InjectedEvent] = {}
    for ev in events:
        day = (end - timedelta(days=ev.day_offset)).astimezone(TZ).date()
        for offset in range(ev.hours):
            hour = (ev.start_hour + offset) % 24
            event_map[(ev.serial, day.toordinal(), hour)] = ev

    rows: list[dict] = []
    for spec in specs:
        meter_id = meter_ids[spec.serial]
        for i in range(days * 24):
            ts = start + timedelta(hours=i)
            value = hourly_kwh(spec, ts, rng)
            local_ts = ts.astimezone(TZ)
            ev = event_map.get((spec.serial, local_ts.date().toordinal(), local_ts.hour))
            event_label = None
            if ev is not None:
                value = value * ev.factor if ev.kind != "outage" else value * ev.factor
                event_label = ev.label
            value = round(value, 4)
            rows.append({
                "organization_id": org_id, "meter_id": meter_id, "ts": ts,
                "interval_minutes": 60,
                "consumption_kwh": Decimal(str(value)),
                "power_kw": Decimal(str(round(value, 4))),   # 1-hour interval: kW == kWh/h
                "source": "seed", "quality": "ok", "created_at": datetime.now(UTC),
                "_demo_event": event_label,
            })
    return rows


def describe_events(events: list[InjectedEvent] | None = None) -> list[dict]:
    return [{"meter_serial": e.serial, "kind": e.kind, "days_ago": e.day_offset,
             "start_hour": e.start_hour, "hours": e.hours,
             "label": e.label} for e in (events if events is not None else DEFAULT_EVENTS)]
