"""Forecasting: method selection, backtested accuracy, cost grounding, honesty."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal


def _history(client, org_a, readings_factory, *, days=60, base=120.0, serial="FC-1",
             tariff="450"):
    meter = client.post("/api/v1/meters", json={"name": f"Forecast {serial}",
                                                "serial_number": serial},
                        headers=org_a["_headers"]).json()
    if tariff:
        client.post("/api/v1/tariffs", json={"name": "Forecast tariff", "price_per_kwh": tariff,
                                             "valid_from": "2025-01-01", "is_default": True},
                    headers=org_a["_headers"])
    start = (datetime.now(UTC) - timedelta(days=days)).replace(minute=0, second=0, microsecond=0)
    readings_factory(org_a["active_organization"]["id"], meter["id"],
                     start=start.isoformat(), hours=days * 24,
                     kwh_pattern=lambda i, ts: base * (1.6 if 8 <= ts.hour <= 19 else 0.4))
    return meter, start


def test_forecast_uses_seasonal_model_with_backtest(client, org_a, readings_factory):
    _history(client, org_a, readings_factory, days=60)
    r = client.get("/api/v1/forecast?horizon_days=30", headers=org_a["_headers"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["method"] == "seasonal"          # >= 28 days of history available
    assert body["horizon_days"] == 30
    assert len(body["points"]) == 30
    assert body["accuracy_mape"] is not None
    assert body["confidence"] in {"high", "medium"}
    assert body["limitations"], "limitations must always be stated"
    assert "not an invoice" in body["disclaimer"]
    # pattern: 12 h at 192 kWh + 12 h at 48 kWh = 2 880 kWh/day -> ~86 400 kWh / 30 days
    total = Decimal(str(body["total_kwh"]))
    assert Decimal("60000") < total < Decimal("110000")
    assert all(Decimal(str(p["consumption_kwh"])) >= 0 for p in body["points"])


def test_forecast_cost_requires_tariff(client, org_a, readings_factory):
    _history(client, org_a, readings_factory, days=45, tariff=None, serial="FC-2")
    body = client.get("/api/v1/forecast", headers=org_a["_headers"]).json()
    assert body["total_cost"] is None
    assert "No tariff is configured" in body["tariff"]["note"]


def test_forecast_cost_matches_tariff(client, org_a, readings_factory):
    _history(client, org_a, readings_factory, days=45, serial="FC-3", tariff="450")
    body = client.get("/api/v1/forecast", headers=org_a["_headers"]).json()
    expected = Decimal(str(body["total_kwh"])) * Decimal("450")
    assert abs(Decimal(str(body["total_cost"])) - expected) < Decimal("1")


def test_insufficient_history_is_rejected_not_faked(client, org_a):
    r = client.get("/api/v1/forecast", headers=org_a["_headers"])
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "insufficient_history"


def test_explicit_method_is_honoured_and_limited(client, org_a, readings_factory):
    _history(client, org_a, readings_factory, days=20, serial="FC-4")
    body = client.get("/api/v1/forecast?method=moving_average",
                      headers=org_a["_headers"]).json()
    assert body["method"] == "moving_average"
    seasonal = client.get("/api/v1/forecast?method=seasonal",
                          headers=org_a["_headers"]).json()
    # too little history for seasonality: the API says so instead of pretending
    assert any("at least 28" in note for note in seasonal["limitations"])


def test_forecast_is_organization_scoped(client, org_a, org_b, readings_factory):
    _history(client, org_a, readings_factory, days=45, serial="FC-5")
    b = org_b["_client"].get("/api/v1/forecast", headers=org_b["_headers"])
    assert b.status_code == 422          # org B has no data at all
    assert b.json()["error"]["code"] == "insufficient_history"
