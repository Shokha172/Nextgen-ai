"""Anomaly detection: precision, explainability, and the anti-false-positive guards."""
from __future__ import annotations

from decimal import Decimal

LOCAL_START = "2026-01-31T19:00:00"     # 01.02.2026 00:00 local
# Explicit detection window so the assertions never depend on "today".
WINDOW = "start=2026-01-31T19:00:00Z&end=2026-02-23T19:00:00Z"


def _noisy(base: float):
    """A flat baseline has zero MAD, so a z-score is mathematically undefined —
    real meters are never perfectly flat, so fixtures include a little variance."""
    # vary per DAY, not per hour: 24 is divisible by 3, so an i%3 pattern would make
    # every hour-of-day perfectly flat again and leave the MAD (hence z) undefined.
    return lambda i, ts: base * (1.03 if (i // 24) % 3 == 0 else
                                 0.97 if (i // 24) % 3 == 1 else 1.0)


def _meter_with_baseline(client, org_a, readings_factory, *, days=21, base=100.0,
                         serial="ANOM-1", max_power_kw=None):
    body = {"name": f"Anomaly meter {serial}", "serial_number": serial}
    if max_power_kw:
        body["max_power_kw"] = str(max_power_kw)
    meter = client.post("/api/v1/meters", json=body, headers=org_a["_headers"]).json()
    readings_factory(org_a["active_organization"]["id"], meter["id"], start=LOCAL_START,
                     hours=days * 24, kwh_pattern=_noisy(base))
    return meter


def test_single_spike_is_detected_and_explained(client, org_a, readings_factory):
    meter = _meter_with_baseline(client, org_a, readings_factory, days=21)
    readings_factory(org_a["active_organization"]["id"], meter["id"],
                     start="2026-02-21T19:00:00", hours=24,
                     kwh_pattern=lambda i, ts: 400.0 if (i + 14) % 24 == 14
                     else 100.0 * (1.03 if (i // 24) % 3 == 0 else
                                   0.97 if (i // 24) % 3 == 1 else 1.0))

    r = client.post(f"/api/v1/anomalies/detect?{WINDOW}",
                    headers=org_a["_headers"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["count"] >= 1
    hit = max(body["anomalies"], key=lambda a: float(a["deviation_pct"]))
    assert Decimal(str(hit["observed_kwh"])) == Decimal("400")
    # baseline is the median of the same hour/regime across days: ~100 kWh
    assert abs(Decimal(str(hit["expected_kwh"])) - Decimal("100")) <= Decimal("6")
    assert Decimal("280") <= Decimal(str(hit["deviation_pct"])) <= Decimal("315")
    assert hit["severity"] in {"high", "critical"}
    assert hit["method"] in {"time_of_day", "rolling_zscore"}
    # explanation is numeric and available in all three product languages
    assert "400" in hit["explanation"]["uz"]
    assert "kWh" in hit["explanation"]["en"]
    assert hit["explanation"]["ru"]
    assert hit["details"]["z_score"] is not None


def test_sustained_level_change_is_not_flagged(client, org_a, readings_factory):
    """A new operating regime (e.g. a second shift) must not be reported as an anomaly."""
    meter = _meter_with_baseline(client, org_a, readings_factory, days=21, serial="ANOM-2")
    # 12 consecutive hours at 2.5x during the last day
    readings_factory(org_a["active_organization"]["id"], meter["id"],
                     start="2026-02-21T19:00:00", hours=24,
                     kwh_pattern=lambda i, ts: 250.0 if 6 <= (i + 14) % 24 <= 17 else 100.0)
    body = client.post(f"/api/v1/anomalies/detect?{WINDOW}&persist=false",
                       headers=org_a["_headers"]).json()
    flagged_times = {str(a["observed_kwh"]) for a in body["anomalies"]}
    assert "250.0000" not in flagged_times
    assert any("sustained level change" in note for note in body["notes"])


def test_power_ceiling_detector(client, org_a, readings_factory):
    meter = _meter_with_baseline(client, org_a, readings_factory, days=10, base=40.0,
                                 serial="ANOM-3", max_power_kw=50)
    readings_factory(org_a["active_organization"]["id"], meter["id"],
                     start="2026-02-10T19:00:00", hours=24,
                     kwh_pattern=lambda i, ts: 180.0 if (i + 14) % 24 == 10 else 40.0)
    body = client.post(f"/api/v1/anomalies/detect?{WINDOW}&persist=false",
                       headers=org_a["_headers"]).json()
    methods = {a["method"] for a in body["anomalies"]}
    assert "threshold" in methods
    thr = next(a for a in body["anomalies"] if a["method"] == "threshold")
    assert thr["details"]["limit"] == "50"
    assert thr["severity"] == "critical"


def test_no_false_positives_on_clean_data(client, org_a, readings_factory):
    _meter_with_baseline(client, org_a, readings_factory, days=21, serial="ANOM-4")
    body = client.post(f"/api/v1/anomalies/detect?{WINDOW}&persist=false",
                       headers=org_a["_headers"]).json()
    assert body["count"] == 0


def test_anomalies_are_persisted_listed_and_acknowledged(client, org_a, readings_factory):
    meter = _meter_with_baseline(client, org_a, readings_factory, days=10, serial="ANOM-5")
    readings_factory(org_a["active_organization"]["id"], meter["id"],
                     start="2026-02-10T19:00:00", hours=24,
                     kwh_pattern=lambda i, ts: 300.0 if (i + 14) % 24 == 11 else 100.0)
    detected = client.post(f"/api/v1/anomalies/detect?{WINDOW}",
                           headers=org_a["_headers"]).json()
    assert detected["persisted"] is True

    listed = client.get("/api/v1/anomalies", headers=org_a["_headers"]).json()
    assert listed["total"] >= 1
    item = listed["items"][0]
    assert set(item["explanations"]) == {"uz", "ru", "en"}
    assert item["acknowledged"] is False

    ack = client.post(f"/api/v1/anomalies/{item['id']}/acknowledge",
                      headers=org_a["_headers"])
    assert ack.status_code == 200
    assert ack.json()["acknowledged"] is True
    assert client.get("/api/v1/anomalies?acknowledged=false",
                      headers=org_a["_headers"]).json()["total"] == 0


def test_detection_is_idempotent(client, org_a, readings_factory):
    meter = _meter_with_baseline(client, org_a, readings_factory, days=10, serial="ANOM-6")
    readings_factory(org_a["active_organization"]["id"], meter["id"],
                     start="2026-02-10T19:00:00", hours=24,
                     kwh_pattern=lambda i, ts: 300.0 if (i + 14) % 24 == 11 else 100.0)
    first = client.post(f"/api/v1/anomalies/detect?{WINDOW}",
                        headers=org_a["_headers"]).json()
    second = client.post(f"/api/v1/anomalies/detect?{WINDOW}",
                         headers=org_a["_headers"]).json()
    stored = client.get("/api/v1/anomalies", headers=org_a["_headers"]).json()["total"]
    assert first["count"] == second["count"] == stored     # UNIQUE(meter, ts, method)


def test_anomaly_isolation_between_orgs(client, org_a, org_b, readings_factory):
    meter = _meter_with_baseline(client, org_a, readings_factory, days=10, serial="ANOM-7")
    readings_factory(org_a["active_organization"]["id"], meter["id"],
                     start="2026-02-10T19:00:00", hours=24,
                     kwh_pattern=lambda i, ts: 300.0 if (i + 14) % 24 == 11 else 100.0)
    client.post(f"/api/v1/anomalies/detect?{WINDOW}", headers=org_a["_headers"])
    mine = client.get("/api/v1/anomalies", headers=org_a["_headers"]).json()["items"][0]

    assert org_b["_client"].get("/api/v1/anomalies",
                                headers=org_b["_headers"]).json()["total"] == 0
    stolen = org_b["_client"].post(f"/api/v1/anomalies/{mine['id']}/acknowledge",
                                   headers=org_b["_headers"])
    assert stolen.status_code == 404
