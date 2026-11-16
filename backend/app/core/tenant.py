"""Tenant resolution: the single place where "which organization am I acting for?"
is answered. Client input is never trusted for this — the value comes from the
authenticated membership stored in the session.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import set_tenant_context
from app.core.errors import Forbidden, Unauthorized
from app.models import AuthSession, Organization, OrganizationMember, User
from app.models.enums import ROLE_RANK, Role


@dataclass
class Identity:
    """Authenticated principal, before an organization is chosen."""

    user: User
    session: AuthSession | None = None
    memberships: list[OrganizationMember] = field(default_factory=list)
    active_org_id: uuid.UUID | None = None
    role: Role | None = None
    is_bot: bool = False

    def role_in(self, org_id: uuid.UUID) -> Role | None:
        for m in self.memberships:
            if m.organization_id == org_id and m.status == "active":
                return Role(m.role)
        return None


@dataclass
class Tenant:
    """A request scoped to one organization, with the RLS GUC already bound."""

    db: Session
    user: User
    org: Organization
    membership: OrganizationMember
    role: Role
    identity: Identity
    # Only set for bot (service-plane) tenants: the linked Telegram account's own
    # preferences, so the bot can honour the saved language across restarts.
    bot_language: str | None = None
    bot_alerts_enabled: bool | None = None

    @property
    def org_id(self) -> uuid.UUID:
        return self.org.id

    @property
    def user_id(self) -> uuid.UUID:
        return self.user.id

    def require(self, minimum: Role) -> None:
        if ROLE_RANK[self.role] < ROLE_RANK[minimum]:
            raise Forbidden(
                f"Requires role '{minimum.value}' or higher; you have '{self.role.value}'",
                code="insufficient_role",
                details={"required": minimum.value, "actual": self.role.value},
            )

    def can(self, minimum: Role) -> bool:
        return ROLE_RANK[self.role] >= ROLE_RANK[minimum]


def bind(db: Session, *, org_id: uuid.UUID, user_id: uuid.UUID | None) -> None:
    """Attach the tenant to the session; the after_begin hook re-applies it on
    every new transaction so pooled connections can never leak across tenants."""
    db.info["tenant"] = {"org_id": str(org_id), "user_id": str(user_id or "")}
    set_tenant_context(db, org_id=str(org_id), user_id=str(user_id))


def load_identity(admin_db: Session, *, user_id: uuid.UUID, session_id: uuid.UUID | None) -> Identity:
    """Identity plane reads run on the privileged connection because `users` and
    `auth_sessions` are deliberately not granted to the tenant role."""
    user = admin_db.get(User, user_id)
    if user is None or not user.is_active:
        raise Unauthorized("Account not found or inactive", code="account_inactive")

    session = None
    if session_id is not None:
        session = admin_db.get(AuthSession, session_id)
        if session is None or session.user_id != user.id:
            raise Unauthorized("Session not found", code="session_invalid")
        if session.revoked_at is not None:
            raise Unauthorized("Session revoked", code="session_revoked")
        if (session.expires_at if session.expires_at.tzinfo else session.expires_at.replace(tzinfo=UTC)) < datetime.now(UTC):
            raise Unauthorized("Session expired", code="session_expired")

    memberships = list(admin_db.scalars(
        select(OrganizationMember).where(
            OrganizationMember.user_id == user.id,
            OrganizationMember.status == "active",
        )))
    return Identity(user=user, session=session, memberships=memberships)


def resolve_active_membership(identity: Identity, org_id: uuid.UUID | None) -> OrganizationMember:
    if not identity.memberships:
        raise Forbidden("You are not a member of any organization", code="no_membership")
    if org_id is None:
        return identity.memberships[0]
    for m in identity.memberships:
        if m.organization_id == org_id:
            return m
    # An authenticated user asking for an org they do not belong to: never a 500,
    # never partial data. Persisted as CROSS_ORG_DENIED for the security review.
    from app.models.enums import AuditAction
    from app.services import audit

    audit.record(AuditAction.CROSS_ORG_DENIED, user_id=identity.user.id,
                 target_type="organization", target_id=str(org_id),
                 meta={"context": "request", "claim_org": str(identity.active_org_id)})
    raise Forbidden("You do not have access to this organization", code="cross_org_denied",
                    details={"organization_id": str(org_id)})
