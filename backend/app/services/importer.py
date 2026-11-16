"""CSV / XLSX import pipeline.

Stages (mirrors the 10-step wizard in the product spec):
  1. read bytes -> tabular data           (memory-safe guards: size + row caps)
  2. detect columns from a multilingual header pool
  3. parse + validate rows                (timestamps, numbers, ranges)
  4. convert cumulative registers to interval consumption (with reset handling)
  5. flag duplicates (within file and against the database)
  6. detect missing intervals for the meter's cadence
  7. return a preview + errors, persist the job as `validated`
  8. confirm -> insert valid rows only, idempotently

Timezone policy: naive timestamps are interpreted in the organization's timezone
(Asia/Tashkent by default) and stored as UTC. Explicitly-offset input is trusted.
"""
from __future__ import annotations

import hashlib
import io
import re
import unicodedata
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import NotFound, ValidationFailed
from app.core.tenant import Tenant
from app.models import ImportJob, ImportStagingRow, Meter, MeterReading
from app.models.enums import AuditAction, ImportStatus, MeterType, ReadingSource
from app.services import audit
from app.services.meter_service import kwh_to_kw

MAX_PREVIEW_ROWS = 200
MAX_ERRORS = 200

# Multilingual header dictionary (uz / ru / en). Matching is normalised: lowercased,
# diacritics stripped, punctuation collapsed.
HEADER_ALIASES: dict[str, tuple[str, ...]] = {
    "timestamp": ("timestamp", "time", "datetime", "date time", "date", "ts", "vaqt", "sana",
                  "vaqt sana", "дата", "время", "дата время", "дата и время", "месяц",
                  "period", "davr", "период", "reading time", "hisob vaqti"),
    "consumption_kwh": ("consumption", "consumption kwh", "kwh", "energy", "energy kwh",
                        "value", "istеmol", "istemol", "iste'mol", "iste mol", "sarflangan",
                        "energiya", "квтч", "квт ч", "расход", "потребление", "энергия",
                        "показатель", "расход квтч"),
    "register_kwh": ("register", "reading", "meter reading", "register kwh", "cumulative",
                     "korsatkich", "ko'rsatkich", "korsatkichi", "pokazanie", "показание",
                     "показания", "счетчик показание", "schetchik"),
    "interval_minutes": ("interval", "interval minutes", "interval min", "minutes",
                         "davr davomiyligi", "интервал", "минут", "интервал минут"),
    "meter_serial": ("meter", "meter serial", "serial", "serial number", "meter id",
                     "schetchik", "счетчик", "hisoblagich", "hisoblagich raqami"),
    "department": ("department", "bo'lim", "bolim", "цех", "подразделение", "uchastka"),
    "power_kw": ("power", "kw", "power kw", "кви", "квт", "мощность", "quvvat"),
}

_NUM_CLEAN = re.compile(r"[^\d,.\-]")


def normalise_header(value: str) -> str:
    s = unicodedata.normalize("NFKD", str(value))
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.replace("ʻ", "'").replace("’", "'").replace("`", "'")
    s = re.sub(r"[_\-\.\/\(\)\[\]]+", " ", s.lower())
    s = re.sub(r"\s+", " ", s).strip()
    return s


def detect_columns(columns: list[str]) -> tuple[dict[str, str], list[str]]:
    """Map file headers to canonical roles. Returns (mapping, unmapped_headers)."""
    mapping: dict[str, str] = {}
    used: set[str] = set()
    normalised = {c: normalise_header(c) for c in columns}
    for role, aliases in HEADER_ALIASES.items():
        if role == "power_kw":  # kW is derived, never imported as consumption
            continue
        for alias in aliases:
            for original, norm in normalised.items():
                if original in used:
                    continue
                if norm == alias or (len(alias) > 3 and alias in norm and norm not in
                                    {normalise_header(a) for a in ("date",)}):
                    mapping[role] = original
                    used.add(original)
                    break
            if role in mapping:
                break
    unmapped = [c for c in columns if c not in used]
    return mapping, unmapped


@dataclass
class RowIssue:
    row: int
    message: str
    kind: str = "error"


@dataclass
class ParsedImport:
    mapping: dict[str, str]
    reading_type: str
    total_rows: int
    valid: list[dict] = field(default_factory=list)
    duplicates: int = 0
    out_of_order: int = 0
    resets: list[dict] = field(default_factory=list)
    issues: list[RowIssue] = field(default_factory=list)
    missing_intervals: int = 0
    interval_minutes: int = 60
    warnings: list[str] = field(default_factory=list)
    preview: list[dict] = field(default_factory=list)

    @property
    def invalid(self) -> int:
        return len(self.issues)


# ---------------------------------------------------------------- reading files
def read_table(content: bytes, filename: str) -> pd.DataFrame:
    if len(content) > settings.UPLOAD_MAX_MB * 1024 * 1024:
        raise ValidationFailed(f"File exceeds {settings.UPLOAD_MAX_MB} MB",
                               code="file_too_large")
    name = (filename or "").lower()
    if name.endswith(".xlsx"):  # macro-enabled workbooks are refused on purpose
        try:
            df = pd.read_excel(io.BytesIO(content), dtype=str, engine="openpyxl")
        except Exception as exc:
            raise ValidationFailed(f"Cannot read the Excel file: {exc}", code="unreadable_file")
    elif name.endswith((".csv", ".txt", ".tsv")):
        df = _read_csv(content, filename)
    else:
        raise ValidationFailed("Unsupported file type. Upload .csv or .xlsx",
                               code="unsupported_file_type")
    if df.empty:
        raise ValidationFailed("The file contains no data rows", code="empty_file")
    if len(df) > settings.UPLOAD_MAX_ROWS:
        raise ValidationFailed(f"File has {len(df)} rows; the limit is {settings.UPLOAD_MAX_ROWS}",
                               code="too_many_rows")
    df.columns = [str(c).strip() for c in df.columns]
    return df


def _read_csv(content: bytes, filename: str) -> pd.DataFrame:
    last_error: Exception | None = None
    for encoding in ("utf-8-sig", "utf-8", "cp1251"):
        sep = "\t" if filename.lower().endswith(".tsv") else None
        try:
            return pd.read_csv(io.BytesIO(content), dtype=str, encoding=encoding,
                               sep=sep, engine="python", on_bad_lines="skip")
        except Exception as exc:  # try the next encoding
            last_error = exc
    raise ValidationFailed(f"Cannot read the CSV file: {last_error}", code="unreadable_file")


# ------------------------------------------------------------------- conversions
def parse_number(value, decimal_comma: bool | None = None) -> Decimal | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "-", "n/a", "na", ""}:
        return None
    text = text.replace("\u00a0", "").replace(" ", "").replace("'", "")
    has_comma, has_dot = "," in text, "." in text
    if has_comma and has_dot:
        # whichever separator appears last is the decimal separator
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif has_comma and (decimal_comma is None or decimal_comma):
        text = text.replace(",", ".")
    text = _NUM_CLEAN.sub("", text)
    try:
        return Decimal(text)
    except (InvalidOperation, ValueError):
        return None


def parse_timestamp(value, tz: ZoneInfo) -> datetime | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none"}:
        return None
    ts = pd.to_datetime(text, errors="coerce", utc=False, dayfirst=False)
    if ts is pd.NaT or pd.isna(ts):
        ts = pd.to_datetime(text, errors="coerce", dayfirst=True)
        if ts is pd.NaT or pd.isna(ts):
            return None
    py_ts = ts.to_pydatetime()
    if py_ts.tzinfo is None:
        py_ts = py_ts.replace(tzinfo=tz)
    return py_ts.astimezone(UTC)


# ------------------------------------------------------------------ main pipeline
def analyse(df: pd.DataFrame, *, mapping: dict[str, str], reading_type: str,
            tz_name: str, interval_minutes: int, multiplier: Decimal,
            decimal_comma: bool | None = None,
            meter_max_power_kw: Decimal | None = None) -> ParsedImport:
    tz = ZoneInfo(tz_name)
    if "timestamp" not in mapping:
        raise ValidationFailed("No timestamp column was detected. Map one explicitly.",
                               code="missing_timestamp_column")
    if reading_type == "interval" and "consumption_kwh" not in mapping:
        raise ValidationFailed("Interval imports need a consumption (kWh) column.",
                               code="missing_consumption_column")
    if reading_type == "cumulative" and "register_kwh" not in mapping:
        raise ValidationFailed("Cumulative imports need a meter register column.",
                               code="missing_register_column")

    result = ParsedImport(mapping=mapping, reading_type=reading_type,
                          total_rows=int(len(df)), interval_minutes=interval_minutes)
    records: list[dict] = []
    seen: dict[datetime, int] = {}

    for idx, raw in enumerate(df.to_dict("records"), start=2):  # +2: header + 1-based
        ts = parse_timestamp(raw.get(mapping["timestamp"]), tz)
        if ts is None:
            result.issues.append(RowIssue(idx, "Timestamp could not be parsed"))
            continue
        if "interval_minutes" in mapping:
            explicit = parse_number(raw.get(mapping["interval_minutes"]))
            if explicit is not None and explicit > 0:
                result.interval_minutes = int(explicit)
        value_col = mapping.get("consumption_kwh") if reading_type == "interval" else mapping.get("register_kwh")
        value = parse_number(raw.get(value_col), decimal_comma=decimal_comma)
        if value is None:
            result.issues.append(RowIssue(idx, "Value could not be parsed as a number"))
            continue
        if value < 0:
            result.issues.append(RowIssue(idx, "Negative values are not valid for this column"))
            continue
        records.append({"row": idx, "ts": ts, "value": value})

    if not records:
        result.warnings.append("No usable rows were found in the file.")
        return result

    records.sort(key=lambda r: r["ts"])

    if reading_type == "cumulative":
        converted: list[dict] = []
        previous: dict | None = None
        for rec in records:
            if previous is None:
                # the first register value only establishes a baseline: no consumption
                # can be derived from a single cumulative reading.
                previous = rec
                continue
            delta = rec["value"] - previous["value"]
            minutes = int((rec["ts"] - previous["ts"]).total_seconds() // 60) or interval_minutes
            if delta < 0:
                # meter rollover / reset: cannot be interpreted as negative consumption.
                result.resets.append({
                    "row": rec["row"], "ts": rec["ts"].isoformat(),
                    "previous_register": str(previous["value"]), "register": str(rec["value"]),
                    "reason": "register decreased (meter reset or replacement)",
                })
                previous = rec
                continue
            converted.append({"row": rec["row"], "ts": previous["ts"], "value": delta,
                              "interval_minutes": minutes, "register": rec["value"]})
            previous = rec
        records = converted
        if result.resets:
            result.warnings.append(
                f"{len(result.resets)} register reset(s) detected; intervals spanning a reset "
                f"were skipped instead of being reported as negative consumption.")

    for rec in records:
        if rec["ts"] in seen:
            result.duplicates += 1
            continue
        seen[rec["ts"]] = rec["row"]
        kwh = rec["value"] * multiplier
        # An interval longer than the cadence is legitimate (gaps exist), but the
        # implied power must still be computed from the true duration.
        minutes = rec.get("interval_minutes") or interval_minutes
        if minutes <= 0:
            result.issues.append(RowIssue(rec["row"], "Non-positive interval duration"))
            continue
        if meter_max_power_kw is not None and kwh_to_kw(kwh, minutes) > meter_max_power_kw * Decimal("1.5"):
            result.issues.append(RowIssue(
                rec["row"],
                f"Implied power {kwh_to_kw(kwh, minutes)} kW exceeds meter ceiling "
                f"{meter_max_power_kw} kW by more than 50%"))
            continue
        result.valid.append({"row": rec["row"], "ts": rec["ts"], "consumption_kwh": kwh,
                             "interval_minutes": minutes,
                             "power_kw": kwh_to_kw(kwh, minutes)})

    # missing intervals for the covered span
    if len(result.valid) >= 2:
        span = result.valid[-1]["ts"] - result.valid[0]["ts"]
        expected = int(span.total_seconds() // (interval_minutes * 60)) + 1
        result.missing_intervals = max(0, expected - len(result.valid))
        if result.missing_intervals:
            result.warnings.append(
                f"{result.missing_intervals} expected interval(s) are missing from the file "
                f"for the covered period (cadence {interval_minutes} min).")

    for rec in result.valid[:MAX_PREVIEW_ROWS]:
        result.preview.append({"row": rec["row"], "ts": rec["ts"].isoformat(),
                               "consumption_kwh": str(rec["consumption_kwh"].quantize(Decimal("0.0001"))),
                               "power_kw": str(rec["power_kw"].quantize(Decimal("0.0001"))),
                               "status": "valid", "message": None})
    for issue in result.issues[:MAX_PREVIEW_ROWS]:
        result.preview.append({"row": issue.row, "ts": None, "consumption_kwh": None,
                               "power_kw": None, "status": "error", "message": issue.message})
    return result


# ------------------------------------------------------------------ persistence
def create_job(tenant: Tenant, *, filename: str, content: bytes, content_type: str | None,
               meter_id: uuid.UUID | None, reading_type: str | None = None) -> ImportJob:
    meter = None
    if meter_id is not None:
        meter = tenant.db.scalar(select(Meter).where(Meter.id == meter_id,
                                                     Meter.organization_id == tenant.org_id))
        if meter is None:
            raise NotFound("Meter not found")
    job = ImportJob(
        organization_id=tenant.org_id, meter_id=meter.id if meter else None,
        filename=filename[:255], content_type=(content_type or "")[:120] or None,
        size_bytes=len(content), file_sha256=hashlib.sha256(content).hexdigest(),
        reading_type=(reading_type or (meter.meter_type if meter else MeterType.INTERVAL.value)),
        status=ImportStatus.UPLOADED.value, created_by=tenant.user_id,
    )
    tenant.db.add(job)
    tenant.db.commit()
    tenant.db.refresh(job)
    audit.record(AuditAction.IMPORT_CREATE, org_id=tenant.org_id, user_id=tenant.user_id,
                 target_type="import_job", target_id=str(job.id),
                 meta={"filename": filename, "size": len(content)})
    return job


def validate_job(tenant: Tenant, job_id: uuid.UUID, *, content: bytes, meter_id: uuid.UUID,
                 reading_type: str, mapping: dict[str, str] | None, tz_name: str,
                 interval_minutes: int | None, decimal_comma: bool | None) -> ParsedImport:
    job, meter = _load(tenant, job_id)
    df = read_table(content, job.filename)
    detected, unmapped = detect_columns(list(df.columns))
    final_mapping = {**(mapping or detected)} if mapping else detected
    final_mapping = {k: v for k, v in final_mapping.items() if v}
    parsed = analyse(
        df, mapping=final_mapping, reading_type=reading_type, tz_name=tz_name,
        interval_minutes=interval_minutes or meter.interval_minutes,
        multiplier=meter.multiplier, decimal_comma=decimal_comma,
        meter_max_power_kw=meter.max_power_kw)

    # duplicates that already exist in the database for this meter
    if parsed.valid:
        existing = _existing_timestamps(tenant, meter.id, parsed.valid[0]["ts"], parsed.valid[-1]["ts"])
        def _as_utc(dt):
            if hasattr(dt, "tzinfo") and dt.tzinfo is None:
                return dt.replace(tzinfo=UTC)
            return dt.astimezone(UTC) if hasattr(dt, "astimezone") else dt
        fresh = [r for r in parsed.valid if _as_utc(r["ts"]) not in existing]
        db_dupes = len(parsed.valid) - len(fresh)
        parsed.duplicates += db_dupes
        if db_dupes:
            parsed.warnings.append(f"{db_dupes} row(s) already exist in the database and will be skipped.")
        parsed.valid = fresh

    job.meter_id = meter.id
    job.reading_type = reading_type
    job.column_mapping = {**final_mapping, "_unmapped": unmapped}
    job.total_rows = parsed.total_rows
    job.valid_rows = len(parsed.valid)
    job.invalid_rows = parsed.invalid
    job.duplicate_rows = parsed.duplicates
    job.missing_intervals = parsed.missing_intervals
    job.errors = [{"row": i.row, "message": i.message} for i in parsed.issues[:MAX_ERRORS]]
    job.warnings = parsed.warnings + ([{"resets": parsed.resets}] if parsed.resets else [])
    job.preview = parsed.preview
    # replace any staged rows from a previous validation attempt of this job
    tenant.db.query(ImportStagingRow).filter(
        ImportStagingRow.import_job_id == job.id).delete(synchronize_session=False)
    batch: list[ImportStagingRow] = []
    for rec in parsed.valid:
        batch.append(ImportStagingRow(
            organization_id=tenant.org_id, import_job_id=job.id, source_row=rec["row"],
            ts=rec["ts"], interval_minutes=rec["interval_minutes"],
            consumption_kwh=rec["consumption_kwh"].quantize(Decimal("0.0001")),
            power_kw=rec["power_kw"].quantize(Decimal("0.0001"))))
        if len(batch) >= 5000:
            tenant.db.add_all(batch)
            tenant.db.flush()
            batch = []
    if batch:
        tenant.db.add_all(batch)
    job.status = ImportStatus.VALIDATED.value
    tenant.db.commit()
    return parsed


def confirm_job(tenant: Tenant, job_id: uuid.UUID, *, skip_duplicates: bool = True) -> dict:
    job, meter = _load(tenant, job_id)
    if job.status == ImportStatus.CONFIRMED.value:
        raise ValidationFailed("This import has already been confirmed", code="already_confirmed")
    if job.status != ImportStatus.VALIDATED.value or not job.preview:
        raise ValidationFailed("Validate the file before confirming the import",
                               code="not_validated")

    staged = list(tenant.db.scalars(select(ImportStagingRow).where(
        ImportStagingRow.import_job_id == job.id).order_by(ImportStagingRow.ts)))
    if not staged:
        raise ValidationFailed("There are no validated rows to import", code="nothing_to_import")

    existing = _existing_timestamps(tenant, meter.id, staged[0].ts, staged[-1].ts)
    inserted = skipped = 0
    first_ts = last_ts = None
    batch: list[MeterReading] = []
    for row in staged:
        row_ts = row.ts.replace(tzinfo=UTC) if row.ts.tzinfo is None else row.ts.astimezone(UTC)
        if row_ts in existing:
            if skip_duplicates:
                skipped += 1
                continue
            raise ValidationFailed("Duplicate reading encountered; enable skip_duplicates",
                                   code="duplicate_reading", details={"ts": row.ts.isoformat()})
        batch.append(MeterReading(
            organization_id=tenant.org_id, meter_id=meter.id, ts=row_ts,
            interval_minutes=row.interval_minutes,
            consumption_kwh=row.consumption_kwh, power_kw=row.power_kw,
            source=ReadingSource.IMPORT.value, quality="ok", created_at=datetime.now(UTC),
            import_job_id=job.id))
        existing.add(row_ts)
        inserted += 1
        first_ts = first_ts or row.ts
        last_ts = row.ts
        if len(batch) >= 5000:
            tenant.db.add_all(batch)
            tenant.db.flush()
            batch = []
    if batch:
        tenant.db.add_all(batch)
        tenant.db.flush()
    tenant.db.query(ImportStagingRow).filter(
        ImportStagingRow.import_job_id == job.id).delete(synchronize_session=False)
    job.status = ImportStatus.CONFIRMED.value
    job.confirmed_at = datetime.now(UTC)
    tenant.db.commit()
    audit.record(AuditAction.IMPORT_CONFIRM, org_id=tenant.org_id, user_id=tenant.user_id,
                 target_type="import_job", target_id=str(job.id),
                 meta={"inserted": inserted, "skipped": skipped})
    from app.services import notifications
    notifications.notify_import(tenant, inserted=inserted, skipped=skipped, job_id=job.id)
    return {"job_id": job.id, "status": job.status, "inserted": inserted,
            "skipped_duplicates": skipped, "invalid": job.invalid_rows,
            "missing_intervals": job.missing_intervals,
            "first_reading_at": first_ts, "last_reading_at": last_ts,
            "message": f"{inserted} reading(s) imported, {skipped} duplicate(s) skipped."}


def _load(tenant: Tenant, job_id: uuid.UUID) -> tuple[ImportJob, Meter]:
    job = tenant.db.scalar(select(ImportJob).where(
        ImportJob.id == job_id, ImportJob.organization_id == tenant.org_id))
    if job is None:
        raise NotFound("Import job not found")
    if job.meter_id is None:
        raise ValidationFailed("Assign a meter to this import first", code="meter_required")
    meter = tenant.db.scalar(select(Meter).where(Meter.id == job.meter_id,
                                                  Meter.organization_id == tenant.org_id))
    if meter is None:
        raise NotFound("Meter not found")
    return job, meter


def _existing_timestamps(tenant: Tenant, meter_id: uuid.UUID, start: datetime,
                         end: datetime) -> set[datetime]:
    start_utc = start.astimezone(UTC) if hasattr(start, "tzinfo") and start.tzinfo else (start.replace(tzinfo=UTC) if hasattr(start, "replace") else start)
    end_utc = end.astimezone(UTC) if hasattr(end, "tzinfo") and end.tzinfo else (end.replace(tzinfo=UTC) if hasattr(end, "replace") else end)
    rows = tenant.db.execute(select(MeterReading.ts).where(
        MeterReading.meter_id == meter_id, MeterReading.ts >= start_utc,
        MeterReading.ts <= end_utc)).scalars()
    out = set()
    for ts in rows:
        if isinstance(ts, str):
            ts = datetime.fromisoformat(ts)
        if hasattr(ts, "tzinfo") and ts.tzinfo is None:
            ts = ts.replace(tzinfo=UTC)
        out.add(ts)
    return out


# -------------------------------------------------------------------- templates
def csv_template() -> bytes:
    body = (
        "timestamp,consumption_kwh,meter_serial\n"
        "2026-01-01 00:00,120.5,MER-001\n"
        "2026-01-01 01:00,118.2,MER-001\n"
        "2026-01-01 02:00,97.0,MER-001\n"
    )
    instructions = (
        "# NEXTGEN AI import template (interval consumption)\n"
        "# timestamp: ISO-8601 or 'YYYY-MM-DD HH:MM'. Naive values are read as Asia/Tashkent.\n"
        "# consumption_kwh: energy used during the interval (kWh) - NOT power (kW).\n"
        "# meter_serial: optional; if the file covers a single meter you may omit it.\n"
        "# For cumulative meters use the 'register_kwh' template instead.\n"
    )
    return instructions.encode("utf-8") + body.encode("utf-8")


def xlsx_template() -> bytes:
    df = pd.DataFrame({
        "timestamp": ["2026-01-01 00:00", "2026-01-01 01:00", "2026-01-01 02:00"],
        "consumption_kwh": [120.5, 118.2, 97.0],
        "meter_serial": ["MER-001", "MER-001", "MER-001"],
    })
    cumulative = pd.DataFrame({
        "timestamp": ["2026-01-01 00:00", "2026-01-01 01:00", "2026-01-01 02:00"],
        "register_kwh": [10450.0, 10568.5, 10686.7],
        "meter_serial": ["MER-002", "MER-002", "MER-002"],
    })
    notes = pd.DataFrame({"column": ["timestamp", "consumption_kwh", "register_kwh", "meter_serial"],
                          "meaning": [
                              "Interval start. Naive timestamps are interpreted as Asia/Tashkent.",
                              "Energy consumed during the interval, kWh (not kW).",
                              "Cumulative meter register, kWh. Consecutive differences become consumption.",
                              "Optional when the file covers exactly one meter."]})
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="interval")
        cumulative.to_excel(writer, index=False, sheet_name="cumulative")
        notes.to_excel(writer, index=False, sheet_name="notes")
    return buf.getvalue()
