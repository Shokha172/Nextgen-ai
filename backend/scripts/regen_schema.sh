#!/usr/bin/env bash
# Regenerate the initial migration from the models (development helper).
# DESTRUCTIVE: drops the public schema. Never run against production.
set -euo pipefail
cd "$(dirname "$0")/.."
PGURL="${DATABASE_ADMIN_URL:-postgresql://postgres:postgres@127.0.0.1:5433/nextgen}"
TEST_URL="${TEST_DATABASE_ADMIN_URL:-postgresql://postgres:postgres@127.0.0.1:5433/nextgen_test}"
for url in "$PGURL" "$TEST_URL"; do
  psql "$url" -q -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public; GRANT USAGE ON SCHEMA public TO nextgen_app;"
done
rm -f alembic/versions/*.py
python3 -m alembic revision --autogenerate -m "initial schema" >/dev/null
MIG=$(ls alembic/versions/*.py | head -1)
python3 - "$MIG" <<'PY'
import sys, re, pathlib
p = pathlib.Path(sys.argv[1]); s = p.read_text()
s = s.replace("from alembic import op\nimport sqlalchemy as sa",
              "from alembic import op\nimport sqlalchemy as sa\n\nfrom app.core.rls import apply_security, revert_security")
s = re.sub(r"(def upgrade\(\) -> None:\n(?:.*\n)*?)(\n\ndef downgrade\(\) -> None:)",
           lambda m: m.group(1).rstrip("\n") + "\n\n    # --- multi-tenant security: RLS policies, grants, least-privilege boundary ---\n    apply_security(op.get_bind())\n" + m.group(2), s, count=1)
s = s.replace("def downgrade() -> None:\n", "def downgrade() -> None:\n    revert_security(op.get_bind())\n", 1)
p.write_text(s)
print(f"patched {p}")
PY
python3 scripts/bootstrap_db.py
ALEMBIC_DATABASE_URL="$TEST_URL" python3 -m alembic upgrade head >/dev/null && echo "[regen] test database migrated"
