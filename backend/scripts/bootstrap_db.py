#!/usr/bin/env python3
"""Idempotent database bootstrap: create the low-privilege app role, then migrate.

Usage:  python scripts/bootstrap_db.py [--reset]
Requires DATABASE_ADMIN_URL to point at a role that may create roles/DDL.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys

from sqlalchemy import create_engine, text

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.core.config import settings  # noqa: E402

APP_ROLE = "nextgen_app"
APP_PW = os.getenv("NEXTGEN_APP_DB_PASSWORD", "nextgen_app_pw")


def ensure_role() -> None:
    engine = create_engine(settings.DATABASE_ADMIN_URL, isolation_level="AUTOCOMMIT")
    with engine.connect() as conn:
        exists = conn.execute(text("SELECT 1 FROM pg_roles WHERE rolname = :r"), {"r": APP_ROLE}).scalar()
        if not exists:
            conn.execute(text(
                f"CREATE ROLE {APP_ROLE} LOGIN PASSWORD '{APP_PW}' "
                "NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOINHERIT"))
            print(f"[bootstrap] role {APP_ROLE} created")
        else:
            conn.execute(text(f"ALTER ROLE {APP_ROLE} WITH LOGIN PASSWORD '{APP_PW}' "
                              "NOSUPERUSER NOBYPASSRLS"))
            print(f"[bootstrap] role {APP_ROLE} verified (NOSUPERUSER, NOBYPASSRLS)")
    engine.dispose()


def run_migrations(reset: bool = False) -> None:
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env = {**os.environ, "ALEMBIC_DATABASE_URL": settings.DATABASE_ADMIN_URL}
    if reset:
        print("[bootstrap] downgrade base (destructive)")
        subprocess.run([sys.executable, "-m", "alembic", "downgrade", "base"], cwd=root, env=env, check=False)
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=root, env=env, check=True)
    print("[bootstrap] migrations applied")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--reset", action="store_true", help="drop all schema objects first")
    a = ap.parse_args()
    ensure_role()
    run_migrations(reset=a.reset)
