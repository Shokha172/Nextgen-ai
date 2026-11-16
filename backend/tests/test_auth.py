"""Authentication: registration, login, lockout, refresh rotation, reset, RBAC."""
from __future__ import annotations

import pytest


def test_register_creates_user_org_and_owner_membership(client):
    r = client.post("/api/v1/auth/register", json={
        "email": "Owner@Example.uz", "password": "Str0ng-Passw0rd!",
        "full_name": "Dilshod Karimov", "organization_name": "Toshkent Metall Zavodi"})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["user"]["email"] == "owner@example.uz"          # normalised
    assert body["role"] == "owner"
    assert body["active_organization"]["name"] == "Toshkent Metall Zavodi"
    assert body["token"]["access_token"]
    # httpOnly session cookies are set for the browser flow
    assert "ng_access" in r.cookies
    assert "ng_refresh" in r.cookies


def test_duplicate_email_rejected_case_insensitively(client):
    payload = {"email": "dup@example.uz", "password": "Str0ng-Passw0rd!", "full_name": "A B"}
    assert client.post("/api/v1/auth/register", json=payload).status_code == 201
    payload["email"] = "DUP@example.uz"
    r = client.post("/api/v1/auth/register", json=payload)
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "email_taken"


@pytest.mark.parametrize("password", ["short", "alllowercase", "12345678901"])
def test_weak_passwords_rejected(client, password):
    r = client.post("/api/v1/auth/register", json={
        "email": f"weak-{password[:3]}@example.uz", "password": password, "full_name": "Weak Pass"})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "validation_failed"


def test_login_and_me(client, org_a):
    r = client.post("/api/v1/auth/login",
                    json={"email": org_a["_email"], "password": org_a["_password"]})
    assert r.status_code == 200, r.text
    token = r.json()["token"]["access_token"]
    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["active_organization"]["role"] == "owner"


def test_login_wrong_password_and_no_user_enumeration(client, org_a):
    bad = client.post("/api/v1/auth/login",
                      json={"email": org_a["_email"], "password": "Wrong-Password1!"})
    missing = client.post("/api/v1/auth/login",
                          json={"email": "nobody@example.uz", "password": "Wrong-Password1!"})
    assert bad.status_code == missing.status_code == 401
    assert bad.json()["error"]["message"] == missing.json()["error"]["message"]


def test_account_lockout_after_repeated_failures(client, org_a):
    for _ in range(8):
        client.post("/api/v1/auth/login",
                    json={"email": org_a["_email"], "password": "Wrong-Password1!"})
    r = client.post("/api/v1/auth/login",
                    json={"email": org_a["_email"], "password": org_a["_password"]})
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "account_locked"


def test_refresh_rotates_and_old_token_is_burned(client, org_a):
    first = client.post("/api/v1/auth/login",
                        json={"email": org_a["_email"], "password": org_a["_password"]})
    refresh_1 = first.cookies.get("ng_refresh")
    assert refresh_1
    r2 = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_1})
    assert r2.status_code == 200, r2.text
    # replay of the burned token fails
    replay = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_1})
    assert replay.status_code == 401
    assert replay.json()["error"]["code"] == "refresh_invalid"


def test_logout_revokes_session_immediately(client, org_a):
    r = client.post("/api/v1/auth/logout", headers=org_a["_headers"])
    assert r.status_code == 200
    after = client.get("/api/v1/auth/me", headers=org_a["_headers"])
    assert after.status_code == 401
    assert after.json()["error"]["code"] == "session_revoked"


def test_password_reset_flow_revokes_sessions(client, org_a):
    forgot = client.post("/api/v1/auth/forgot-password", json={"email": org_a["_email"]})
    assert forgot.status_code == 200
    token = forgot.json()["dev_reset_token"]
    assert token, "dev tokens must be exposed in test mode"
    reset = client.post("/api/v1/auth/reset-password",
                        json={"token": token, "new_password": "N3w-Passw0rd!x"})
    assert reset.status_code == 200
    # old session is dead, old password rejected, new password works
    assert client.get("/api/v1/auth/me", headers=org_a["_headers"]).status_code == 401
    assert client.post("/api/v1/auth/login",
                       json={"email": org_a["_email"], "password": org_a["_password"]}
                       ).status_code == 401
    assert client.post("/api/v1/auth/login",
                       json={"email": org_a["_email"], "password": "N3w-Passw0rd!x"}
                       ).status_code == 200
    # a used reset token cannot be replayed
    again = client.post("/api/v1/auth/reset-password",
                        json={"token": token, "new_password": "An0ther-Passw0rd!"})
    assert again.status_code == 422


def test_unauthenticated_requests_are_401(client):
    for path in ("/api/v1/meters", "/api/v1/members", "/api/v1/organization", "/api/v1/auth/me"):
        r = client.get(path)
        assert r.status_code == 401, path
        assert r.json()["error"]["code"] in {"not_authenticated", "unauthorized"}


@pytest.mark.parametrize("token", ["garbage", "a.b.c", ""])
def test_invalid_tokens_rejected(client, token):
    r = client.get("/api/v1/meters", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401


def test_viewer_cannot_create_meter(client, register):
    owner = register(org="Role Test MChJ")
    headers = {"Authorization": f"Bearer {owner['token']['access_token']}"}
    invite = client.post("/api/v1/members/invite",
                         json={"email": "viewer@example.uz", "role": "viewer"}, headers=headers)
    assert invite.status_code == 201, invite.text

    viewer = register(email="viewer@example.uz", org=None if False else "Ignored Org")
    # the invitation was created before the account existed -> re-register binds it
    import uuid
    from app.core.db import AdminSessionLocal
    from app.models.organization import Organization, OrganizationMember
    from sqlalchemy import select

    with AdminSessionLocal() as s:
        org = s.scalar(select(Organization).where(Organization.name == "Role Test MChJ"))
        org_id = org.id
        member = s.scalar(select(OrganizationMember).where(
            OrganizationMember.organization_id == org_id,
            OrganizationMember.invited_email == "viewer@example.uz"
        ))
        member.user_id = uuid.UUID(str(viewer["user"]["id"]))
        member.status = "active"
        s.commit()

    viewer_login = client.post("/api/v1/auth/login", json={
        "email": "viewer@example.uz", "password": viewer["_password"],
        "organization_id": str(org_id)})
    assert viewer_login.status_code == 200, viewer_login.text
    viewer_headers = {"Authorization": f"Bearer {viewer_login.json()['token']['access_token']}"}

    # viewer: read yes, write no
    assert client.get("/api/v1/meters", headers=viewer_headers).status_code == 200
    denied = client.post("/api/v1/meters", json={"name": "Nope", "serial_number": "N1"},
                         headers=viewer_headers)
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "insufficient_role"
