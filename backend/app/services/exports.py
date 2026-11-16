"""Report generation: PDF (reportlab), XLSX (openpyxl) and CSV.

Files are written under `REPORT_OUTPUT_DIR/<org_id>/` so a download can only ever
resolve inside the caller's own organization directory. Every report records the
period, the tariff assumptions and the DEMO flag it was produced from.
"""
from __future__ import annotations

import csv
import io
import re
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy import func, select

from app.core.config import settings
from app.core.errors import NotFound, ValidationFailed
from app.core.tenant import Tenant
from app.core.timeutil import period_bounds, to_local
from app.models import Report
from app.models.enums import AuditAction
from app.services import analytics, anomalies as anomaly_service, audit, forecast as forecast_service
from app.services import savings as savings_service

KINDS = {"dashboard", "consumption", "anomalies", "savings", "forecast"}
FORMATS = {"pdf", "xlsx", "csv"}

KIND_TITLE = {
    "dashboard": "Boshqaruv paneli hisoboti",
    "consumption": "Iste'mol tahlili",
    "anomalies": "Anomaliyalar hisoboti",
    "savings": "Tejamkorlik hisoboti",
    "forecast": "Prognoz hisoboti",
}


def _slug(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip("-")[:60] or "report"


def _n(value, digits: int = 1) -> str:
    if value is None:
        return "—"
    return f"{Decimal(str(value)):,.{digits}f}".replace(",", " ")


def _collect(tenant: Tenant, *, kind: str, period: str) -> dict:
    """Gather the data for one report. Numbers are read, never invented."""
    if kind in {"dashboard", "consumption"}:
        start, end = period_bounds(period)
        totals = analytics.totals(tenant, start=start, end=end, filters={})
        return {
            "window": {"start": start, "end": end},
            "totals": totals,
            "series": analytics.series(tenant, start=start, end=end, filters={}, granularity=None),
            "by_meter": analytics.by_meter(tenant, start=start, end=end, filters={}),
            "by_department": analytics.by_department(tenant, start=start, end=end),
            "peaks": analytics.peaks(tenant, start=start, end=end, filters={}, limit=10),
            "anomalies": anomaly_service.list_stored(tenant, start=start, end=end, limit=20),
            "comparison": analytics.comparison(tenant, start=start, end=end, filters={},
                                               mode="previous"),
        }
    if kind == "anomalies":
        start, end = period_bounds(period)
        return {"window": {"start": start, "end": end},
                "anomalies": anomaly_service.list_stored(tenant, start=start, end=end, limit=200)}
    if kind == "forecast":
        return {"forecast": forecast_service.generate(tenant, horizon_days=30, history_days=90,
                                                      persist=False)}
    start, end = period_bounds(period)
    return {"window": {"start": start, "end": end},
            "savings": savings_service.list_reports(tenant, limit=50)}


# --------------------------------------------------------------------------- PDF
def _pdf(tenant: Tenant, *, kind: str, title: str, data: dict, language: str) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm,
                            topMargin=14 * mm, bottomMargin=14 * mm,
                            title=title, author="NEXTGEN AI")
    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=styles["Heading1"], fontSize=17, leading=20,
                        textColor=colors.HexColor("#101A2B"), spaceAfter=2)
    h2 = ParagraphStyle("h2", parent=styles["Heading2"], fontSize=11.5, leading=14,
                        textColor=colors.HexColor("#3B82F6"), spaceBefore=10, spaceAfter=4)
    body = ParagraphStyle("body", parent=styles["Normal"], fontSize=8.5, leading=11)
    small = ParagraphStyle("small", parent=body, fontSize=7.5, textColor=colors.HexColor("#64748B"))

    story: list = [Paragraph("NEXTGEN AI", h1), Paragraph(title, h2)]
    org_line = f"{tenant.org.name} · {tenant.org.timezone} · {tenant.org.currency}"
    story.append(Paragraph(org_line, body))
    if tenant.org.is_demo:
        story.append(Paragraph("<b>DEMO MA'LUMOT — namuna hisobot</b>", body))
    window = data.get("window") or {}
    stamp = datetime.now(UTC).astimezone(to_local(datetime.now(UTC)).tzinfo)
    meta = [f"Yaratilgan: {stamp:%d.%m.%Y %H:%M} (Asia/Tashkent)"]
    if window.get("start"):
        meta.append(f"Davr: {to_local(window['start']):%d.%m.%Y} – {to_local(window['end']):%d.%m.%Y}")
    story.append(Paragraph(" · ".join(meta), small))

    def table(rows: list[list[str]], widths=None, header=True) -> Table:
        tbl = Table(rows, colWidths=widths, hAlign="LEFT")
        style = [("FONTSIZE", (0, 0), (-1, -1), 7.5),
                 ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                 ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#CBD5E1")),
                 ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F1F5F9")])]
        if header:
            style += [("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#17243A")),
                      ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                      ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold")]
        tbl.setStyle(TableStyle(style))
        return tbl

    totals = data.get("totals")
    if totals:
        story.append(Paragraph("Umumiy ko'rsatkichlar", h2))
        rows = [["Ko'rsatkich", "Qiymat"],
                ["Jami iste'mol (kWh)", _n(totals["consumption_kwh"], 2)],
                ["O'qishlar soni", _n(totals["readings"], 0)],
                ["Ma'lumot qamrovi (%)", _n(totals["data_coverage_pct"], 1)],
                ["O'rtacha quvvat (kW)", _n(totals["average_power_kw"], 2)],
                ["Eng yuqori quvvat (kW)", _n(totals["peak_power_kw"], 2)],
                ["Hisoblangan xarajat",
                 f"{_n(totals['estimated_cost'], 0)} {totals['currency']}"
                 if totals["estimated_cost"] is not None else "tarif sozlanmagan"]]
        if totals.get("tariff", {}).get("name"):
            rows.append(["Tarif", f"{totals['tariff']['name']} · "
                                   f"{_n(totals['tariff']['price_per_kwh'], 2)} "
                                   f"{totals['currency']}/kWh"])
        story.append(table(rows, widths=[70 * mm, 70 * mm]))

    comparison = data.get("comparison")
    if comparison and comparison.get("difference_pct") is not None:
        story.append(Paragraph("Davr taqqoslashuvi", h2))
        story.append(table([
            ["Joriy davr (kWh)", _n(comparison["current"]["consumption_kwh"], 2)],
            ["Bazaviy davr (kWh)", _n(comparison["baseline"]["consumption_kwh"], 2)],
            ["Farq (%)", _n(comparison["difference_pct"], 2)],
        ], widths=[70 * mm, 70 * mm]))

    if data.get("series"):
        story.append(Paragraph("Dinamika", h2))
        rows = [["Kesim", "Iste'mol (kWh)", "O'qishlar", "Cho'qqi quvvat (kW)"]]
        for point in data["series"][:60]:
            rows.append([point["label"], _n(point["consumption_kwh"], 2),
                         str(point["readings"]), _n(point["peak_power_kw"], 2)])
        story.append(table(rows, widths=[40 * mm, 40 * mm, 30 * mm, 40 * mm]))

    if data.get("by_meter"):
        story.append(Paragraph("Hisoblagichlar bo'yicha", h2))
        rows = [["Hisoblagich", "Bo'lim", "Iste'mol (kWh)", "Ulush (%)"]]
        for meter in data["by_meter"]:
            rows.append([meter["name"], meter.get("department") or "—",
                         _n(meter["consumption_kwh"], 2), _n(meter["share_pct"], 2)])
        story.append(table(rows, widths=[55 * mm, 40 * mm, 35 * mm, 25 * mm]))

    stored_anomalies = (data.get("anomalies") or {}).get("items") or []
    if stored_anomalies:
        story.append(Paragraph("Anomaliyalar", h2))
        rows = [["Vaqt", "Hisoblagich", "Kuzatilgan (kWh)", "Kutilgan (kWh)", "Og'ish (%)"]]
        for item in stored_anomalies[:40]:
            rows.append([to_local(item["ts"]).strftime("%d.%m.%Y %H:%M"), item["meter"],
                         _n(item["observed_kwh"], 2), _n(item["expected_kwh"], 2),
                         _n(item["deviation_pct"], 2)])
        story.append(table(rows, widths=[32 * mm, 42 * mm, 32 * mm, 30 * mm, 22 * mm]))

    fc = data.get("forecast")
    if fc:
        story.append(Paragraph("Prognoz", h2))
        story.append(table([
            ["Usul", fc["method"]],
            ["Gorizont (kun)", str(fc["horizon_days"])],
            ["Prognoz jami (kWh)", _n(fc["total_kwh"], 2)],
            ["Prognoz xarajati", f"{_n(fc['total_cost'], 0)} {fc['currency']}"
             if fc["total_cost"] is not None else "tarif sozlanmagan"],
            ["Aniqlik (MAPE, %)", _n(fc["accuracy_mape"], 2) if fc["accuracy_mape"] else "—"],
            ["Ishonch", fc["confidence"]],
        ], widths=[70 * mm, 70 * mm]))
        rows = [["Sana", "Prognoz (kWh)", "Xarajat"]]
        for point in fc["points"][:31]:
            rows.append([point["date"], _n(point["consumption_kwh"], 2),
                         _n(point["estimated_cost"], 0) if point["estimated_cost"] else "—"])
        story.append(table(rows, widths=[40 * mm, 40 * mm, 40 * mm]))

    if data.get("savings"):
        story.append(Paragraph("Tejamkorlik hisobotlari", h2))
        rows = [["Nomi", "Davr", "Bazaviy (kWh)", "Joriy (kWh)", "Tejam (kWh)", "Sifat"]]
        for row in data["savings"]:
            rows.append([row["name"], f"{row['period_start']} – {row['period_end']}",
                         _n(row["baseline_kwh"], 2), _n(row["actual_kwh"], 2),
                         _n(row["savings_kwh"], 2) if row["savings_kwh"] is not None else "—",
                         row["quality"]])
        story.append(table(rows, widths=[38 * mm, 40 * mm, 26 * mm, 24 * mm, 24 * mm, 20 * mm]))

    story.append(Spacer(1, 8))
    story.append(Paragraph(
        "Hisobotidagi pul qiymatlari tashkilot tarifi bo'yicha hisoblangan baho bo'lib, "
        "hisob-faktura emas. Anomaliya va prognoz qiymatlari algoritmik hisoblanadi. "
        "Energiya — kWh, quvvat — kW.", small))
    doc.build(story)
    return buffer.getvalue()


# -------------------------------------------------------------------------- XLSX
def _xlsx(tenant: Tenant, *, kind: str, title: str, data: dict) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Umumiy"
    bold = Font(bold=True, color="FFFFFF")
    fill = PatternFill("solid", fgColor="17243A")

    def header(ws_, row: int, values: list[str]) -> None:
        for col, value in enumerate(values, start=1):
            cell = ws_.cell(row=row, column=col, value=value)
            cell.font = bold
            cell.fill = fill
            cell.alignment = Alignment(horizontal="left")

    ws.append(["NEXTGEN AI", title])
    ws.append(["Tashkilot", tenant.org.name])
    ws.append(["Hisobot turi", KIND_TITLE.get(kind, kind)])
    ws.append(["Demo ma'lumotlari", "HA" if tenant.org.is_demo else "YO'Q"])
    window = data.get("window") or {}
    if window.get("start"):
        ws.append(["Davr", f"{to_local(window['start']):%d.%m.%Y} – "
                           f"{to_local(window['end']):%d.%m.%Y}"])
    ws.append(["Yaratilgan", datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")])
    for row in ws.iter_rows(min_row=1, max_row=ws.max_row, max_col=1):
        row[0].font = Font(bold=True)
    ws.column_dimensions["A"].width = 22
    ws.column_dimensions["B"].width = 60

    totals = data.get("totals")
    if totals:
        ws.append([])
        header(ws, ws.max_row + 1, ["Ko'rsatkich", "Qiymat"])
        for label, value in [
            ("Jami iste'mol (kWh)", float(totals["consumption_kwh"])),
            ("O'qishlar", totals["readings"]),
            ("Qamrov (%)", totals["data_coverage_pct"]),
            ("O'rtacha quvvat (kW)", float(totals["average_power_kw"])),
            ("Eng yuqori quvvat (kW)", float(totals["peak_power_kw"])),
            ("Hisoblangan xarajat", float(totals["estimated_cost"])
             if totals["estimated_cost"] is not None else None),
            ("Valyuta", totals["currency"]),
        ]:
            ws.append([label, value])

        series_ws = wb.create_sheet("Dinamika")
        header(series_ws, 1, ["Kesim", "Iste'mol (kWh)", "O'qishlar", "O'rtacha quvvat (kW)",
                              "Cho'qqi quvvat (kW)", "Xarajat"])
        for point in data["series"]:
            series_ws.append([point["label"], float(point["consumption_kwh"]), point["readings"],
                              float(point["average_power_kw"]), float(point["peak_power_kw"]),
                              float(point["estimated_cost"]) if point["estimated_cost"] else None])
        for col, width in zip("ABCDEF", (18, 18, 12, 20, 20, 18)):
            series_ws.column_dimensions[col].width = width

        meter_ws = wb.create_sheet("Hisoblagichlar")
        header(meter_ws, 1, ["Hisoblagich", "Seriya", "Bo'lim", "Iste'mol (kWh)", "Ulush (%)",
                             "Cho'qqi quvvat (kW)", "Xarajat"])
        for meter in data["by_meter"]:
            meter_ws.append([meter["name"], meter["serial_number"], meter.get("department"),
                             float(meter["consumption_kwh"]), float(meter["share_pct"]),
                             float(meter["peak_power_kw"]),
                             float(meter["estimated_cost"]) if meter["estimated_cost"] else None])
        for col, width in zip("ABCDEFG", (34, 16, 22, 18, 12, 20, 18)):
            meter_ws.column_dimensions[col].width = width

        dept_ws = wb.create_sheet("Bo'limlar")
        header(dept_ws, 1, ["Bo'lim", "Iste'mol (kWh)", "Ulush (%)"])
        for row in data["by_department"]:
            dept_ws.append([row["department"], float(row["consumption_kwh"]), float(row["share_pct"])])
        for col, width in zip("ABC", (30, 20, 12)):
            dept_ws.column_dimensions[col].width = width

    stored = (data.get("anomalies") or {}).get("items")
    if stored is not None:
        an_ws = wb.create_sheet("Anomaliyalar")
        header(an_ws, 1, ["Vaqt", "Hisoblagich", "Kuzatilgan (kWh)", "Kutilgan (kWh)",
                          "Og'ish (%)", "Jiddiylik", "Usul", "Izoh"])
        if not stored:
            an_ws.append(["—", "Tanlangan davrda anomaliya aniqlanmadi", None, None, None,
                          None, None, None])
        for item in stored:
            an_ws.append([to_local(item["ts"]).strftime("%d.%m.%Y %H:%M"), item["meter"],
                          float(item["observed_kwh"]), float(item["expected_kwh"]),
                          float(item["deviation_pct"]), item["severity"], item["method"],
                          item["explanation"]])
        for col, width in zip("ABCDEFGH", (18, 30, 18, 18, 12, 12, 18, 70)):
            an_ws.column_dimensions[col].width = width

    fc = data.get("forecast")
    if fc:
        fc_ws = wb.create_sheet("Prognoz")
        header(fc_ws, 1, ["Sana", "Prognoz (kWh)", "Xarajat", "Usul", "Ishonch"])
        for point in fc["points"]:
            fc_ws.append([point["date"], float(point["consumption_kwh"]),
                          float(point["estimated_cost"]) if point["estimated_cost"] else None,
                          fc["method"], fc["confidence"]])
        for col, width in zip("ABCDE", (14, 18, 18, 18, 12)):
            fc_ws.column_dimensions[col].width = width

    savings_ws = None
    if data.get("savings"):
        savings_ws = wb.create_sheet("Tejamkorlik")
        header(savings_ws, 1, ["Nomi", "Boshlanish", "Tugash", "Bazaviy (kWh)", "Joriy (kWh)",
                               "Tejam (kWh)", "Sifat", "Tasdiqlangan"])
        for row in data["savings"]:
            savings_ws.append([row["name"], str(row["period_start"]), str(row["period_end"]),
                               float(row["baseline_kwh"]) if row["baseline_kwh"] else None,
                               float(row["actual_kwh"]),
                               float(row["savings_kwh"]) if row["savings_kwh"] is not None else None,
                               row["quality"], row["verified"]])
        for col, width in zip("ABCDEFGH", (32, 14, 14, 18, 18, 16, 14, 14)):
            savings_ws.column_dimensions[col].width = width

    note = wb.create_sheet("Izoh")
    for line in [
        "Pul qiymatlari tashkilot tarifi bo'yicha hisoblangan baho — hisob-faktura emas.",
        "Anomaliya va prognoz — algoritmik hisob; kafolat emas.",
        "Energiya kWh, quvvat kW.",
        "DEMO tashkilot ma'lumotlari namuna bo'lib, real korxona hisoboti emas.",
    ]:
        note.append([line])
    note.column_dimensions["A"].width = 110

    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


# --------------------------------------------------------------------------- CSV
def _csv(tenant: Tenant, *, kind: str, title: str, data: dict) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["# NEXTGEN AI report", title])
    writer.writerow(["# organization", tenant.org.name])
    writer.writerow(["# environment", "DEMO" if tenant.org.is_demo else "PRODUCTION"])
    window = data.get("window") or {}
    if window.get("start"):
        writer.writerow(["# period", f"{to_local(window['start']):%Y-%m-%d}",
                         f"{to_local(window['end']):%Y-%m-%d}"])
    writer.writerow(["# generated_at_utc", datetime.now(UTC).isoformat(timespec="seconds")])
    writer.writerow(["# units", "energy=kWh", "power=kW", "currency", tenant.org.currency])
    writer.writerow(["# note",
                     "Pul qiymatlari tarif bo'yicha hisoblangan baho, hisob-faktura emas; "
                     "DEMO tashkilot ma'lumotlari namuna."])
    writer.writerow([])
    if data.get("series"):
        writer.writerow(["bucket_local", "label", "consumption_kwh", "readings",
                         "average_power_kw", "peak_power_kw", "estimated_cost"])
        for point in data["series"]:
            writer.writerow([point["bucket"], point["label"], point["consumption_kwh"],
                             point["readings"], point["average_power_kw"],
                             point["peak_power_kw"], point["estimated_cost"]])
    elif (data.get("anomalies") or {}).get("items") is not None:
        writer.writerow(["ts_local", "meter", "observed_kwh", "expected_kwh", "deviation_pct",
                         "severity", "method", "explanation"])
        for item in (data["anomalies"]["items"] or []):
            writer.writerow([to_local(item["ts"]).isoformat(), item["meter"], item["observed_kwh"],
                             item["expected_kwh"], item["deviation_pct"], item["severity"],
                             item["method"], item["explanation"]])
    elif data.get("forecast"):
        fc = data["forecast"]
        writer.writerow(["date", "consumption_kwh", "estimated_cost"])
        for point in fc["points"]:
            writer.writerow([point["date"], point["consumption_kwh"], point["estimated_cost"]])
    elif data.get("savings"):
        writer.writerow(["name", "period_start", "period_end", "baseline_kwh", "actual_kwh",
                         "savings_kwh", "quality", "verified"])
        for row in data["savings"]:
            writer.writerow([row["name"], row["period_start"], row["period_end"],
                             row["baseline_kwh"], row["actual_kwh"], row["savings_kwh"],
                             row["quality"], row["verified"]])
    return buffer.getvalue().encode("utf-8-sig")


def generate(tenant: Tenant, *, kind: str, fmt: str, period: str = "month",
             title: str | None = None, language: str = "uz") -> Report:
    if kind not in KINDS:
        raise ValidationFailed(f"Unknown report kind: {kind}", code="invalid_kind")
    if fmt not in FORMATS:
        raise ValidationFailed(f"Unknown report format: {fmt}", code="invalid_format")
    data = _collect(tenant, kind=kind, period=period)
    report_title = (title or KIND_TITLE.get(kind, kind))[:200]
    if fmt == "pdf":
        content = _pdf(tenant, kind=kind, title=report_title, data=data, language=language)
    elif fmt == "xlsx":
        content = _xlsx(tenant, kind=kind, title=report_title, data=data)
    else:
        content = _csv(tenant, kind=kind, title=report_title, data=data)

    folder = Path(settings.REPORT_OUTPUT_DIR).resolve() / str(tenant.org_id)
    folder.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    filename = f"nextgen-{kind}-{stamp}-{uuid.uuid4().hex[:6]}.{fmt}"
    path = folder / filename
    path.write_bytes(content)

    row = Report(organization_id=tenant.org_id, kind=kind, format=fmt, title=report_title,
                 period_start=data.get("window", {}).get("start"),
                 period_end=data.get("window", {}).get("end"),
                 filename=filename, size_bytes=len(content), status="ready",
                 params={"period": period, "language": language,
                         "is_demo": tenant.org.is_demo, "path": str(path)},
                 created_by=tenant.user_id)
    tenant.db.add(row)
    tenant.db.commit()
    tenant.db.refresh(row)
    audit.record(AuditAction.REPORT_EXPORT, org_id=tenant.org_id, user_id=tenant.user_id,
                 target_type="report", target_id=str(row.id),
                 meta={"kind": kind, "format": fmt, "size": len(content)})
    return row


def serialize(row: Report) -> dict:
    return {"id": row.id, "kind": row.kind, "format": row.format, "title": row.title,
            "filename": row.filename, "size_bytes": row.size_bytes, "status": row.status,
            "period_start": row.period_start, "period_end": row.period_end,
            "params": {k: v for k, v in (row.params or {}).items() if k != "path"},
            "created_at": row.created_at, "download_url": f"/api/v1/reports/{row.id}/download"}


def list_reports(tenant: Tenant, *, limit: int = 50, offset: int = 0) -> dict:
    base = select(Report).where(Report.organization_id == tenant.org_id)
    total = tenant.db.scalar(select(func.count()).select_from(base.subquery())) or 0
    rows = tenant.db.scalars(base.order_by(Report.created_at.desc()).limit(limit).offset(offset))
    return {"items": [serialize(row) for row in rows], "total": total,
            "limit": limit, "offset": offset}


def report_path(tenant: Tenant, report_id: uuid.UUID) -> tuple[Path, Report]:
    """Resolve a report file, re-checking that it belongs to this tenant.

    The stored filename is joined to the organization directory and resolved; a
    path that escapes that directory (traversal, tampering) is treated as absent.
    """
    row = tenant.db.scalar(select(Report).where(Report.id == report_id,
                                               Report.organization_id == tenant.org_id))
    if row is None:
        raise NotFound("Report not found")
    folder = (Path(settings.REPORT_OUTPUT_DIR).resolve() / str(tenant.org_id)).resolve()
    path = (folder / row.filename).resolve()
    if path.parent != folder:
        raise NotFound("Report not found")
    if not path.exists():
        raise NotFound("Report file is no longer available")
    return path, row


def resolve_download(tenant: Tenant, report_id: uuid.UUID) -> Path:
    return report_path(tenant, report_id)[0]
