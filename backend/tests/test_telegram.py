"""Telegram integration: linking security, environment isolation, bot service plane."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, text

DEMO_KEY = "demo-key-for-tests"
OFFICIAL_KEY = "official-key-for-tests"


def _bot_headers(mode: str) -> dict:
    return {"X-Bot-Service-Key": DEMO_KEY if mode == "demo" else OFFICIAL_KEY,
            "X-Bot-Mode": mode}


def _link_official(client, org, telegram_user_id=555000111):
    code = client.post("/api/v1/telegram/link", headers=org["_headers"]).json()
    assert code["bot_mode"] == "official"
    r = client.post(f"/api/v1/telegram/service/link?code={code['code']}",
                    json={"telegram_user_id": telegram_user_id,
                          "telegram_username": "operator"},
                    headers=_bot_headers("official"))
    assert r.status_code == 200, r.text
    return code, r.json()


def test_link_code_is_hashed_and_single_use(client, org_a, admin_engine):
    code = client.post("/api/v1/telegram/link", headers=org_a["_headers"]).json()
    assert code["bot_mode"] == "official"
    assert code["expires_in_minutes"] == 10

    with admin_engine.begin() as conn:
        stored = conn.execute(text(
            "select code_hash from telegram_link_codes limit 1")).scalar()
    assert stored != code["code"], "the plaintext code must never be stored"

    first = client.post(f"/api/v1/telegram/service/link?code={code['code']}",
                        json={"telegram_user_id": 111}, headers=_bot_headers("official"))
    assert first.status_code == 200, first.text
    assert first.json()["organization_name"] == "Alpha Industrial MChJ"

    # replaying the same code is refused
    second = client.post(f"/api/v1/telegram/service/link?code={code['code']}",
                         json={"telegram_user_id": 222}, headers=_bot_headers("official"))
    assert second.status_code == 422
    assert second.json()["error"]["code"] == "link_code_invalid"


def test_expired_link_code_rejected(client, org_a, admin_engine):
    code = client.post("/api/v1/telegram/link", headers=org_a["_headers"]).json()
    with admin_engine.begin() as conn:
        conn.execute(text("update telegram_link_codes set expires_at = :e"),
                     {"e": datetime.now(UTC) - timedelta(minutes=1)})
    r = client.post(f"/api/v1/telegram/service/link?code={code['code']}",
                    json={"telegram_user_id": 333}, headers=_bot_headers("official"))
    assert r.status_code == 422


def test_tampered_link_code_rejected(client, org_a):
    client.post("/api/v1/telegram/link", headers=org_a["_headers"])
    r = client.post("/api/v1/telegram/service/link?code=WRONGCODE",
                    json={"telegram_user_id": 444}, headers=_bot_headers("official"))
    assert r.status_code == 422


def test_demo_credentials_cannot_use_an_official_code(client, org_a):
    code = client.post("/api/v1/telegram/link", headers=org_a["_headers"]).json()
    r = client.post(f"/api/v1/telegram/service/link?code={code['code']}",
                    json={"telegram_user_id": 555}, headers=_bot_headers("demo"))
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "link_environment_mismatch"


def test_service_key_is_required_and_mode_specific(client, org_a):
    assert client.get("/api/v1/telegram/service/dashboard?telegram_user_id=1").status_code == 401
    bad = client.get("/api/v1/telegram/service/dashboard?telegram_user_id=1",
                     headers={"X-Bot-Service-Key": "nope", "X-Bot-Mode": "official"})
    assert bad.status_code == 401
    # the demo key cannot impersonate the official bot
    crossed = client.get("/api/v1/telegram/service/dashboard?telegram_user_id=1",
                         headers={"X-Bot-Service-Key": DEMO_KEY, "X-Bot-Mode": "official"})
    assert crossed.status_code == 401


def test_unlinked_telegram_user_is_refused(client, org_a):
    r = client.get("/api/v1/telegram/service/dashboard?telegram_user_id=999999",
                   headers=_bot_headers("official"))
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "not_linked"


def test_official_bot_reads_only_the_linked_organization(client, org_a, org_b, readings_factory):
    from datetime import datetime
    meter = client.post("/api/v1/meters", json={"name": "Bot meter", "serial_number": "BOT-1"},
                        headers=org_a["_headers"]).json()
    start = (datetime.now(UTC) - timedelta(days=3)).replace(minute=0, second=0, microsecond=0)
    readings_factory(org_a["active_organization"]["id"], meter["id"], start=start.isoformat(),
                     hours=48, kwh_pattern=lambda i, ts: 10)
    _link_official(client, org_a)

    body = client.get("/api/v1/telegram/service/dashboard?telegram_user_id=555000111&period=last_30_days",
                      headers=_bot_headers("official"))
    assert body.status_code == 200, body.text
    assert body.json()["has_data"] is True
    # the bot passes no organization id anywhere; org B stays invisible
    assert client.get("/api/v1/telegram/service/anomalies?telegram_user_id=555000111",
                      headers=_bot_headers("official")).json()["total"] == 0
    assert org_b["_client"].get("/api/v1/meters", headers=org_b["_headers"]).json()["total"] == 0


def test_demo_bot_session_is_confined_to_the_demo_org(client, admin_engine):
    # seed a demo organization directly (the seed script does this in real life)
    with admin_engine.begin() as conn:
        org_id = conn.execute(text("""
            insert into organizations (id, name, slug, is_demo, industry)
            values (gen_random_uuid(), 'Demo Org', 'demo-test', true, 'manufacturing')
            returning id""")).scalar()
        user_id = conn.execute(text("""
            insert into users (id, email, password_hash, full_name, is_demo)
            values (gen_random_uuid(), 'demo-bot@nextgen.uz', 'x', 'Demo Owner', true)
            returning id""")).scalar()
        conn.execute(text("""
            insert into organization_members (id, organization_id, user_id, role, status)
            values (gen_random_uuid(), :org, :user, 'owner', 'active')"""),
            {"org": org_id, "user": user_id})

    session = client.post("/api/v1/telegram/service/demo-session",
                          json={"telegram_user_id": 777, "telegram_username": "guest"},
                          headers=_bot_headers("demo"))
    assert session.status_code == 200, session.text
    assert session.json()["is_demo"] is True
    me = client.get("/api/v1/telegram/service/me?telegram_user_id=777",
                    headers=_bot_headers("demo"))
    assert me.status_code == 200
    assert me.json()["is_demo"] is True
    # the official bot must not be able to use the demo session
    official = client.get("/api/v1/telegram/service/me?telegram_user_id=777",
                          headers=_bot_headers("official"))
    assert official.status_code == 401


def test_demo_bot_cannot_upload_files(client, admin_engine):
    with admin_engine.begin() as conn:
        org_id = conn.execute(text("""
            insert into organizations (id, name, slug, is_demo)
            values (gen_random_uuid(), 'Demo Org', 'demo-test-2', true) returning id""")).scalar()
        user_id = conn.execute(text("""
            insert into users (id, email, password_hash, full_name, is_demo)
            values (gen_random_uuid(), 'demo-bot2@nextgen.uz', 'x', 'Demo Owner', true)
            returning id""")).scalar()
        conn.execute(text("""
            insert into organization_members (id, organization_id, user_id, role, status)
            values (gen_random_uuid(), :org, :user, 'owner', 'active')"""),
            {"org": org_id, "user": user_id})
    client.post("/api/v1/telegram/service/demo-session",
                json={"telegram_user_id": 888}, headers=_bot_headers("demo"))
    r = client.post("/api/v1/telegram/service/upload",
                    files={"file": ("data.csv", b"timestamp,consumption_kwh\n2026-01-01 00:00,10\n")},
                    data={"telegram_user_id": "888"}, headers=_bot_headers("demo"))
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "demo_read_only"


def test_web_unlink_revokes_bot_access(client, org_a):
    _link_official(client, org_a)
    accounts = client.get("/api/v1/telegram/accounts", headers=org_a["_headers"]).json()
    assert len(accounts["items"]) == 1
    client.delete(f"/api/v1/telegram/accounts/{accounts['items'][0]['id']}",
                  headers=org_a["_headers"])
    after = client.get("/api/v1/telegram/service/me?telegram_user_id=555000111",
                       headers=_bot_headers("official"))
    assert after.status_code == 401


def test_another_org_cannot_revoke_a_link(client, org_a, org_b):
    _link_official(client, org_a)
    accounts = client.get("/api/v1/telegram/accounts", headers=org_a["_headers"]).json()
    stolen = org_b["_client"].delete(f"/api/v1/telegram/accounts/{accounts['items'][0]['id']}",
                                     headers=org_b["_headers"])
    assert stolen.status_code == 404
    assert client.get("/api/v1/telegram/service/me?telegram_user_id=555000111",
                      headers=_bot_headers("official")).status_code == 200


def test_telegram_webhook_secret_check(client):
    r = client.post("/api/v1/telegram/webhook", json={"update_id": 1})
    # no secret configured in tests -> accepted
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_me_exposes_saved_language_and_alert_preference(client, org_a):
    """The bot rebuilds its session from /me, so the saved language must be there."""
    _link_official(client, org_a, telegram_user_id=555000777)
    me = client.get("/api/v1/telegram/service/me?telegram_user_id=555000777",
                    headers=_bot_headers("official")).json()
    assert me["language"] == "uz"          # new accounts default to Uzbek
    assert me["alerts_enabled"] is True

    set_lang = client.post("/api/v1/telegram/service/language?telegram_user_id=555000777"
                           "&language=ru", headers=_bot_headers("official"))
    assert set_lang.status_code == 200
    after = client.get("/api/v1/telegram/service/me?telegram_user_id=555000777",
                       headers=_bot_headers("official")).json()
    assert after["language"] == "ru"       # survives a bot restart

    toggled = client.post("/api/v1/telegram/service/alerts?telegram_user_id=555000777",
                          headers=_bot_headers("official")).json()
    assert toggled["alerts_enabled"] is False
    assert client.get("/api/v1/telegram/service/me?telegram_user_id=555000777",
                      headers=_bot_headers("official")).json()["alerts_enabled"] is False
