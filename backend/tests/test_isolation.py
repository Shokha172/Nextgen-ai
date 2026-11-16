"""Multi-tenant isolation — the security core of the product.

Covers three independent layers:
  1. API authorization (a token for org A must never reach org B's resources)
  2. Claim tampering (org/role claims are re-validated against the database)
  3. PostgreSQL RLS (proven directly on a connection that bypasses the API)
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import jwt
import pytest
from sqlalchemy import text

from app.core.config import settings


def _meter(client, headers, name="Meter 1", serial="SN-1"):
    r = client.post("/api/v1/meters", json={"name": name, "serial_number": serial}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


def test_org_cannot_read_another_orgs_meter(client, org_a, org_b):
    meter_b = _meter(org_b["_client"], org_b["_headers"], name="Beta Meter", serial="B-1")

    # list: only own meters
    listing = client.get("/api/v1/meters", headers=org_a["_headers"])
    assert listing.status_code == 200
    assert listing.json()["total"] == 0

    # direct fetch of a foreign id is a 404, not a data leak
    detail = client.get(f"/api/v1/meters/{meter_b['id']}", headers=org_a["_headers"])
    assert detail.status_code == 404
    assert detail.json()["error"]["code"] == "not_found"


def test_org_cannot_mutate_another_orgs_meter(client, org_a, org_b):
    meter_b = _meter(org_b["_client"], org_b["_headers"], name="Beta Meter", serial="B-2")

    assert client.patch(f"/api/v1/meters/{meter_b['id']}",
                        json={"name": "Hijacked"}, headers=org_a["_headers"]).status_code == 404
    assert client.delete(f"/api/v1/meters/{meter_b['id']}",
                         headers=org_a["_headers"]).status_code == 404

    # unchanged for the legitimate owner
    check = org_b["_client"].get(f"/api/v1/meters/{meter_b['id']}", headers=org_b["_headers"])
    assert check.status_code == 200
    assert check.json()["name"] == "Beta Meter"


def test_foreign_meter_readings_are_not_listed(client, org_a, org_b):
    meter_b = _meter(org_b["_client"], org_b["_headers"], serial="B-3")
    added = org_b["_client"].post(
        f"/api/v1/meters/{meter_b['id']}/readings",
        json={"ts": "2026-03-01T10:00:00Z", "consumption_kwh": 42.5},
        headers=org_b["_headers"])
    assert added.status_code == 201, added.text

    leak = client.get("/api/v1/readings", headers=org_a["_headers"])
    assert leak.status_code == 200
    assert leak.json()["total"] == 0

    filtered = client.get(f"/api/v1/readings?meter_id={meter_b['id']}", headers=org_a["_headers"])
    assert filtered.json()["total"] == 0


def test_tampered_org_claim_is_rejected(client, org_a, org_b):
    """A forged `org` claim must fail against the membership table."""
    payload = jwt.decode(org_a["token"]["access_token"], settings.JWT_SECRET,
                         algorithms=[settings.JWT_ALG])
    org_b_id = org_b["active_organization"]["id"]
    payload["org"] = org_b_id
    forged = jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALG)

    r = client.get("/api/v1/meters", headers={"Authorization": f"Bearer {forged}"})
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "cross_org_denied"


def test_tampered_role_claim_grants_nothing(client, org_a):
    """Authorization uses the stored membership role, never the JWT claim."""
    payload = jwt.decode(org_a["token"]["access_token"], settings.JWT_SECRET,
                         algorithms=[settings.JWT_ALG])
    payload["role"] = "viewer"          # downgrade claim
    downgraded = jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALG)
    assert client.post("/api/v1/meters", json={"name": "Still Allowed", "serial_number": "OK-1"},
                       headers={"Authorization": f"Bearer {downgraded}"}).status_code == 201


def test_token_signed_with_wrong_secret_rejected(client, org_a):
    payload = jwt.decode(org_a["token"]["access_token"], settings.JWT_SECRET,
                         algorithms=[settings.JWT_ALG])
    forged = jwt.encode(payload, "attacker-secret-attacker-secret-123456", algorithm="HS256")
    r = client.get("/api/v1/meters", headers={"Authorization": f"Bearer {forged}"})
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "token_invalid"


def test_expired_token_rejected(client, org_a):
    payload = jwt.decode(org_a["token"]["access_token"], settings.JWT_SECRET,
                         algorithms=[settings.JWT_ALG])
    payload["exp"] = int(datetime(2020, 1, 1, tzinfo=UTC).timestamp())
    expired = jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALG)
    r = client.get("/api/v1/meters", headers={"Authorization": f"Bearer {expired}"})
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "token_expired"


def test_cross_org_attempt_is_audited(client, org_a, org_b, admin_engine):
    payload = jwt.decode(org_a["token"]["access_token"], settings.JWT_SECRET,
                         algorithms=[settings.JWT_ALG])
    payload["org"] = org_b["active_organization"]["id"]
    forged = jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALG)
    client.get("/api/v1/meters", headers={"Authorization": f"Bearer {forged}"})

    with admin_engine.begin() as conn:
        denied = conn.execute(text(
            "select count(*) from audit_logs where action='cross_org_denied'")).scalar()
    assert denied >= 1


def test_database_rls_blocks_cross_org_even_without_the_api(client, org_a, org_b, app_engine):
    """Layer 3: talk to PostgreSQL directly as the low-privilege application role.
    With no tenant bound it must see nothing; bound to A it must not see B."""
    if app_engine.dialect.name != "postgresql":
        pytest.skip("PostgreSQL RLS test requires PostgreSQL")
    org_a_id = org_a["active_organization"]["id"]
    org_b_id = org_b["active_organization"]["id"]
    meter_b = _meter(org_b["_client"], org_b["_headers"], name="Only Beta", serial="RLS-1")
    _meter(client, org_a["_headers"], name="Only Alpha", serial="RLS-2")

    with app_engine.connect() as conn:
        assert conn.execute(text("select count(*) from meters")).scalar() == 0  # fail closed
        conn.execute(text("select set_config('app.current_org', :o, false)"), {"o": org_a_id})
        names = [r[0] for r in conn.execute(text("select name from meters"))]
        assert names == ["Only Alpha"]
        # and a cross-tenant write is refused by the WITH CHECK clause
        with pytest.raises(Exception) as ctx:
            conn.execute(text(
                "insert into meters (organization_id, name, serial_number) "
                "values (:org, 'sneak', 'SNEAK-1')"), {"org": org_b_id})
        assert "row-level security" in str(ctx.value).lower()
