"""Savings reports and PDF/XLSX/CSV exports."""
from __future__ import annotations

import io
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from openpyxl import load_workbook


def _meter(client, org_a, readings_factory, *, serial="SV-1", tariff="450"):
    meter = client.post("/api/v1/meters", json={"name": f"Savings meter {serial}",
                                               "serial_number": serial},
                        headers=org_a["_headers"]).json()
    if tariff:
        client.post("/api/v1/tariffs", json={"name": "Savings tariff",
                                             "price_per_kwh": tariff,
                                             "valid_from": "2025-01-01", "is_default": True},
                    headers=org_a["_headers"])
    return meter


def test_savings_requires_a_real_baseline(client, org_a, readings_factory):
    meter = _meter(client, org_a, readings_factory)
    today = datetime.now(UTC).date()
    start = today - timedelta(days=10)
    readings_factory(org_a["active_organization"]["id"], meter["id"],
                     start=f"{start}T00:00:00", hours=24 * 10,
                     kwh_pattern=lambda i, ts: 10)
    r = client.post("/api/v1/savings", json={
        "name": "No baseline test", "period_start": str(start), "period_end": str(today - timedelta(days=1)),
        "baseline_method": "previous_period"}, headers=org_a["_headers"])
    assert r.status_code == 200, r.text
    report = r.json()["report"]
    # the preceding window has no data at all -> no savings may be claimed
    assert report["quality"] == "insufficient"
    assert report["savings_kwh"] is None
    assert report["savings_amount"] is None
    assert report["verified"] is False
    assert "no savings" in report["methodology"]["status_reason"].lower()


def test_verified_savings_with_full_coverage(client, org_a, readings_factory):
    meter = _meter(client, org_a, readings_factory)
    today = datetime.now(UTC).date()
    baseline_start = (today - timedelta(days=20))
    current_start = today - timedelta(days=10)
    # baseline: 12 kWh/h ; current: 10 kWh/h  -> 16.67% reduction
    readings_factory(org_a["active_organization"]["id"], meter["id"],
                     start=f"{baseline_start}T00:00:00", hours=24 * 10,
                     kwh_pattern=lambda i, ts: 12)
    readings_factory(org_a["active_organization"]["id"], meter["id"],
                     start=f"{current_start}T00:00:00", hours=24 * 10,
                     kwh_pattern=lambda i, ts: 10)
    r = client.post("/api/v1/savings", json={
        "name": "Shift optimisation", "period_start": str(current_start),
        "period_end": str(today), "baseline_method": "previous_period"},
        headers=org_a["_headers"])
    body = r.json()
    report = body["report"]
    assert report["quality"] == "verified", body
    assert report["verified"] is True
    # ~10 days x 24 h x (12-10) kWh = ~480 kWh saved; the exact figure depends on how
    # the local-day windows fall, so assert the range and the tariff arithmetic.
    savings = Decimal(str(report["savings_kwh"]))
    assert Decimal("300") <= savings <= Decimal("500")
    assert Decimal(str(report["savings_amount"])) == (savings * Decimal("450")).quantize(
        Decimal("0.01"))
    assert "formula" in body["methodology"]
    assert "not an audit" in body["disclaimer"].lower()
    assert Decimal(str(body["narration"]["facts"]["savings_kwh"])) == savings


def test_savings_reports_are_isolated(client, org_a, org_b, readings_factory):
    _meter(client, org_a, readings_factory)
    today = datetime.now(UTC).date()
    created = client.post("/api/v1/savings", json={
        "name": "Isolated report", "period_start": str(today - timedelta(days=5)),
        "period_end": str(today)}, headers=org_a["_headers"]).json()["report"]
    assert org_b["_client"].get(f"/api/v1/savings/{created['id']}",
                                headers=org_b["_headers"]).status_code == 404
    assert org_b["_client"].get("/api/v1/savings",
                                headers=org_b["_headers"]).json()["total"] == 0


def test_export_pdf_xlsx_csv(client, org_a, readings_factory):
    meter = _meter(client, org_a, readings_factory)
    start = (datetime.now(UTC) - timedelta(days=5)).replace(minute=0, second=0, microsecond=0)
    readings_factory(org_a["active_organization"]["id"], meter["id"],
                     start=start.isoformat(), hours=24 * 5,
                     kwh_pattern=lambda i, ts: 25)
    for fmt, magic in (("pdf", b"%PDF"), ("xlsx", b"PK")):
        r = client.post("/api/v1/reports/export", json={"kind": "dashboard", "format": fmt,
                                                        "period": "last_7_days"},
                        headers=org_a["_headers"])
        assert r.status_code == 200, r.text
        report = r.json()
        download = client.get(report["download_url"], headers=org_a["_headers"])
        assert download.status_code == 200
        assert download.content[:4].startswith(magic)
        assert len(download.content) > 1000
    csv_report = client.post("/api/v1/reports/export",
                             json={"kind": "consumption", "format": "csv", "period": "last_7_days"},
                             headers=org_a["_headers"]).json()
    csv_download = client.get(csv_report["download_url"], headers=org_a["_headers"])
    text = csv_download.content.decode()
    assert "bucket_local" in text and "consumption_kwh" in text
    assert "# note" in text


def test_xlsx_contains_expected_sheets_and_demo_flag(client, org_a, readings_factory):
    meter = _meter(client, org_a, readings_factory)
    readings_factory(org_a["active_organization"]["id"], meter["id"],
                     start=(datetime.now(UTC) - timedelta(days=3)).replace(minute=0, second=0,
                                                                          microsecond=0).isoformat(),
                     hours=48, kwh_pattern=lambda i, ts: 15)
    r = client.post("/api/v1/reports/export", json={"kind": "dashboard", "format": "xlsx",
                                                    "period": "last_7_days"},
                    headers=org_a["_headers"]).json()
    content = client.get(r["download_url"], headers=org_a["_headers"]).content
    wb = load_workbook(io.BytesIO(content))
    assert {"Umumiy", "Dinamika", "Hisoblagichlar", "Anomaliyalar", "Izoh"} <= set(wb.sheetnames)
    summary = wb["Umumiy"]
    values = {row[0].value: row[1].value for row in summary.iter_rows(min_row=2)}
    assert values["Tashkilot"] == "Alpha Industrial MChJ"
    assert values["Demo ma'lumotlari"] == "YO'Q"


def test_report_download_is_tenant_scoped(client, org_a, org_b, readings_factory):
    _meter(client, org_a, readings_factory)
    created = client.post("/api/v1/reports/export", json={"kind": "dashboard", "format": "csv",
                                                          "period": "month"},
                          headers=org_a["_headers"]).json()
    stolen = org_b["_client"].get(f"/api/v1/reports/{created['id']}/download",
                                  headers=org_b["_headers"])
    assert stolen.status_code == 404
    assert org_b["_client"].get("/api/v1/reports",
                                headers=org_b["_headers"]).json()["total"] == 0


def test_notifications_are_created_for_anomalies(client, org_a, readings_factory):
    meter = _meter(client, org_a, readings_factory)
    start = (datetime.now(UTC) - timedelta(days=20)).replace(minute=0, second=0, microsecond=0)
    readings_factory(org_a["active_organization"]["id"], meter["id"], start=start.isoformat(),
                     hours=24 * 18, kwh_pattern=lambda i, ts: 100)
    spike = start + timedelta(days=19)
    readings_factory(org_a["active_organization"]["id"], meter["id"], start=spike.isoformat(),
                     hours=24, kwh_pattern=lambda i, ts: 600 if i == 10 else 100)
    client.post("/api/v1/anomalies/detect?period=last_30_days", headers=org_a["_headers"])
    notes = client.get("/api/v1/notifications", headers=org_a["_headers"]).json()
    assert notes["total"] >= 1
    assert notes["unread"] >= 1
    first = notes["items"][0]
    assert first["type"] == "anomaly"
    client.post(f"/api/v1/notifications/{first['id']}/read", headers=org_a["_headers"])
    assert client.get("/api/v1/notifications", headers=org_a["_headers"]).json()["unread"] == 0
