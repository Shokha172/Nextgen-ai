"""Explainable anomaly detection.

Four detectors, all statistical and all explainable:
  1. time_of_day      — each interval compared to the same hour's baseline (median/MAD)
  2. rolling_zscore   — interval vs a trailing rolling median, robust z-score
  3. threshold        — meter power ceiling (`max_power_kw`)
  4. drop             — consumption far below baseline (outage or meter fault)

Anti-false-positive guards (a legitimate production increase must not be flagged):
  * a minimum relative deviation (organization setting, default 25%) *and* a robust
    z-score above the organization threshold must both hold;
  * a minimum absolute deviation, so tiny intervals never produce noise;
  * a **sustained-shift guard**: a deviation lasting `sustained_intervals` intervals
    or more is a level change, not an anomaly, and is reported separately;
  * night-time intervals are compared with night-time baselines only (time-of-day),
    so ramping production at 06:00 is not mistaken for waste.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import numpy as np
import pandas as pd
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.errors import NotFound
from app.core.tenant import Tenant
from app.models import Anomaly, Meter, MeterReading
from app.models.enums import AnomalyMethod, Severity

MIN_ABSOLUTE_KWH = Decimal("5")          # ignore deviations smaller than this
SUSTAINED_INTERVALS = 6                  # >= 6 consecutive -> level shift, not anomaly
MAD_SCALE = 0.6745                       # consistency constant for median absolute deviation

EXPLANATIONS = {
    "uz": {
        "time_of_day": ("{ts} da {observed} kWh iste'mol qilindi, kutilgan qiymat {expected} kWh "
                        "(shu soat uchun {days} kunlik mediana). Og'ish {pct}%."),
        "rolling_zscore": ("{ts} da {observed} kWh iste'mol qilindi; oxirgi {window} interval "
                           "bo'yicha mediana {expected} kWh. Robust z-ball {z}. Og'ish {pct}%."),
        "threshold": ("{ts} da o'rtacha quvvat {kw} kVt bo'lib, hisoblagich chegarasi "
                      "{limit} kVt dan oshdi (o'lchangan {observed} kWh / {interval} daqiqa)."),
        "drop": ("{ts} da iste'mol {observed} kWh, kutilgan {expected} kWh. Bu {pct}% past — "
                 "uzilish yoki hisoblagich nosozligi bo'lishi mumkin."),
    },
    "ru": {
        "time_of_day": ("{ts}: потребление {observed} кВт·ч, ожидалось {expected} кВт·ч "
                        "(медиана за {days} дней для этого часа). Отклонение {pct}%."),
        "rolling_zscore": ("{ts}: потребление {observed} кВт·ч; медиана последних {window} "
                           "интервалов {expected} кВт·ч. Робастный z-score {z}. Отклонение {pct}%."),
        "threshold": ("{ts}: средняя мощность {kw} кВт превысила лимит счётчика {limit} кВт "
                      "({observed} кВт·ч за {interval} мин)."),
        "drop": ("{ts}: потребление {observed} кВт·ч против ожидаемых {expected} кВт·ч — "
                 "на {pct}% ниже нормы (возможен простой или неисправность счётчика)."),
    },
    "en": {
        "time_of_day": ("{ts}: {observed} kWh consumed vs expected {expected} kWh "
                        "(median for this hour over {days} days). Deviation {pct}%."),
        "rolling_zscore": ("{ts}: {observed} kWh consumed vs rolling median {expected} kWh over "
                           "the last {window} intervals. Robust z-score {z}. Deviation {pct}%."),
        "threshold": ("{ts}: average power {kw} kW exceeded the meter ceiling of {limit} kW "
                      "({observed} kWh over {interval} min)."),
        "drop": ("{ts}: {observed} kWh vs expected {expected} kWh — {pct}% below baseline "
                 "(possible outage or meter fault)."),
    },
}


@dataclass
class DetectionResult:
    meter_id: uuid.UUID
    flagged: list[dict] = field(default_factory=list)
    suppressed_sustained: int = 0
    baseline_days: int = 0
    analysed_intervals: int = 0
    notes: list[str] = field(default_factory=list)


def _severity(deviation_pct: float, *, direction: str) -> str:
    pct = abs(deviation_pct)
    if direction == "drop":
        return Severity.INFO.value if pct < 60 else Severity.LOW.value
    if pct >= 100:
        return Severity.CRITICAL.value
    if pct >= 60:
        return Severity.HIGH.value
    if pct >= 35:
        return Severity.MEDIUM.value
    return Severity.LOW.value


class _SafeDict(dict):
    """Formatting must never crash an explanation: unknown fields render as '—'."""

    def __missing__(self, key):  # noqa: D105
        return "—"


def _explain(method: str, *, ts_local: datetime, observed: Decimal, expected: Decimal,
             deviation_pct: float, extra: dict) -> dict:
    payload = _SafeDict({
        "ts": ts_local.strftime("%d.%m.%Y %H:%M"),
        "observed": f"{observed:.1f}",
        "expected": f"{expected:.1f}",
        "pct": f"{abs(deviation_pct):.1f}",
        "z": f"{extra.get('z'):.2f}" if isinstance(extra.get("z"), (int, float)) else "—",
        "window": extra.get("window", "—"),
        "days": extra.get("days", "—"),
        "kw": extra.get("kw", "—"),
        "limit": extra.get("limit", "—"),
        "interval": extra.get("interval", "—"),
    })
    payload.update(extra)
    out = {}
    for lang, templates in EXPLANATIONS.items():
        key = method if method in templates else ("drop" if deviation_pct < 0 else "time_of_day")
        out[lang] = templates[key].format_map(payload)
    return out


def load_frame(tenant: Tenant, meter_id: uuid.UUID, start: datetime, end: datetime) -> pd.DataFrame:
    rows = tenant.db.execute(
        select(MeterReading.ts, MeterReading.consumption_kwh, MeterReading.power_kw,
               MeterReading.interval_minutes)
        .where(MeterReading.organization_id == tenant.org_id,
               MeterReading.meter_id == meter_id,
               MeterReading.ts >= start, MeterReading.ts < end)
        .order_by(MeterReading.ts))
    data = [(ts, float(kwh), float(kw) if kw is not None else np.nan, minutes)
            for ts, kwh, kw, minutes in rows]
    df = pd.DataFrame(data, columns=["ts", "kwh", "kw", "interval_minutes"])
    if not df.empty:
        from app.core.timeutil import TZ
        def _to_local(t):
            if isinstance(t, str):
                t = datetime.fromisoformat(t)
            if hasattr(t, "tzinfo") and t.tzinfo is None:
                if hasattr(t, "tz_localize"):
                    t = t.tz_localize(UTC)
                else:
                    t = t.replace(tzinfo=UTC)
            elif hasattr(t, "tzinfo") and t.tzinfo is not None:
                if hasattr(t, "tz_convert"):
                    t = t.tz_convert(UTC)
                else:
                    t = t.astimezone(UTC)
            if hasattr(t, "tz_convert"):
                return t.tz_convert(TZ)
            return t.astimezone(TZ)
        df["ts_local"] = df["ts"].apply(_to_local)
        df["hour"] = df["ts_local"].apply(lambda t: t.hour)
        df["day"] = df["ts_local"].apply(lambda t: t.date())
        # Industrial sites run different regimes on weekdays and weekends; a baseline
        # that mixes them makes every weekday look like waste and every weekend like
        # an outage. Regimes are therefore modelled separately.
        df["is_weekend"] = df["ts_local"].apply(lambda t: t.weekday() >= 5)
    return df


def _same_hour_rolling_baseline(df: pd.DataFrame, *, lookback_days: int = 7,
                               min_points: int = 4) -> pd.DataFrame:
    """Median and MAD of the same hour of day over the *previous* days.

    Strictly backward looking (no leakage from the interval being tested) and
    seasonal by construction, which is what keeps shift ramps out of the results.
    """
    medians = np.full(len(df), np.nan)
    mads = np.full(len(df), np.nan)
    positions = np.arange(len(df))
    for _key, idx in df.groupby(["hour", "is_weekend"]).groups.items():
        pos = np.sort(np.asarray(idx))
        vals = df["kwh"].to_numpy()[pos]
        for j, p in enumerate(pos):
            window = vals[max(0, j - lookback_days):j]
            if len(window) >= min_points:
                med = float(np.median(window))
                medians[p] = med
                mads[p] = float(np.median(np.abs(window - med)))
    return pd.DataFrame({"median": medians, "mad": mads}, index=positions)


def _finite(value):
    """JSONB has no Infinity/NaN: statistics that overflow become null."""
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if f != f or f in (float("inf"), float("-inf")):
        return None
    return round(f, 3)


def _runs(mask: np.ndarray) -> list[tuple[int, int]]:
    runs, start = [], None
    for i, flag in enumerate(mask):
        if flag and start is None:
            start = i
        elif not flag and start is not None:
            runs.append((start, i - 1))
            start = None
    if start is not None:
        runs.append((start, len(mask) - 1))
    return runs


def detect_meter(tenant: Tenant, meter: Meter, df: pd.DataFrame, *,
                 flagged_only_after: datetime | None = None) -> DetectionResult:
    result = DetectionResult(meter_id=meter.id, analysed_intervals=len(df))
    if df.empty:
        result.notes.append("No readings in the requested window.")
        return result
    df = df.sort_values("ts").reset_index(drop=True)
    df["kwh"] = df["kwh"].astype(float)
    result.baseline_days = int(df["day"].nunique())

    z_threshold = float(tenant.org.anomaly_z_threshold or 3.0)
    min_dev_pct = float(tenant.org.anomaly_min_deviation_pct or 25.0)

    # ---------- detector 1: time-of-day baseline (median + MAD per hour) ----------
    grouped = df.groupby(["hour", "is_weekend"])
    stats = pd.DataFrame({
        "median": grouped["kwh"].median(),
        "count": grouped["kwh"].count(),
        "days": grouped["day"].nunique(),
    })
    stats["mad"] = grouped["kwh"].apply(
        lambda s: float(np.median(np.abs(s - np.median(s)))))
    candidates: dict[int, dict] = {}

    def _stat(hour: int, is_weekend: bool):
        key = (hour, is_weekend)
        return stats.loc[key] if key in stats.index else None

    for i, row in df.iterrows():
        hour_stat = _stat(row["hour"], row["is_weekend"])
        if hour_stat is None or hour_stat["count"] < 3:
            continue
        median = float(hour_stat["median"])
        mad = float(hour_stat["mad"])
        if median <= 0:
            continue
        deviation = (row["kwh"] - median) / median * 100.0
        sigma = mad * 1.4826 if mad > 0 else None
        z = (row["kwh"] - median) / sigma if sigma else float("inf")
        if abs(deviation) < min_dev_pct or abs(row["kwh"] - median) < float(MIN_ABSOLUTE_KWH):
            continue
        if sigma is not None and abs(z) < z_threshold:
            continue
        candidates[i] = {
            "method": AnomalyMethod.TIME_OF_DAY.value,
            "expected": median, "deviation_pct": deviation, "z": z,
            "extra": {"days": int(hour_stat["days"])},
        }

    # ---------- detector 2: same-hour rolling robust z-score ----------
    # Comparing against a plain 24-interval window would flag every shift change
    # (a night-to-day ramp is not an anomaly). The baseline is therefore built from
    # the same hour of day on the preceding days only.
    lookback_days = 7
    seasonal = _same_hour_rolling_baseline(df, lookback_days=lookback_days)
    for i in range(len(df)):
        if i in candidates:
            continue
        med, mad = seasonal["median"].iloc[i], seasonal["mad"].iloc[i]
        if pd.isna(med) or med <= 0:
            continue
        observed = float(df["kwh"].iloc[i])
        deviation = (observed - med) / med * 100.0
        sigma = (float(mad) * 1.4826) if not pd.isna(mad) and mad > 0 else None
        z = (observed - med) / sigma if sigma else None
        if abs(deviation) < min_dev_pct or abs(observed - med) < float(MIN_ABSOLUTE_KWH):
            continue
        if sigma is None:
            # No dispersion measure for this hour yet: require a much larger jump.
            if abs(deviation) < 2 * min_dev_pct:
                continue
        elif abs(z) < z_threshold:
            continue
        candidates[i] = {"method": AnomalyMethod.ROLLING_ZSCORE.value, "expected": float(med),
                         "deviation_pct": deviation, "z": z,
                         "extra": {"window": lookback_days, "z": z}}

    # ---------- detector 3: meter power ceiling ----------
    if meter.max_power_kw:
        limit = float(meter.max_power_kw)
        for i, row in df.iterrows():
            kw = row["kw"]
            if pd.isna(kw):
                kw = row["kwh"] / (row["interval_minutes"] / 60.0)
            if kw and kw > limit:
                observed = float(row["kwh"])
                stat_row = _stat(row["hour"], row["is_weekend"])
                median = float(stat_row["median"]) if stat_row is not None else observed
                candidates[i] = {
                    "method": AnomalyMethod.THRESHOLD.value, "expected": max(median, observed / 1.0001),
                    "deviation_pct": (observed - median) / median * 100.0 if median else 0.0,
                    "z": None,
                    "extra": {"kw": f"{kw:.1f}", "limit": f"{limit:g}",
                              "interval": int(row["interval_minutes"])},
                }

    # ---------- detector 4: consumption drop ----------
    for i, row in df.iterrows():
        if i in candidates:
            continue
        stat_row = _stat(row["hour"], row["is_weekend"])
        if stat_row is None or stat_row["count"] < 3:
            continue
        median = float(stat_row["median"])
        if median < 10 * float(MIN_ABSOLUTE_KWH):
            continue
        observed = float(row["kwh"])
        deviation = (observed - median) / median * 100.0
        if deviation <= -max(60.0, min_dev_pct):
            candidates[i] = {"method": AnomalyMethod.TIME_OF_DAY.value, "expected": median,
                             "deviation_pct": deviation, "z": None,
                             "extra": {"days": int(stat_row["days"]),
                                       "regime": "weekend" if row["is_weekend"] else "weekday"}}

    # ---------- sustained-shift guard ----------
    mask = np.zeros(len(df), dtype=bool)
    for i in candidates:
        mask[i] = True
    sustained: set[int] = set()
    for start_i, end_i in _runs(mask):
        if (end_i - start_i + 1) >= SUSTAINED_INTERVALS:
            sustained.update(range(start_i, end_i + 1))
            result.suppressed_sustained += 1
    if sustained:
        result.notes.append(
            f"{len(sustained)} interval(s) around a sustained level change were not flagged: "
            f"runs of {SUSTAINED_INTERVALS}+ intervals indicate a new operating regime "
            f"(e.g. a new production shift) rather than an anomaly.")

    for i in sorted(candidates):
        if i in sustained:
            continue
        cand = candidates[i]
        row = df.iloc[i]
        observed = float(row["kwh"])
        expected = float(cand["expected"])
        deviation = float(cand["deviation_pct"])
        direction = "drop" if deviation < 0 else "rise"
        ts_local = row["ts_local"]
        if flagged_only_after and row["ts"] < flagged_only_after:
            continue
        result.flagged.append({
            "ts": row["ts"], "ts_local": ts_local,
            "observed_kwh": Decimal(f"{observed:.4f}"),
            "expected_kwh": Decimal(f"{expected:.4f}"),
            "deviation_pct": Decimal(f"{deviation:.2f}"),
            "severity": _severity(deviation, direction=direction),
            "method": cand["method"],
            "direction": direction,
            "explanation": _explain(cand["method"], ts_local=ts_local,
                                    observed=Decimal(f"{observed:.1f}"),
                                    expected=Decimal(f"{expected:.1f}"),
                                    deviation_pct=deviation, extra=cand["extra"]),
            "details": {"z_score": _finite(cand["z"]),
                        "z_threshold": z_threshold, "min_deviation_pct": min_dev_pct,
                        "hour_of_day": int(row["hour"]),
                        "interval_minutes": int(row["interval_minutes"]), **cand["extra"]},
        })
    return result


def run_detection(tenant: Tenant, *, start: datetime, end: datetime,
                  meter_id: uuid.UUID | None = None, persist: bool = True) -> dict:
    """Detect anomalies for one meter or the whole organization; optionally persist."""
    q = select(Meter).where(Meter.organization_id == tenant.org_id, Meter.status == "active")
    if meter_id:
        q = q.where(Meter.id == meter_id)
    meters = list(tenant.db.scalars(q))
    if meter_id and not meters:
        raise NotFound("Meter not found")

    all_flagged: list[dict] = []
    per_meter = []
    notes: list[str] = []
    for meter in meters:
        df = load_frame(tenant, meter.id, start, end)
        res = detect_meter(tenant, meter, df)
        per_meter.append({"meter_id": meter.id, "meter": meter.name,
                          "analysed_intervals": res.analysed_intervals,
                          "baseline_days": res.baseline_days,
                          "flagged": len(res.flagged),
                          "suppressed_sustained_runs": res.suppressed_sustained})
        notes.extend(res.notes)
        for item in res.flagged:
            item["meter_id"], item["meter"] = meter.id, meter.name
            all_flagged.append(item)

    if persist and all_flagged:
        rows = [{"organization_id": tenant.org_id, "meter_id": item["meter_id"],
                 "ts": item["ts"], "observed_kwh": item["observed_kwh"],
                 "expected_kwh": item["expected_kwh"], "deviation_pct": item["deviation_pct"],
                 "severity": item["severity"], "method": item["method"],
                 "explanation": item["explanation"]["uz"], "details": {**item["details"],
                                                                      "explanations": item["explanation"]},
                 "created_at": datetime.now(UTC)} for item in all_flagged]
        stmt = pg_insert(Anomaly).values(rows).on_conflict_do_nothing(
            index_elements=["meter_id", "ts", "method"])
        tenant.db.execute(stmt)
        tenant.db.commit()

    if persist and all_flagged:
        from app.services import notifications
        notifications.notify_anomalies(tenant, all_flagged)

    severity_counts: dict[str, int] = {}
    for item in all_flagged:
        severity_counts[item["severity"]] = severity_counts.get(item["severity"], 0) + 1
    return {
        "window": {"start": start, "end": end},
        "anomalies": all_flagged,
        "count": len(all_flagged),
        "severity_counts": severity_counts,
        "per_meter": per_meter,
        "notes": sorted(set(notes)),
        "thresholds": {"z": tenant.org.anomaly_z_threshold,
                       "min_deviation_pct": tenant.org.anomaly_min_deviation_pct},
        "persisted": bool(persist and all_flagged),
    }


def list_stored(tenant: Tenant, *, start: datetime | None = None, end: datetime | None = None,
                severity: str | None = None, meter_id: uuid.UUID | None = None,
                acknowledged: bool | None = None, limit: int = 100, offset: int = 0) -> dict:
    from sqlalchemy import func as f
    q = select(Anomaly, Meter.name).join(Meter, Meter.id == Anomaly.meter_id).where(
        Anomaly.organization_id == tenant.org_id)
    if start:
        q = q.where(Anomaly.ts >= start)
    if end:
        q = q.where(Anomaly.ts < end)
    if severity:
        q = q.where(Anomaly.severity == severity)
    if meter_id:
        q = q.where(Anomaly.meter_id == meter_id)
    if acknowledged is not None:
        q = q.where(Anomaly.acknowledged.is_(acknowledged))
    total = tenant.db.scalar(select(f.count()).select_from(q.subquery())) or 0
    rows = tenant.db.execute(q.order_by(Anomaly.ts.desc()).limit(limit).offset(offset)).all()
    items = []
    for anomaly, meter_name in rows:
        explanations = (anomaly.details or {}).get("explanations") or {
            "uz": anomaly.explanation, "ru": anomaly.explanation, "en": anomaly.explanation}
        items.append({
            "id": anomaly.id, "meter_id": anomaly.meter_id, "meter": meter_name,
            "ts": anomaly.ts, "observed_kwh": anomaly.observed_kwh,
            "expected_kwh": anomaly.expected_kwh, "deviation_pct": anomaly.deviation_pct,
            "severity": anomaly.severity, "method": anomaly.method,
            "explanation": explanations.get("uz"), "explanations": explanations,
            "details": anomaly.details, "acknowledged": anomaly.acknowledged,
        })
    return {"items": items, "total": total, "limit": limit, "offset": offset}


def acknowledge(tenant: Tenant, anomaly_id: uuid.UUID) -> Anomaly:
    anomaly = tenant.db.scalar(select(Anomaly).where(
        Anomaly.id == anomaly_id, Anomaly.organization_id == tenant.org_id))
    if anomaly is None:
        raise NotFound("Anomaly not found")
    anomaly.acknowledged = True
    anomaly.acknowledged_by = tenant.user_id
    anomaly.acknowledged_at = datetime.now(UTC)
    tenant.db.commit()
    return anomaly
