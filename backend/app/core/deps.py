"""FastAPI dependencies: authentication, tenant binding, RBAC, rate limiting.

Token sources, in priority order:
  1. `Authorization: Bearer <jwt>`  — API clients, tests, bots-with-user-tokens
  2. httpOnly cookie `ng_access`    — the Next.js server forwarding the browser session
The active organization comes from the JWT claim and is re-validated against the
database on every request; it is never read from a query string or body.
"""
from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, Header, Request
from sqlalchemy.orm import Session

from app.core import rate_limit
from app.core.config import settings
from app.core.db import AdminSessionLocal, SessionLocal, get_db
from app.core.errors import Forbidden, RateLimited, Unauthorized
from app.core.security import constant_time_eq, decode_access_token
from app.core.tenant import Identity, Tenant, bind, load_identity, resolve_active_membership
from app.models import Organization
from app.models.enums import Role

ACCESS_COOKIE = "ng_access"
REFRESH_COOKIE = "ng_refresh"


def client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def limit_dependency(key_prefix: str, limit: int | None = None) -> Callable:
    def _dep(request: Request) -> None:
        rate_limit.hit(f"{key_prefix}:{client_ip(request)}", limit=limit)
    return _dep


TenantRateLimit = Annotated[None, Depends(limit_dependency("api"))]
LoginRateLimit = Annotated[None, Depends(limit_dependency("login", settings.LOGIN_RATE_LIMIT_PER_MINUTE))]


def _raw_token(request: Request) -> str | None:
    auth = request.headers.get("authorization")
    if auth and auth.lower().startswith("bearer "):
        return auth.split(" ", 1)[1].strip()
    return request.cookies.get(ACCESS_COOKIE)


def get_identity(request: Request, db: Session = Depends(get_db)) -> Identity:
    token = _raw_token(request)
    if not token:
        raise Unauthorized("Not authenticated", code="not_authenticated")
    payload = decode_access_token(token)
    sid_raw = payload.get("sid")
    admin = AdminSessionLocal()
    try:
        identity = load_identity(
            admin,
            user_id=uuid.UUID(payload["sub"]),
            session_id=uuid.UUID(sid_raw) if sid_raw else None,
        )
    finally:
        admin.close()
    org_claim = payload.get("org")
    identity.active_org_id = uuid.UUID(org_claim) if org_claim else None
    identity.role = Role(payload["role"]) if payload.get("role") else None
    return identity


def get_tenant(identity: Identity = Depends(get_identity), db: Session = Depends(get_db)) -> Tenant:
    membership = resolve_active_membership(identity, identity.active_org_id)
    bind(db, org_id=membership.organization_id, user_id=identity.user.id)
    org = db.get(Organization, membership.organization_id)
    if org is None:  # org deleted or RLS mismatch
        raise Forbidden("Organization not available", code="org_unavailable")
    if not org.is_active:
        raise Forbidden("Organization is inactive", code="org_inactive")
    if org.is_demo and settings.is_prod:
        raise Forbidden("Demo organizations are not available in production",
                        code="demo_isolated")
    return Tenant(db=db, user=identity.user, org=org, membership=membership,
                  role=Role(membership.role), identity=identity)


def require_role(minimum: Role) -> Callable[..., Tenant]:
    def _dep(tenant: Tenant = Depends(get_tenant)) -> Tenant:
        tenant.require(minimum)
        return tenant
    return _dep


TenantViewer = Annotated[Tenant, Depends(require_role(Role.VIEWER))]
TenantAnalyst = Annotated[Tenant, Depends(require_role(Role.ANALYST))]
TenantAdmin = Annotated[Tenant, Depends(require_role(Role.ADMIN))]
TenantOwner = Annotated[Tenant, Depends(require_role(Role.OWNER))]
CurrentIdentity = Annotated[Identity, Depends(get_identity)]
PlainDb = Annotated[Session, Depends(get_db)]


def verify_bot_service_key(
    x_bot_service_key: str | None = Header(default=None),
    x_bot_mode: str | None = Header(default=None),
) -> str:
    """Bot -> API authentication. Two independent keys so the demo bot can never
    authenticate as the official bot (and therefore can never reach a real org)."""
    if not x_bot_service_key or not x_bot_mode:
        raise Unauthorized("Bot service credentials required", code="bot_auth_required")
    mode = x_bot_mode.strip().lower()
    expected = {"demo": settings.BOT_SERVICE_KEY_DEMO,
                "official": settings.BOT_SERVICE_KEY_OFFICIAL}.get(mode)
    if not expected:
        raise Unauthorized("Unknown bot mode", code="bot_auth_required")
    if not constant_time_eq(x_bot_service_key, expected):
        raise Unauthorized("Invalid bot service key", code="bot_auth_required")
    return mode


BotMode = Annotated[str, Depends(verify_bot_service_key)]


def paginate(total: int, page: int, page_size: int) -> dict:
    return {"total": total, "page": page, "page_size": page_size,
            "has_next": page * page_size < total}
