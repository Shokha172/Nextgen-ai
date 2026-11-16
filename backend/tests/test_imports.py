"""Import pipeline: detection, cumulative conversion, resets, duplicates, gaps,
and end-to-end persistence of a real CSV through the API."""
from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


def _meter(client, headers, serial="MER-100", **extra):
    body = {"name": f"Meter {serial}", "serial_number": serial, **extra}
    r = client.post("/api/v1/meters", json=body, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


def _upload(client, headers, meter_id, path, **form):
    with open(FIXTURES / path, "rb") as fh:
        data = {"meter_id": meter_id, **{k: str(v) for k, v in form.items()}}
        return client.post("/api/v1/imports", files={"file": (path, fh)}, data=data,
                           headers=headers)


# ------------------------------------------------------------------ pure functions
def test_column_detection_multilingual():
    from app.services.importer import detect_columns
    cases = [
        (["Vaqt", "Iste'mol (kWh)", "Hisoblagich raqami"], {"timestamp", "consumption_kwh", "meter_serial"}),
        (["Дата и время", "Расход, кВт·ч", "Счётчик"], {"timestamp", "consumption_kwh", "meter_serial"}),
        (["timestamp", "register_kwh"], {"timestamp", "register_kwh"}),
    ]
    for headers, expected in cases:
        mapping, _ = detect_columns(headers)
        assert expected <= set(mapping), (headers, mapping)


def test_number_and_timestamp_parsing():
    from app.services.importer import parse_number, parse_timestamp
    from zoneinfo import ZoneInfo
    assert parse_number("1 234,56") == Decimal("1234.56")
    assert parse_number("1,234.56") == Decimal("1234.56")
    assert parse_number("") is None
    tz = ZoneInfo("Asia/Tashkent")
    # naive input is interpreted as Tashkent local time (UTC+5), stored as UTC
    ts = parse_timestamp("2026-05-01 09:00", tz)
    assert ts.isoformat() == "2026-05-01T04:00:00+00:00"
    # explicit offsets are respected
    assert parse_timestamp("2026-05-01T09:00:00+05:00", tz).hour == 4


def test_cumulative_conversion_and_meter_reset():
    import pandas as pd
    from app.services.importer import analyse
    df = pd.DataFrame({
        "timestamp": ["2026-01-01 00:00", "2026-01-01 01:00", "2026-01-01 02:00",
                      "2026-01-01 03:00"],
        "register_kwh": ["1000", "1050", "1100", "10"],   # reset at 03:00
    })
    parsed = analyse(df, mapping={"timestamp": "timestamp", "register_kwh": "register_kwh"},
                     reading_type="cumulative", tz_name="Asia/Tashkent", interval_minutes=60,
                     multiplier=Decimal("1"))
    # first register establishes the baseline -> 2 usable intervals from 3 deltas
    assert len(parsed.valid) == 2
    assert [Decimal(str(r["consumption_kwh"])) for r in parsed.valid] == [Decimal("50"), Decimal("50")]
    assert len(parsed.resets) == 1
    assert "reset" in parsed.resets[0]["reason"]
    # never a negative consumption value
    assert all(r["consumption_kwh"] >= 0 for r in parsed.valid)


def test_interval_duplicates_and_gaps_detected():
    import pandas as pd
    from app.services.importer import analyse
    df = pd.DataFrame({
        "timestamp": ["2026-01-01 00:00", "2026-01-01 01:00", "2026-01-01 01:00",
                      "2026-01-01 04:00"],
        "consumption_kwh": ["10", "12", "12", "15"],
    })
    parsed = analyse(df, mapping={"timestamp": "timestamp", "consumption_kwh": "consumption_kwh"},
                     reading_type="interval", tz_name="Asia/Tashkent", interval_minutes=60,
                     multiplier=Decimal("1"))
    assert len(parsed.valid) == 3
    assert parsed.duplicates == 1
    assert parsed.missing_intervals == 2   # 02:00 and 03:00 absent


# ------------------------------------------------------------------- API workflow
def test_import_end_to_end(client, org_a):
    meter = _meter(client, org_a["_headers"])
    resp = _upload(client, org_a["_headers"], meter["id"], "interval_uz.csv")
    assert resp.status_code == 201, resp.text
    job = resp.json()

    # detection worked on Uzbek headers and comma decimals
    assert job["column_mapping"]["timestamp"] == "Vaqt"
    assert job["column_mapping"]["consumption_kwh"] == "Iste'mol (kWh)"
    assert job["status"] == "validated"
    assert job["duplicate_rows"] == 1
    assert job["invalid_rows"] == 2
    assert job["missing_intervals"] >= 1
    assert job["valid_rows"] == 21

    confirmed = client.post(f"/api/v1/imports/{job['id']}/confirm", json={},
                            headers=org_a["_headers"])
    assert confirmed.status_code == 200, confirmed.text
    result = confirmed.json()
    assert result["inserted"] == 21
    assert result["status"] == "confirmed"

    # readings are queryable and the peak-hour pattern survived the round trip
    readings = client.get(f"/api/v1/readings?meter_id={meter['id']}&page_size=100",
                          headers=org_a["_headers"]).json()
    assert readings["total"] == 21
    peak = [r for r in readings["items"] if r["ts"].endswith("10:00:00Z")]
    assert peak and Decimal(peak[0]["consumption_kwh"]) == Decimal("115.0000")

    # re-confirming is refused (idempotency guard)
    again = client.post(f"/api/v1/imports/{job['id']}/confirm", json={},
                        headers=org_a["_headers"])
    assert again.status_code == 422
    assert again.json()["error"]["code"] == "already_confirmed"


def test_reimport_skips_existing_duplicates(client, org_a):
    meter = _meter(client, org_a["_headers"], serial="MER-300")
    job1 = _upload(client, org_a["_headers"], meter["id"], "interval_uz.csv").json()
    assert client.post(f"/api/v1/imports/{job1['id']}/confirm", json={},
                       headers=org_a["_headers"]).json()["inserted"] == 21

    job2 = _upload(client, org_a["_headers"], meter["id"], "interval_uz.csv").json()
    assert job2["valid_rows"] == 0
    assert job2["duplicate_rows"] >= 21


def test_cumulative_import_through_api(client, org_a):
    meter = _meter(client, org_a["_headers"], serial="MER-200", meter_type="cumulative")
    resp = _upload(client, org_a["_headers"], meter["id"], "cumulative.csv",
                   reading_type="cumulative")
    assert resp.status_code == 201, resp.text
    job = resp.json()
    assert job["valid_rows"] == 22   # 23 register deltas minus the one spanning the reset
    confirm = client.post(f"/api/v1/imports/{job['id']}/confirm", json={},
                          headers=org_a["_headers"]).json()
    assert confirm["inserted"] == 22
    readings = client.get(f"/api/v1/readings?meter_id={meter['id']}&page_size=100",
                          headers=org_a["_headers"]).json()
    values = {Decimal(r["consumption_kwh"]) for r in readings["items"]}
    assert values == {Decimal("42.5000")}       # uniform register growth


def test_xlsx_template_roundtrip(client, org_a):
    meter = _meter(client, org_a["_headers"], serial="MER-001")
    resp = _upload(client, org_a["_headers"], meter["id"], "template.xlsx")
    assert resp.status_code == 201, resp.text
    assert resp.json()["valid_rows"] == 3


def test_template_downloads(client, org_a):
    csv_t = client.get("/api/v1/imports/templates/csv", headers=org_a["_headers"])
    assert csv_t.status_code == 200
    assert "consumption_kwh" in csv_t.text
    xlsx_t = client.get("/api/v1/imports/templates/xlsx", headers=org_a["_headers"])
    assert xlsx_t.status_code == 200
    assert xlsx_t.content[:2] == b"PK"


@pytest.mark.parametrize("filename,payload,code", [
    ("evil.exe", b"MZ\x90\x00", "unsupported_file_type"),
    ("fake.xlsx", b"#!/bin/sh\nrm -rf /", "invalid_upload"),
    ("binary.csv", b"\x00\x01\x02binary", "invalid_upload"),
])
def test_malicious_uploads_rejected(client, org_a, filename, payload, code):
    meter = _meter(client, org_a["_headers"], serial=f"M-{filename[:6]}")
    r = client.post("/api/v1/imports", files={"file": (filename, payload)},
                    data={"meter_id": meter["id"]}, headers=org_a["_headers"])
    assert r.status_code == 422, r.text
    assert r.json()["error"]["code"] == code


def test_import_requires_meter_and_role(client, org_a):
    with open(FIXTURES / "interval_uz.csv", "rb") as fh:
        r = client.post("/api/v1/imports", files={"file": ("x.csv", fh)},
                        data={}, headers=org_a["_headers"])
    assert r.status_code == 422


def test_cannot_import_into_another_orgs_meter(client, org_a, org_b):
    meter_b = _meter(org_b["_client"], org_b["_headers"], serial="B-METER")
    r = _upload(client, org_a["_headers"], meter_b["id"], "interval_uz.csv")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"
