"""Database engines and session factories.

Two connection paths, deliberately:
  * admin engine  -> owner role (migrations, seeds, auth-table maintenance)
  * app engine    -> nextgen_app role, NOSUPERUSER NOBYPASSRLS, so PostgreSQL
                     Row Level Security policies are genuinely enforced.
"""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from decimal import Decimal
import sqlite3
import uuid

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings

from datetime import datetime, timedelta
from sqlalchemy.engine import Engine

sqlite3.register_adapter(uuid.UUID, str)
sqlite3.register_adapter(Decimal, float)


def register_sqlite_functions(conn):
    if not isinstance(conn, sqlite3.Connection):
        return

    def _parse_dt(dt_val):
        if not dt_val:
            return None
        if isinstance(dt_val, str):
            dt_val = dt_val.replace("T", " ")
            if "." in dt_val:
                dt_val = dt_val.split(".")[0]
            try:
                return datetime.fromisoformat(dt_val)
            except Exception:
                return None
        return dt_val

    def sqlite_date_trunc(unit, dt_val):
        dt = _parse_dt(dt_val)
        if not dt:
            return dt_val
        u = str(unit).lower()
        if u.startswith("year"):
            return dt.strftime("%Y-01-01 00:00:00")
        elif u.startswith("month"):
            return dt.strftime("%Y-%m-01 00:00:00")
        elif u.startswith("week"):
            start = dt - timedelta(days=dt.weekday())
            return start.strftime("%Y-%m-%d 00:00:00")
        elif u.startswith("day"):
            return dt.strftime("%Y-%m-%d 00:00:00")
        elif u.startswith("hour"):
            return dt.strftime("%Y-%m-%d %H:00:00")
        return dt.strftime("%Y-%m-%d %H:%M:%S")

    def sqlite_timezone(tz_name, dt_val):
        dt = _parse_dt(dt_val)
        if not dt:
            return dt_val
        if "tashkent" in str(tz_name).lower():
            dt = dt + timedelta(hours=5)
        return dt.strftime("%Y-%m-%d %H:%M:%S")

    def sqlite_extract(field, dt_val):
        dt = _parse_dt(dt_val)
        if not dt:
            return 0
        f = str(field).lower().strip("'\"")
        if f == "hour":
            return dt.hour
        elif f == "month":
            return dt.month
        elif f == "year":
            return dt.year
        elif f == "day":
            return dt.day
        elif f in ("dow", "dayofweek"):
            return dt.weekday()
        return 0

    conn.create_function("date_trunc", 2, sqlite_date_trunc)
    conn.create_function("timezone", 2, sqlite_timezone)
    conn.create_function("extract", 2, sqlite_extract)
    conn.create_function("gen_random_uuid", 0, lambda: uuid.uuid4().hex)


@event.listens_for(Engine, "connect")
def _on_engine_connect(dbapi_con, con_record):
    register_sqlite_functions(dbapi_con)


class Base(DeclarativeBase):
    pass


def _engine(url: str, **kw):
    if url.startswith("sqlite"):
        return create_engine(
            url,
            connect_args={"check_same_thread": False},
            echo=settings.DB_ECHO,
            future=True,
            **kw,
        )
    return create_engine(
        url,
        pool_pre_ping=True,
        pool_size=settings.DB_POOL_SIZE,
        max_overflow=settings.DB_MAX_OVERFLOW,
        echo=settings.DB_ECHO,
        future=True,
        **kw,
    )


app_engine = _engine(settings.DATABASE_URL)
admin_engine = _engine(settings.DATABASE_ADMIN_URL)

SessionLocal = sessionmaker(bind=app_engine, expire_on_commit=False, class_=Session)
AdminSessionLocal = sessionmaker(bind=admin_engine, expire_on_commit=False, class_=Session)


def get_db() -> Iterator[Session]:
    """Plain (non-tenant) session, used by auth flows before an org is known."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def admin_session() -> Iterator[Session]:
    db = AdminSessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


# Every transaction opened by a session carrying tenant info re-binds the RLS
# context, so an explicit commit() in the middle of a request can never drop the
# tenant binding (this is what makes SET LOCAL safe under connection pooling).
@event.listens_for(Session, "after_begin")
def _bind_tenant_on_begin(session: Session, transaction, connection) -> None:  # noqa: ARG001
    ctx = session.info.get("tenant")
    if not ctx:
        return
    if connection.dialect.name == "postgresql":
        connection.execute(text("SELECT set_config('app.current_org', :o, true)"),
                           {"o": str(ctx.get("org_id") or "")})
        connection.execute(text("SELECT set_config('app.current_user', :u, true)"),
                           {"u": str(ctx.get("user_id") or "")})


def set_tenant_context(db: Session, *, org_id: str, user_id: str | None = None) -> None:
    """Bind the current transaction to a tenant for RLS (SET LOCAL semantics)."""
    bind = getattr(db, "bind", None) or getattr(db, "get_bind", lambda: None)()
    if bind and hasattr(bind, "dialect") and bind.dialect.name == "postgresql":
        db.execute(text("SELECT set_config('app.current_org', :o, true)"), {"o": str(org_id)})
        db.execute(text("SELECT set_config('app.current_user', :u, true)"), {"u": str(user_id or "")})


def healthcheck() -> tuple[bool, str]:
    try:
        with app_engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True, "ok"
    except Exception as exc:  # pragma: no cover - exercised only when DB is down
        return False, str(exc)[:200]
