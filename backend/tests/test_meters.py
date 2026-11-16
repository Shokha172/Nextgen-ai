"""Meter management and reading semantics (kWh energy vs kW power)."""
from __future__ import annotations

from decimal import Decimal


def test_create_meter_and_kw_derivation(client, org_a):
    created = client.post("/api/v1/meters", json={
        "name": "Main Infeed", "serial_number": "MER-001", "department": "Melting",
        "interval_minutes": 30, "multiplier": "2.0"}, headers=org_a["_headers"])
    assert created.status_code == 201, created.text
    meter = created.json()
    assert meter["unit"] == "kWh"
    assert meter["meter_type"] == "interval"

    # 60 kWh over 30 minutes with a 2x CT multiplier -> 120 kWh -> 240 kW average
    reading = client.post(f"/api/v1/meters/{meter['id']}/readings", json={
        "ts": "2026-04-02T08:00:00Z", "consumption_kwh": 60},
        headers=org_a["_headers"])
    assert reading.status_code == 201, reading.text
    body = reading.json()
    assert Decimal(body["consumption_kwh"]) == Decimal("120.0000")   # energy (kWh)
    assert Decimal(body["power_kw"]) == Decimal("240.0000")          # power (kW)
    assert body["interval_minutes"] == 30


def test_duplicate_serial_rejected_within_org(client, org_a):
    payload = {"name": "Meter X", "serial_number": "DUP-9"}
    assert client.post("/api/v1/meters", json=payload, headers=org_a["_headers"]).status_code == 201
    again = client.post("/api/v1/meters", json=payload, headers=org_a["_headers"])
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "duplicate_serial"


def test_same_serial_allowed_in_different_orgs(client, org_a, org_b):
    payload = {"name": "Shared Serial", "serial_number": "SAME-1"}
    assert client.post("/api/v1/meters", json=payload, headers=org_a["_headers"]).status_code == 201
    assert org_b["_client"].post("/api/v1/meters", json=payload,
                                 headers=org_b["_headers"]).status_code == 201


def test_duplicate_reading_timestamp_rejected(client, org_a):
    meter = client.post("/api/v1/meters", json={"name": "Hourly", "serial_number": "H-1"},
                        headers=org_a["_headers"]).json()
    body = {"ts": "2026-04-03T00:00:00Z", "consumption_kwh": 10}
    assert client.post(f"/api/v1/meters/{meter['id']}/readings", json=body,
                       headers=org_a["_headers"]).status_code == 201
    dup = client.post(f"/api/v1/meters/{meter['id']}/readings", json=body,
                      headers=org_a["_headers"])
    assert dup.status_code == 409
    assert dup.json()["error"]["code"] == "duplicate_reading"


def test_negative_consumption_rejected(client, org_a):
    meter = client.post("/api/v1/meters", json={"name": "Neg", "serial_number": "N-1"},
                        headers=org_a["_headers"]).json()
    r = client.post(f"/api/v1/meters/{meter['id']}/readings",
                    json={"ts": "2026-04-03T01:00:00Z", "consumption_kwh": -5},
                    headers=org_a["_headers"])
    assert r.status_code == 422


def test_meter_stats_rollup(client, org_a):
    meter = client.post("/api/v1/meters", json={"name": "Stats", "serial_number": "ST-1"},
                        headers=org_a["_headers"]).json()
    for hour, kwh in ((0, 10), (1, 20), (2, 30)):
        client.post(f"/api/v1/meters/{meter['id']}/readings",
                    json={"ts": f"2026-04-04T0{hour}:00:00Z", "consumption_kwh": kwh},
                    headers=org_a["_headers"])
    listing = client.get("/api/v1/meters", headers=org_a["_headers"]).json()
    row = next(m for m in listing["items"] if m["id"] == meter["id"])
    assert row["readings"] == 3
    assert Decimal(row["total_kwh"]) == Decimal("60.0000")


def test_coverage_endpoint_reports_gaps(client, org_a):
    meter = client.post("/api/v1/meters", json={"name": "Gappy", "serial_number": "G-1"},
                        headers=org_a["_headers"]).json()
    for hour in (0, 1, 3):  # hour 2 missing
        client.post(f"/api/v1/meters/{meter['id']}/readings",
                    json={"ts": f"2026-04-05T0{hour}:00:00Z", "consumption_kwh": 5},
                    headers=org_a["_headers"])
    cov = client.get(f"/api/v1/meters/{meter['id']}/coverage"
                     f"?start=2026-04-05T00:00:00Z&end=2026-04-05T04:00:00Z",
                     headers=org_a["_headers"])
    assert cov.status_code == 200
    assert cov.json() == {"expected_intervals": 4, "present_intervals": 3, "coverage_pct": 75.0}
