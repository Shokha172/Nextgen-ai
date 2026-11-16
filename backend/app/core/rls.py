"""Row Level Security definitions, kept in one place.

Executed by the Alembic migration that introduces/refreshes tenant tables, so a
plain `alembic upgrade head` always lands a fully isolated database. Also used by
tests to assert that isolation is real rather than nominal.

Why this works even if application code is buggy:
  * the API connects as `nextgen_app` -> NOSUPERUSER, NOBYPASSRLS, not the owner;
  * FORCE ROW LEVEL SECURITY applies policies even to the table owner;
  * the policy predicate dereferences a transaction-local GUC that the request
    layer sets from the *authenticated* membership, never from client input;
  * with no GUC the predicate is NULL -> zero rows (fail closed).
"""
from __future__ import annotations

TENANT_TABLES: tuple[str, ...] = (
    "organization_members", "meters", "meter_readings", "tariffs", "import_jobs",
    "anomalies", "forecasts", "ai_insights", "savings_reports", "reports",
    "notifications", "audit_logs", "telegram_accounts", "telegram_link_codes",
    "import_staging_rows",
)

ORG_PREDICATE = "organization_id = NULLIF(current_setting('app.current_org', true), '')::uuid"

_RLS_TEMPLATE = """
ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;
ALTER TABLE {table} FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON {table};
CREATE POLICY tenant_isolation ON {table}
    USING ({pred})
    WITH CHECK ({pred});
"""

_ORG_SQL = """
ALTER TABLE organizations ENABLE ROW LEVEL SECURITY;
ALTER TABLE organizations FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON organizations;
CREATE POLICY tenant_isolation ON organizations
    USING (id = NULLIF(current_setting('app.current_org', true), '')::uuid)
    WITH CHECK (id = NULLIF(current_setting('app.current_org', true), '')::uuid);
"""

_GRANTS_SQL = """
GRANT USAGE ON SCHEMA public TO nextgen_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON
    organizations, organization_members, meters, meter_readings, tariffs, import_jobs,
    anomalies, forecasts, ai_insights, savings_reports, reports, notifications,
    audit_logs, telegram_accounts, telegram_link_codes, import_staging_rows
TO nextgen_app;
-- The identity plane (users, auth_sessions, password_reset_tokens) is deliberately
-- NOT granted to nextgen_app: those flows use the privileged admin path.
"""


def statements() -> list[str]:
    out = [_ORG_SQL]
    for t in TENANT_TABLES:
        out.append(_RLS_TEMPLATE.format(table=t, pred=ORG_PREDICATE))
        out.append(f"CREATE INDEX IF NOT EXISTS ix_{t}_org_rls ON {t} (organization_id);")
    out.append(_GRANTS_SQL)
    clean: list[str] = []
    for block in out:
        clean.extend(s.strip() for s in block.split(";") if s.strip() and not s.strip().startswith("--"))
    return clean


def apply_security(bind) -> None:
    """Idempotently apply policies + grants using a sync SQLAlchemy connection."""
    for stmt in statements():
        bind.exec_driver_sql(stmt)


def revert_security(bind) -> None:
    bind.exec_driver_sql("REVOKE ALL ON ALL TABLES IN SCHEMA public FROM nextgen_app")
    for t in ("organizations", *TENANT_TABLES):
        bind.exec_driver_sql(f"DROP POLICY IF EXISTS tenant_isolation ON {t}")
        bind.exec_driver_sql(f"ALTER TABLE {t} DISABLE ROW LEVEL SECURITY")
