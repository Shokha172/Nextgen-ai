"""Test harness.

The suite runs against a dedicated PostgreSQL database (`nextgen_test`) with the
real Alembic migration and the real RLS policies — no SQLite shortcuts, because
the isolation guarantees live in PostgreSQL.
"""
from __future__ import annotations

import os
import subprocess
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Detect if PostgreSQL is available on 5433 or configured via env
is_postgres = False
if "TEST_DATABASE_ADMIN_URL" in os.environ:
    ADMIN_URL = os.environ["TEST_DATABASE_ADMIN_URL"]
    APP_URL = os.getenv("TEST_DATABASE_URL", ADMIN_URL)
    is_postgres = True
else:
    try:
        import socket
        s = socket.create_connection(("127.0.0.1", 5433), timeout=0.3)
        s.close()
        ADMIN_URL = "postgresql+psycopg://postgres:postgres@127.0.0.1:5433/nextgen_test"
        APP_URL = "postgresql+psycopg://nextgen_app:nextgen_app_pw@127.0.0.1:5433/nextgen_test"
        is_postgres = True
    except Exception:
        TEST_DB_PATH = Path(ROOT) / "test_nextgen.db"
        ADMIN_URL = f"sqlite:///{TEST_DB_PATH.as_posix()}"
        APP_URL = f"sqlite:///{TEST_DB_PATH.as_posix()}"
        is_postgres = False
        import sqlite3
        from decimal import Decimal
        sqlite3.register_adapter(uuid.UUID, str)
        sqlite3.register_adapter(Decimal, float)

os.environ["ENVIRONMENT"] = "test"
os.environ["DATABASE_ADMIN_URL"] = ADMIN_URL
os.environ["DATABASE_URL"] = APP_URL
os.environ["JWT_SECRET"] = "test-secret-key-that-is-long-enough-1234567890"
os.environ["RATE_LIMIT_PER_MINUTE"] = "10000"
os.environ["LOGIN_RATE_LIMIT_PER_MINUTE"] = "10000"
os.environ["EXPOSE_DEV_TOKENS"] = "true"
os.environ["BOT_SERVICE_KEY_DEMO"] = "demo-key-for-tests"
os.environ["BOT_SERVICE_KEY_OFFICIAL"] = "official-key-for-tests"

sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def migrated_database():
    if is_postgres:
        env = {**os.environ, "ALEMBIC_DATABASE_URL": ADMIN_URL}
        subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"],
                       cwd=ROOT, env=env, check=True, capture_output=True)
    else:
        from app.core.db import Base, admin_engine as a_eng
        import app.models  # noqa: F401
        Base.metadata.create_all(a_eng)
    yield
    if not is_postgres:
        db_file = Path(ROOT) / "test_nextgen.db"
        if db_file.exists():
            try:
                db_file.unlink(missing_ok=True)
            except Exception:
                pass


@pytest.fixture(scope="session")
def admin_engine():
    kw = {"connect_args": {"check_same_thread": False}} if not is_postgres else {}
    engine = create_engine(ADMIN_URL, future=True, **kw)
    yield engine
    engine.dispose()


@pytest.fixture(scope="session")
def app_engine():
    kw = {"connect_args": {"check_same_thread": False}} if not is_postgres else {}
    engine = create_engine(APP_URL, future=True, **kw)
    yield engine
    engine.dispose()


@pytest.fixture(autouse=True)
def clean_database(admin_engine):
    """Truncate between tests; every test starts from a known-empty tenant space."""
    from app.core import rate_limit
    rate_limit.reset()
    with admin_engine.begin() as conn:
        if is_postgres:
            conn.execute(text("""
                TRUNCATE users, organizations, organization_members, meters, meter_readings,
                         tariffs, import_jobs, import_staging_rows, anomalies, forecasts, ai_insights, savings_reports,
                         reports, notifications, audit_logs, telegram_accounts, telegram_link_codes,
                         auth_sessions, password_reset_tokens
                RESTART IDENTITY CASCADE
            """))
        else:
            for table in ("auth_sessions", "password_reset_tokens", "telegram_link_codes", "telegram_accounts",
                          "audit_logs", "notifications", "reports", "savings_reports", "ai_insights", "forecasts",
                          "anomalies", "import_staging_rows", "import_jobs", "tariffs", "meter_readings", "meters",
                          "organization_members", "organizations", "users"):
                conn.execute(text(f"DELETE FROM {table}"))
    yield


@pytest.fixture
def client():
    """Function-scoped: one TestClient per test so cookies/headers never leak."""
    from app.main import app
    with TestClient(app) as c:
        yield c


@pytest.fixture
def anon(client):
    return client


def _register(client, *, email: str | None = None, org: str = "Test Works LLC",
              password: str = "Str0ng-Passw0rd!", name: str = "Test Owner") -> dict:
    email = email or f"user-{uuid.uuid4().hex[:10]}@example.uz"
    r = client.post("/api/v1/auth/register", json={
        "email": email, "password": password, "full_name": name,
        "organization_name": org, "locale": "uz"})
    assert r.status_code == 201, r.text
    data = r.json()
    data["_email"] = email
    data["_password"] = password
    data["_cookies"] = dict(r.cookies)
    return data


@pytest.fixture
def org_a(client):
    """A fully registered owner + organization, authenticated."""
    data = _register(client, org="Alpha Industrial MChJ")
    client.cookies.clear()
    token = data["token"]["access_token"]
    client.headers.update({"Authorization": f"Bearer {token}"})
    data["_headers"] = {"Authorization": f"Bearer {token}"}
    return data


@pytest.fixture
def org_b(client):
    """A second, independent tenant used for isolation tests."""
    fresh = TestClient(client.app)
    data = _register(fresh, org="Beta Textile MChJ")
    token = data["token"]["access_token"]
    data["_headers"] = {"Authorization": f"Bearer {token}"}
    data["_client"] = fresh
    return data


@pytest.fixture
def register(client):
    def _f(**kw):
        return _register(client, **kw)
    return _f


@pytest.fixture
def readings_factory(admin_engine):
    """Insert exact hourly readings straight into PostgreSQL for analytics tests.

    Bypassing the API is intentional: these tests assert on aggregation maths, so
    the fixture writes precisely known values (10 kWh per hour unless told otherwise).
    """
    from datetime import UTC, datetime, timedelta
    from decimal import Decimal

    def _insert(org_id, meter_id, *, start: str, hours: int, kwh_pattern=None,
                interval_minutes: int = 60):
        start_dt = datetime.fromisoformat(start).replace(tzinfo=UTC)
        rows = []
        for i in range(hours):
            ts = start_dt + timedelta(hours=i)
            kwh = (kwh_pattern(i, ts) if callable(kwh_pattern) else
                   (kwh_pattern[i] if kwh_pattern else 10))
            rows.append({"ts": ts, "kwh": Decimal(str(kwh))})
        if not rows:
            return []
        with admin_engine.begin() as conn:
            from app.models.meter import MeterReading
            insert_rows = [{
                "id": uuid.uuid4(),
                "organization_id": uuid.UUID(str(org_id)),
                "meter_id": uuid.UUID(str(meter_id)),
                "ts": r["ts"],
                "interval_minutes": interval_minutes,
                "consumption_kwh": r["kwh"],
                "power_kw": r["kwh"] * Decimal(60) / Decimal(interval_minutes),
                "source": "seed",
                "quality": "ok",
                "created_at": datetime.now(UTC),
            } for r in rows]
            conn.execute(MeterReading.__table__.insert(), insert_rows)
        return rows
    return _insert
