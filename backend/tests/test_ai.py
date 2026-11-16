"""AI Advisor: grounding, numeric guard, multilingual output, persistence."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.services.ai.base import AIProvider


class HallucinatingProvider(AIProvider):
    """Pretends to be Gemini and invents a consumption figure."""
    name = "gemini"
    model = "fake-model"

    def complete(self, *, system: str, user: str) -> str:
        return ("Sizning iste'molingiz 1234567 kWh ni tashkil etdi va bu 987654321 UZS "
                "tejamkorlik beradi.")


class FaithfulProvider(AIProvider):
    name = "gemini"
    model = "fake-model"

    def complete(self, *, system: str, user: str) -> str:
        # 2400 kWh / 240 readings come from the fact bundle
        return "Jami iste'mol 2400.0 kWh, o'qishlar soni 240."


def _seed(client, org_a, readings_factory, *, hours=240, tariff="450", serial="AI-1"):
    meter = client.post("/api/v1/meters", json={"name": f"AI meter {serial}",
                                                "serial_number": serial},
                        headers=org_a["_headers"]).json()
    if tariff:
        client.post("/api/v1/tariffs", json={"name": "AI tariff", "price_per_kwh": tariff,
                                             "valid_from": "2025-01-01", "is_default": True},
                    headers=org_a["_headers"])
    # The advisor answers about rolling windows ending today, so the fixture data
    # must be recent: start 12 days ago and run forward for `hours`.
    start = (datetime.now(UTC) - timedelta(days=12)).replace(minute=0, second=0, microsecond=0)
    readings_factory(org_a["active_organization"]["id"], meter["id"],
                     start=start.isoformat(), hours=hours)
    return meter


def test_rule_based_answer_is_grounded_in_database(client, org_a, readings_factory):
    _seed(client, org_a, readings_factory, hours=240)
    r = client.post("/api/v1/ai/chat", json={
        "question": "Bu davrda qancha elektr iste'mol qildik?",
        "language": "uz", "period": "last_30_days"}, headers=org_a["_headers"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["intent"] == "total_consumption"
    assert body["provider"] == "rule_based"
    assert body["grounding"]["passed"] is True
    assert Decimal(str(body["measured_facts"]["consumption_kwh"])) == Decimal("2400.0000")
    assert "2 400" in body["answer"] or "2400" in body["answer"]
    # the three-tier disclosure is always present
    assert set(body["disclosure"]) == {"measured", "estimated", "suggested"}
    assert body["limitations"]


@pytest.mark.parametrize("language,needle", [("uz", "Jami iste'mol"), ("ru", "Общее потребление"),
                                             ("en", "Total consumption")])
def test_multilingual_answers(client, org_a, readings_factory, language, needle):
    _seed(client, org_a, readings_factory, hours=48, tariff=None)
    body = client.post("/api/v1/ai/chat", json={
        "question": "How much did we consume?", "language": language,
        "period": "last_30_days"}, headers=org_a["_headers"]).json()
    assert needle in body["answer"]


def test_numeric_guard_rejects_hallucinated_figures(client, org_a, readings_factory, monkeypatch):
    _seed(client, org_a, readings_factory, hours=240)
    import app.services.ai.advisor as advisor
    monkeypatch.setattr(advisor, "get_provider", lambda language="uz": HallucinatingProvider())

    body = client.post("/api/v1/ai/chat", json={
        "question": "Qancha iste'mol qildik?", "language": "uz"}, headers=org_a["_headers"]).json()
    assert body["grounding"]["passed"] is False
    assert "1234567" in " ".join(body["grounding"]["rejected_numbers"]) or \
           "1234567" in body["grounding"]["rejected_numbers"]
    # the invented numbers never reach the answer text
    assert "1234567" not in body["answer"]
    assert "987654321" not in body["answer"]
    assert "2400" in body["answer"].replace(" ", "")       # real figure from the DB
    assert "fact bundle" in body["grounding"]["note"].lower()


def test_numeric_guard_accepts_faithful_narration(client, org_a, readings_factory, monkeypatch):
    _seed(client, org_a, readings_factory, hours=240)
    import app.services.ai.advisor as advisor
    monkeypatch.setattr(advisor, "get_provider", lambda language="uz": FaithfulProvider())
    body = client.post("/api/v1/ai/chat", json={
        "question": "Qancha iste'mol qildik?", "language": "uz"}, headers=org_a["_headers"]).json()
    assert body["grounding"]["passed"] is True
    assert body["provider"] == "gemini"
    assert body["model"] == "fake-model"
    assert "2400" in body["answer"]


def test_advisor_never_invents_cost_without_tariff(client, org_a, readings_factory):
    _seed(client, org_a, readings_factory, hours=48, tariff=None)
    body = client.post("/api/v1/ai/chat", json={
        "question": "Bu oy qancha to'laymiz?", "language": "uz"}, headers=org_a["_headers"]).json()
    assert body["measured_facts"]["estimated_cost"] is None
    assert "tarif" in body["answer"].lower()


def test_advisor_handles_empty_organization_honestly(client, org_a):
    body = client.post("/api/v1/ai/chat", json={
        "question": "What were the biggest anomalies?", "language": "en"},
        headers=org_a["_headers"]).json()
    assert body["intent"] == "biggest_anomalies"
    assert Decimal(str(body["measured_facts"]["consumption_kwh"])) == Decimal("0")
    assert body["grounding"]["passed"] is True
    assert "0" in body["answer"] or "no data" in body["answer"].lower() or "yo'q" in body["answer"]


def test_intent_routing(client, org_a, readings_factory):
    _seed(client, org_a, readings_factory, hours=240)
    cases = {
        "Nima uchun kecha iste'mol oshdi?": "why_increase",
        "Eng katta anomaliyalar qaysilar?": "biggest_anomalies",
        "Qaysi hisoblagich eng ko'p iste'mol qiladi?": "top_meter",
        "Qanday tejash imkoniyatlari bor?": "savings",
        "Keyingi oy uchun prognoz qancha?": "forecast_cost",
    }
    for question, expected in cases.items():
        body = client.post("/api/v1/ai/chat", json={"question": question, "language": "uz"},
                           headers=org_a["_headers"]).json()
        assert body["intent"] == expected, (question, body["intent"])


def test_insights_are_persisted_and_isolated(client, org_a, org_b, readings_factory):
    _seed(client, org_a, readings_factory, hours=24)
    client.post("/api/v1/ai/chat", json={"question": "Qancha iste'mol?", "language": "uz"},
                headers=org_a["_headers"])
    mine = client.get("/api/v1/ai/insights", headers=org_a["_headers"]).json()
    assert mine["total"] >= 1
    assert org_b["_client"].get("/api/v1/ai/insights",
                                headers=org_b["_headers"]).json()["total"] == 0


def test_analyze_endpoint_returns_structured_blocks(client, org_a, readings_factory):
    _seed(client, org_a, readings_factory, hours=240)
    body = client.post("/api/v1/ai/analyze", json={"period": "last_30_days", "language": "uz"},
                       headers=org_a["_headers"]).json()
    assert set(body) >= {"answer", "measured_facts", "estimates", "suggestions", "limitations"}
    assert isinstance(body["suggestions"], list)
