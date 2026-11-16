"""Append-only audit trail. Written on a privileged connection so that security
events (failed logins, cross-org attempts) are recorded even when the tenant
transaction is rolled back."""
from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.core.db import AdminSessionLocal
from app.models import AuditLog
from app.models.enums import AuditAction


def record(
    action: AuditAction | str,
    *,
    org_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
    actor_type: str = "user",
    target_type: str | None = None,
    target_id: str | None = None,
    ip: str | None = None,
    user_agent: str | None = None,
    meta: dict | None = None,
    _db: Session | None = None,
) -> None:
    row = AuditLog(
        organization_id=org_id,
        actor_user_id=user_id,
        actor_type=actor_type,
        action=action.value if hasattr(action, "value") else str(action),
        target_type=target_type,
        target_id=str(target_id) if target_id is not None else None,
        ip_address=ip,
        user_agent=(user_agent or "")[:400] or None,
        meta=meta or {},
    )
    if _db is not None:
        _db.add(row)
        return
    s = AdminSessionLocal()
    try:
        s.add(row)
        s.commit()
    except Exception:  # auditing must never break the request path
        s.rollback()
    finally:
        s.close()
