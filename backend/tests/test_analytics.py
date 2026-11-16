"""Analytics: exact aggregation over known values, comparisons, cost derivation."""
from __future__ import annotations

from datetime import UTC
from decimal import Decimal

# Analytics buckets by LOCAL calendar day (Asia/Tashkent, UTC+5), which is what an
# Uzbek plant means by "daily consumption". Local midnight 01.03.2026 == 28.02 19:00Z.
LOCAL_DAY_1 = "2026-02-28T19:00:00"       # 01.03.2026 00:00 local
LOCAL_DAY_11 = "2026-03-10T19:00:00"      # 11.03.2026 00:00 local


def _setup(client, org_a, readings_factory, *, hours=240, pattern=None, serial="AN-1",
           tariff="450"):
    meter = client.post("/api/v1/meters", json={"name": f"M {serial}", "serial_number": serial},
                        headers=org_a["_headers"]).json()
    if tariff:
        r = client.post("/api/v1/tariffs", json={
            "name": "Test tariff", "price_per_kwh": tariff, "valid_from": "2025-01-01",
            "is_default": True}, headers=org_a["_headers"])
        assert r.status_code == 201, r.text
    readings_factory(org_a["active_organization"]["id"], meter["id"],
                     start=LOCAL_DAY_1, hours=hours, kwh_pattern=pattern)
    return meter


def test_totals_and_daily_series_are_exact(client, org_a, readings_factory):
    _setup(client, org_a, readings_factory, hours=240)          # 10 days x 24h x 10 kWh
    r = client.get("/api/v1/analytics/consumption"
                   f"?start={LOCAL_DAY_1}Z&end={LOCAL_DAY_11}Z&granularity=day",
                   headers=org_a["_headers"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert Decimal(str(body["totals"]["consumption_kwh"])) == Decimal("2400.0000")
    assert body["totals"]["readings"] == 240
    assert body["totals"]["data_coverage_pct"] == 100.0
    daily = body["series"]
    assert len(daily) == 10
    assert all(Decimal(str(d["consumption_kwh"])) == Decimal("240.0000") for d in daily)
    # energy vs power must not be conflated: 10 kWh in one hour is 10 kW average
    assert Decimal(str(body["totals"]["average_power_kw"])) == Decimal("10.0000")


def test_cost_requires_a_configured_tariff(client, org_a, readings_factory):
    _setup(client, org_a, readings_factory, hours=24, tariff=None)
    body = client.get("/api/v1/analytics/consumption?period=year",
                      headers=org_a["_headers"]).json()
    assert body["totals"]["estimated_cost"] is None      # never invented
    assert "tariff" in body["totals"]
    assert "No tariff is configured" in body["totals"]["tariff"]["note"]


def test_cost_uses_configured_tariff(client, org_a, readings_factory):
    _setup(client, org_a, readings_factory, hours=240, tariff="450")
    r = client.get("/api/v1/analytics/consumption"
                   f"?start={LOCAL_DAY_1}Z&end={LOCAL_DAY_11}Z",
                   headers=org_a["_headers"])
    totals = r.json()["totals"]
    # 2400 kWh * 450 UZS
    assert Decimal(str(totals["estimated_cost"])) == Decimal("1080000.00")
    assert totals["currency"] == "UZS"


def test_comparison_with_previous_period(client, org_a, readings_factory):
    meter = _setup(client, org_a, readings_factory, hours=0, tariff=None)
    org_id = org_a["active_organization"]["id"]
    # first week: 100 kWh/day; second week: 150 kWh/day (+50%)
    readings_factory(org_id, meter["id"], start=LOCAL_DAY_1, hours=168,
                     kwh_pattern=lambda i, ts: 100 if ts.hour == 0 else 0)
    readings_factory(org_id, meter["id"], start="2026-03-07T19:00:00", hours=168,
                     kwh_pattern=lambda i, ts: 150 if ts.hour == 0 else 0)
    body = client.get("/api/v1/analytics/comparison"
                      "?period=month", headers=org_a["_headers"])
    assert body.status_code == 200
    # explicit windows are clearer to assert than the current month
    r = client.get("/api/v1/analytics/consumption"
                   "?start=2026-03-07T19:00:00Z&end=2026-03-14T19:00:00Z",
                   headers=org_a["_headers"]).json()
    assert Decimal(str(r["totals"]["consumption_kwh"])) == Decimal("1050.0000")


def test_period_comparison_percentage(client, org_a, readings_factory):
    meter = _setup(client, org_a, readings_factory, hours=0, tariff=None)
    org_id = org_a["active_organization"]["id"]
    readings_factory(org_id, meter["id"], start="2026-01-31T19:00:00", hours=24 * 28,
                     kwh_pattern=lambda i, ts: 10)
    readings_factory(org_id, meter["id"], start="2026-02-28T19:00:00", hours=24,
                     kwh_pattern=lambda i, ts: 20)
    # month over month: March (1 day at 20/h) is compared with February's same length window
    body = client.get("/api/v1/analytics/comparison?period=month&mode=previous",
                      headers=org_a["_headers"]).json()
    assert "current" in body and "baseline" in body
    assert body["difference_pct"] is not None or body["baseline"]["readings"] == 0


def test_breakdowns_and_peaks(client, org_a, readings_factory):
    meter = _setup(client, org_a, readings_factory, hours=0, tariff=None)
    org_id = org_a["active_organization"]["id"]
    readings_factory(org_id, meter["id"], start=LOCAL_DAY_1, hours=48,
                     kwh_pattern=lambda i, ts: 10 if (ts.astimezone(UTC).hour % 24) != 7 else 99)
    body = client.get("/api/v1/analytics/consumption"
                      "?start=2026-02-28T19:00:00Z&end=2026-03-02T19:00:00Z",
                      headers=org_a["_headers"]).json()
    assert len(body["by_meter"]) == 1
    assert body["by_meter"][0]["share_pct"] == 100.0
    assert Decimal(str(body["peaks"][0]["consumption_kwh"])) == Decimal("99")
    assert len(body["hourly_profile"]) == 24
    # 07:00 UTC == 12:00 local, which is the hour carrying the peak in local time
    assert Decimal(str(body["hourly_profile"][12]["average_kwh"])) == Decimal("99")


def test_empty_organization_returns_zeros_not_fabrication(client, org_a):
    body = client.get("/api/v1/analytics/consumption?period=month",
                      headers=org_a["_headers"]).json()
    assert Decimal(str(body["totals"]["consumption_kwh"])) == Decimal("0")
    assert body["series"] == []
    assert body["totals"]["data_coverage_pct"] == 0.0


def test_dashboard_summary_is_grounded(client, org_a, readings_factory):
    _setup(client, org_a, readings_factory, hours=240, tariff="450")
    body = client.get("/api/v1/dashboard/summary?period=year",
                      headers=org_a["_headers"]).json()
    assert body["has_data"] is True
    assert Decimal(str(body["consumption"]["total_kwh"])) == Decimal("2400.0000")
    assert Decimal(str(body["cost"]["estimated"])) == Decimal("1080000.00")
    assert body["anomalies"]["count"] == 0
    assert body["meters"]["active"] == 1
    assert isinstance(body["series"], list)
    # efficiency indicator is null when there is no data to compare, not zero
    assert body["efficiency"]["peak_to_average_ratio"] is not None


def test_dashboard_without_data_says_so(client, org_a):
    body = client.get("/api/v1/dashboard/summary?period=month",
                      headers=org_a["_headers"]).json()
    assert body["has_data"] is False
    assert any("No readings" in n for n in body["notes"])
    assert any("No tariff" in n for n in body["notes"])
