"""Registration, login, refresh rotation, password reset and org switching.

Identity-plane writes use the privileged (admin) session because `users`,
`auth_sessions` and `password_reset_tokens` are intentionally outside the tenant
role's grants. Organization creation during registration is the one tenant write
performed on that path, and its organization_id is server-generated — never taken
from the client.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import AdminSessionLocal
from app.core.errors import Conflict, NotFound, Unauthorized, ValidationFailed
from app.core.logging import log
from app.core.security import (create_access_token, hash_opaque_token, hash_password,
                               needs_rehash, new_opaque_token, verify_password)
from app.models import (AuthSession, Organization, OrganizationMember, PasswordResetToken, User)
from app.models.enums import AuditAction, Language, Role
from app.services import audit

MAX_FAILED_LOGINS = 8
LOCKOUT_MINUTES = 15


def _slugify(name: str) -> str:
    base = "".join(c if c.isalnum() else "-" for c in name.lower()).strip("-")
    base = "-".join(filter(None, base.split("-")))[:60] or "org"
    return base


def _unique_slug(db: Session, name: str) -> str:
    base = _slugify(name)
    slug, n = base, 1
    while db.scalar(select(func.count()).select_from(Organization).where(Organization.slug == slug)):
        n += 1
        slug = f"{base}-{n}"
    return slug


def find_user_by_email(db: Session, email: str) -> User | None:
    return db.scalar(select(User).where(func.lower(User.email) == email.strip().lower()))


def _new_session(db: Session, user: User, org_id: uuid.UUID | None, *, request_meta: dict) -> tuple[AuthSession, str]:
    refresh_plain = new_opaque_token(48)
    sess = AuthSession(
        user_id=user.id,
        org_id=org_id,
        refresh_token_hash=hash_opaque_token(refresh_plain),
        expires_at=datetime.now(UTC) + timedelta(days=settings.REFRESH_TOKEN_TTL_DAYS),
        user_agent=(request_meta.get("user_agent") or "")[:400] or None,
        ip_address=request_meta.get("ip"),
        created_at=datetime.now(UTC),
    )
    db.add(sess)
    db.flush()
    return sess, refresh_plain


def _issue(user: User, sess: AuthSession, org_id: uuid.UUID | None, role: str) -> dict:
    access = create_access_token(user_id=str(user.id), org_id=str(org_id) if org_id else None,
                                 role=role, sid=str(sess.id))
    return {"access_token": access, "token_type": "bearer",
            "expires_in": settings.ACCESS_TOKEN_TTL_MIN * 60}


def register(payload, *, request_meta: dict) -> dict:
    with AdminSessionLocal() as db:
        email = payload.email.strip().lower()
        if find_user_by_email(db, email):
            audit.record(AuditAction.REGISTER, ip=request_meta.get("ip"),
                         user_agent=request_meta.get("user_agent"),
                         meta={"email": email, "result": "duplicate"})
            raise Conflict("An account with this email already exists", code="email_taken")

        user = User(email=email, password_hash=hash_password(payload.password),
                    full_name=payload.full_name.strip(), locale=payload.locale.value,
                    email_verified=False)
        db.add(user)
        db.flush()

        org = None
        role = None
        if payload.invite_token:
            digest = hash_opaque_token(payload.invite_token)
            pending = db.scalar(select(OrganizationMember).where(
                OrganizationMember.invite_token_hash == digest,
                OrganizationMember.status == "invited"))
            if pending is None:
                raise ValidationFailed("Invitation is invalid or has already been used",
                                       code="invite_invalid")
            if (pending.invited_email or "").lower() != email:
                # A leaked invitation link must not let a third party join.
                raise ValidationFailed("This invitation was issued for a different address",
                                       code="invite_email_mismatch")
            pending.user_id = user.id
            pending.status = "active"
            pending.accepted_at = datetime.now(UTC)
            pending.invite_token_hash = None
            org = db.get(Organization, pending.organization_id)
            role = pending.role
        elif payload.organization_name:
            org = Organization(name=payload.organization_name.strip(),
                               slug=_unique_slug(db, payload.organization_name),
                               created_by=user.id, timezone=settings.DISPLAY_TZ,
                               currency=settings.DEFAULT_CURRENCY)
            db.add(org)
            db.flush()
            membership = OrganizationMember(organization_id=org.id, user_id=user.id,
                                            role=Role.OWNER.value, status="active",
                                            accepted_at=datetime.now(UTC),
                                            invited_email=email)
            db.add(membership)
            role = Role.OWNER.value

        sess, refresh_plain = _new_session(db, user, org.id if org else None, request_meta=request_meta)
        db.commit()

        memberships = list(db.scalars(select(OrganizationMember).where(
            OrganizationMember.user_id == user.id)))
        audit.record(AuditAction.REGISTER, org_id=org.id if org else None, user_id=user.id,
                     ip=request_meta.get("ip"), user_agent=request_meta.get("user_agent"),
                     meta={"email": email})
        token = _issue(user, sess, org.id if org else None, role or Role.VIEWER.value)
        token["refresh_token"] = refresh_plain
        return {"user": user, "memberships": memberships, "org": org, "role": role, "token": token}


def login(email: str, password: str, *, org_id: uuid.UUID | None, request_meta: dict) -> dict:
    with AdminSessionLocal() as db:
        user = find_user_by_email(db, email)
        now = datetime.now(UTC)
        if user is None:
            # Constant-ish work regardless of user existence (no user enumeration).
            verify_password(password, "$argon2id$v=19$m=19456,t=2,p=1$c29tZXNhbHR2YWx1ZQ$" + "0" * 43)
            audit.record(AuditAction.LOGIN_FAILED, ip=request_meta.get("ip"),
                         user_agent=request_meta.get("user_agent"),
                         meta={"email": email.strip().lower(), "reason": "no_such_user"})
            raise Unauthorized("Invalid email or password", code="invalid_credentials")

        if user.locked_until and _as_utc(user.locked_until) > now:
            raise Unauthorized("Account temporarily locked after repeated failed logins",
                               code="account_locked")

        if not user.is_active:
            raise Unauthorized("Account is disabled", code="account_inactive")

        if not verify_password(password, user.password_hash):
            user.failed_login_count += 1
            if user.failed_login_count >= MAX_FAILED_LOGINS:
                user.locked_until = now + timedelta(minutes=LOCKOUT_MINUTES)
                user.failed_login_count = 0
                log.warning("account locked", extra={"user_id": str(user.id)})
            db.commit()
            audit.record(AuditAction.LOGIN_FAILED, user_id=user.id, ip=request_meta.get("ip"),
                         user_agent=request_meta.get("user_agent"),
                         meta={"reason": "bad_password"})
            raise Unauthorized("Invalid email or password", code="invalid_credentials")

        if needs_rehash(user.password_hash):
            user.password_hash = hash_password(password)

        memberships = list(db.scalars(select(OrganizationMember).where(
            OrganizationMember.user_id == user.id, OrganizationMember.status == "active")))
        if not memberships:
            raise Unauthorized("No active organization membership", code="no_membership")

        chosen = memberships[0]
        if org_id is not None:
            match = [m for m in memberships if m.organization_id == org_id]
            if not match:
                audit.record(AuditAction.CROSS_ORG_DENIED, user_id=user.id,
                             ip=request_meta.get("ip"), target_type="organization",
                             target_id=str(org_id), meta={"context": "login"})
                raise Unauthorized("You do not have access to this organization",
                                   code="cross_org_denied")
            chosen = match[0]

        user.failed_login_count = 0
        user.locked_until = None
        user.last_login_at = now
        sess, refresh_plain = _new_session(db, user, chosen.organization_id, request_meta=request_meta)
        db.commit()

        org = db.get(Organization, chosen.organization_id)
        audit.record(AuditAction.LOGIN, org_id=chosen.organization_id, user_id=user.id,
                     ip=request_meta.get("ip"), user_agent=request_meta.get("user_agent"))
        token = _issue(user, sess, chosen.organization_id, chosen.role)
        token["refresh_token"] = refresh_plain
        return {"user": user, "memberships": memberships, "org": org, "role": chosen.role,
                "token": token}


def _as_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def refresh(refresh_plain: str, *, request_meta: dict) -> dict:
    if not refresh_plain:
        raise Unauthorized("Refresh token required", code="refresh_required")
    digest = hash_opaque_token(refresh_plain)
    with AdminSessionLocal() as db:
        sess = db.scalar(select(AuthSession).where(AuthSession.refresh_token_hash == digest))
        now = datetime.now(UTC)
        if sess is None or sess.revoked_at is not None or _as_utc(sess.expires_at) < now:
            raise Unauthorized("Refresh token is invalid or expired", code="refresh_invalid")
        user = db.get(User, sess.user_id)
        if user is None or not user.is_active:
            raise Unauthorized("Account unavailable", code="account_inactive")

        # rotation: the old token is burned, a new one is issued
        sess.revoked_at = now
        new_sess, new_plain = _new_session(db, user, sess.org_id, request_meta=request_meta)
        new_sess.rotated_from = sess.id
        db.commit()

        role = Role.VIEWER.value
        if sess.org_id:
            m = db.scalar(select(OrganizationMember).where(
                OrganizationMember.organization_id == sess.org_id,
                OrganizationMember.user_id == user.id,
                OrganizationMember.status == "active"))
            if m:
                role = m.role
        token = _issue(user, new_sess, sess.org_id, role)
        token["refresh_token"] = new_plain
        return {"token": token, "user": user}


def logout(session_id: uuid.UUID | None, *, user_id: uuid.UUID | None, request_meta: dict) -> None:
    if session_id is None:
        return
    with AdminSessionLocal() as db:
        sess = db.get(AuthSession, session_id)
        if sess and sess.revoked_at is None:
            sess.revoked_at = datetime.now(UTC)
            db.commit()
            audit.record(AuditAction.LOGOUT, org_id=sess.org_id, user_id=user_id,
                         ip=request_meta.get("ip"))


def switch_org(user_id: uuid.UUID, org_id: uuid.UUID, *, session_id: uuid.UUID | None,
               request_meta: dict) -> dict:
    with AdminSessionLocal() as db:
        m = db.scalar(select(OrganizationMember).where(
            OrganizationMember.organization_id == org_id,
            OrganizationMember.user_id == user_id,
            OrganizationMember.status == "active"))
        user = db.get(User, user_id)
        if m is None or user is None:
            audit.record(AuditAction.CROSS_ORG_DENIED, user_id=user_id, target_type="organization",
                         target_id=str(org_id), ip=request_meta.get("ip"),
                         meta={"context": "switch_org"})
            raise Unauthorized("You do not have access to this organization",
                               code="cross_org_denied")
        sess = db.get(AuthSession, session_id) if session_id else None
        if sess is None:
            raise Unauthorized("Session not found", code="session_invalid")
        sess.org_id = org_id
        db.commit()
        token = _issue(user, sess, org_id, m.role)
        return {"token": token, "org_id": org_id, "role": m.role}


def request_password_reset(email: str, *, request_meta: dict) -> tuple[str | None, str]:
    """Always returns the same user-facing message (no account enumeration)."""
    msg = "If an account exists for this address, a reset link has been issued."
    with AdminSessionLocal() as db:
        user = find_user_by_email(db, email)
        if user is None or not user.is_active:
            audit.record(AuditAction.LOGIN_FAILED, ip=request_meta.get("ip"),
                         meta={"email": email.lower(), "reason": "reset_unknown_email"})
            return None, msg
        plain = new_opaque_token(32)
        db.add(PasswordResetToken(
            user_id=user.id, token_hash=hash_opaque_token(plain),
            expires_at=datetime.now(UTC) + timedelta(minutes=30), created_at=datetime.now(UTC)))
        db.commit()
        # No SMTP in this build: the token is returned only when EXPOSE_DEV_TOKENS
        # is enabled, and that flag is refused in production by validate_runtime().
        return (plain if settings.EXPOSE_DEV_TOKENS else None), msg


def reset_password(token: str, new_password: str, *, request_meta: dict) -> None:
    digest = hash_opaque_token(token)
    with AdminSessionLocal() as db:
        row = db.scalar(select(PasswordResetToken).where(PasswordResetToken.token_hash == digest))
        now = datetime.now(UTC)
        if row is None or row.used_at is not None or _as_utc(row.expires_at) < now:
            raise ValidationFailed("Reset token is invalid or expired", code="reset_invalid")
        user = db.get(User, row.user_id)
        if user is None:
            raise NotFound("Account not found")
        user.password_hash = hash_password(new_password)
        user.failed_login_count = 0
        user.locked_until = None
        row.used_at = now
        # every existing session dies when the password changes
        for sess in db.scalars(select(AuthSession).where(
                AuthSession.user_id == user.id, AuthSession.revoked_at.is_(None))):
            sess.revoked_at = now
        db.commit()


def change_password(user_id: uuid.UUID, current: str, new: str) -> None:
    with AdminSessionLocal() as db:
        user = db.get(User, user_id)
        if user is None:
            raise NotFound("Account not found")
        if not verify_password(current, user.password_hash):
            raise Unauthorized("Current password is incorrect", code="invalid_credentials")
        if current == new:
            raise ValidationFailed("New password must differ from the current one",
                                   code="password_reused")
        user.password_hash = hash_password(new)
        db.commit()
