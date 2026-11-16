"""Telegram linking and bot-facing session resolution.

Identity rules:
  * a web-authenticated user creates a **short-lived, single-use, hashed** code;
  * the bot exchanges that code for a linked row — a Telegram username alone is
    never sufficient (usernames are mutable and unverified);
  * demo and production are separated by *both* the service key presented by the
    bot and the `is_demo` flag of the organization, so a demo credential can never
    resolve a real enterprise;
  * the bot never sends an organization id: the tenant is derived server-side from
    the linked account.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.config import settings
from app.core.errors import Conflict, Forbidden, NotFound, Unauthorized, ValidationFailed
from app.core.security import hash_opaque_token, new_link_code
from app.models import Organization, OrganizationMember, TelegramAccount, TelegramLinkCode, User
from app.models.enums import AuditAction, Role
from app.services import audit


def create_link_code(db, *, org_id: uuid.UUID, user_id: uuid.UUID, is_demo: bool) -> dict:
    code = new_link_code()
    row = TelegramLinkCode(
        organization_id=org_id, user_id=user_id,
        code_hash=hash_opaque_token(code), is_demo=is_demo,
        expires_at=datetime.now(UTC) + timedelta(minutes=settings.TELEGRAM_LINK_CODE_TTL_MIN),
        created_at=datetime.now(UTC))
    db.add(row)
    db.commit()
    bot = "demo" if is_demo else "official"
    bot_username = (settings.PUBLIC_WEB_URL or "").rstrip("/")
    return {"code": code, "expires_in_minutes": settings.TELEGRAM_LINK_CODE_TTL_MIN,
            "bot_mode": bot, "deep_link": f"https://t.me/your_bot?start={code}",
            "instructions": {
                "uz": f"Telegram botni oching va /start {code} buyrug'ini yuboring.",
                "ru": f"Откройте Telegram-бот и отправьте команду /start {code}.",
                "en": f"Open the Telegram bot and send /start {code}.",
            },
            "note": "The code is single-use and expires; it is stored only as a hash."}


def link_bot_account(admin_db, *, code: str, telegram_user_id: int, telegram_username: str | None,
                     mode: str) -> dict:
    digest = hash_opaque_token(code.strip().upper())
    row = admin_db.scalar(select(TelegramLinkCode).where(
        TelegramLinkCode.code_hash == digest))
    if row is None:
        raise ValidationFailed("This linking code is invalid or has expired",
                               code="link_code_invalid")
    now = datetime.now(UTC)
    exp = row.expires_at if row.expires_at.tzinfo else row.expires_at.replace(tzinfo=UTC)
    if row.used_at is not None or exp < now:
        raise ValidationFailed("This linking code is invalid or has expired",
                               code="link_code_invalid")
    if bool(row.is_demo) != (mode == "demo"):
        # a demo credential can never unlock a production organization
        raise Forbidden("This code belongs to a different bot environment",
                        code="link_environment_mismatch")

    existing = admin_db.scalar(select(TelegramAccount).where(
        TelegramAccount.telegram_user_id == telegram_user_id,
        TelegramAccount.is_demo == row.is_demo))
    if existing is not None:
        if existing.organization_id != row.organization_id:
            raise Conflict("This Telegram account is already linked to another organization",
                           code="telegram_already_linked")
        existing.is_active = True
        existing.revoked_at = None
        existing.telegram_username = telegram_username
        existing.last_seen_at = now
        account = existing
    else:
        account = TelegramAccount(
            organization_id=row.organization_id, user_id=row.user_id,
            telegram_user_id=telegram_user_id, telegram_username=telegram_username,
            is_demo=row.is_demo, language="uz", is_active=True)
        admin_db.add(account)
    row.used_at = now
    try:
        admin_db.commit()
    except IntegrityError:
        admin_db.rollback()
        account = admin_db.scalar(select(TelegramAccount).where(
            TelegramAccount.telegram_user_id == telegram_user_id,
            TelegramAccount.is_demo == row.is_demo))
    admin_db.refresh(account)

    org = admin_db.get(Organization, account.organization_id)
    member = admin_db.scalar(select(OrganizationMember).where(
        OrganizationMember.organization_id == account.organization_id,
        OrganizationMember.user_id == account.user_id))
    audit.record(AuditAction.TELEGRAM_LINK, org_id=account.organization_id,
                 user_id=account.user_id, actor_type="bot",
                 target_type="telegram_account", target_id=str(account.id),
                 meta={"mode": mode, "telegram_user_id": telegram_user_id})
    return {"account_id": account.id, "organization_id": account.organization_id,
            "organization_name": org.name if org else "",
            "is_demo": account.is_demo, "role": member.role if member else None,
            "language": account.language}


def ensure_demo_session(admin_db, *, telegram_user_id: int,
                        telegram_username: str | None) -> dict:
    """The demo bot is open to the public by design — but only ever to the DEMO org."""
    account = admin_db.scalar(select(TelegramAccount).where(
        TelegramAccount.telegram_user_id == telegram_user_id,
        TelegramAccount.is_demo.is_(True)))
    demo_org = admin_db.scalar(select(Organization).where(Organization.is_demo.is_(True),
                                                         Organization.is_active.is_(True))
                               .order_by(Organization.created_at))
    if demo_org is None:
        raise NotFound("The demo organization has not been seeded on this environment",
                       code="demo_not_seeded")
    # The demo session acts as a member of the demo organization; prefer the owner,
    # otherwise any active member. A demo org without any member is a seeding error.
    member = admin_db.scalar(select(OrganizationMember).where(
        OrganizationMember.organization_id == demo_org.id,
        OrganizationMember.status == "active",
        OrganizationMember.user_id.is_not(None),
    ).order_by(OrganizationMember.role.desc()))
    if member is None or member.user_id is None:
        raise NotFound("The demo organization has no member to act as; re-run the seed script",
                       code="demo_not_seeded")
    if account is None:
        account = TelegramAccount(
            organization_id=demo_org.id, user_id=member.user_id,
            telegram_user_id=telegram_user_id, telegram_username=telegram_username,
            is_demo=True, language="uz", is_active=True)
        admin_db.add(account)
        try:
            admin_db.commit()
        except IntegrityError:
            admin_db.rollback()
            account = admin_db.scalar(select(TelegramAccount).where(
                TelegramAccount.telegram_user_id == telegram_user_id,
                TelegramAccount.is_demo.is_(True)))
    else:
        account.last_seen_at = datetime.now(UTC)
        account.is_active = True
        admin_db.commit()
    admin_db.refresh(account)
    return {"account_id": account.id, "organization_id": account.organization_id,
            "organization_name": demo_org.name, "is_demo": True,
            "role": Role.VIEWER.value, "language": account.language}


def find_account(admin_db, *, telegram_user_id: int, mode: str):
    account = admin_db.scalar(select(TelegramAccount).where(
        TelegramAccount.telegram_user_id == telegram_user_id,
        TelegramAccount.is_demo == (mode == "demo"),
        TelegramAccount.is_active.is_(True),
        TelegramAccount.revoked_at.is_(None)))
    if account is None:
        raise Unauthorized("This Telegram account is not linked. Generate a linking code in "
                           "the NEXTGEN AI web platform.", code="not_linked")
    if mode == "demo" and not account.is_demo:
        raise Forbidden("Demo credentials cannot access production accounts",
                        code="environment_mismatch")
    if mode == "official" and account.is_demo:
        raise Forbidden("Official credentials cannot access demo accounts",
                        code="environment_mismatch")
    return account


def unlink(admin_db, *, account_id: uuid.UUID, user_id: uuid.UUID | None = None,
           org_id: uuid.UUID | None = None) -> None:
    account = admin_db.get(TelegramAccount, account_id)
    if account is None:
        raise NotFound("Telegram account not found")
    if org_id is not None and account.organization_id != org_id:
        raise NotFound("Telegram account not found")
    account.is_active = False
    account.revoked_at = datetime.now(UTC)
    admin_db.commit()
    audit.record(AuditAction.TELEGRAM_UNLINK, org_id=account.organization_id,
                 user_id=user_id, actor_type="user", target_type="telegram_account",
                 target_id=str(account_id))


def set_language(admin_db, *, telegram_user_id: int, mode: str, language: str) -> None:
    if language not in ("uz", "ru", "en"):
        raise ValidationFailed("Unsupported language", code="invalid_language")
    account = find_account(admin_db, telegram_user_id=telegram_user_id, mode=mode)
    account.language = language
    admin_db.commit()


def toggle_alerts(admin_db, *, telegram_user_id: int, mode: str) -> bool:
    account = find_account(admin_db, telegram_user_id=telegram_user_id, mode=mode)
    account.alerts_enabled = not account.alerts_enabled
    admin_db.commit()
    return account.alerts_enabled
