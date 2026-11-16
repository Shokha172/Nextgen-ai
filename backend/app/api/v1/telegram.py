"""Telegram endpoints.

Two planes:
  * **web plane** (`/telegram/link`, `/telegram/accounts`) — authenticated by the
    user's session; issues/revokes linking codes.
  * **service plane** (`/telegram/service/*`) — authenticated by the bot's service
    key. The bot never passes an organization id; the tenant is resolved from the
    linked Telegram account. Demo and official keys are separate and are checked
    against `is_demo` on both sides.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, File, Form, Header, Query, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.core import rate_limit
from app.core.db import AdminSessionLocal
from app.core.deps import BotMode, TenantAdmin, TenantViewer
from app.core.errors import Forbidden, NotFound, RateLimited, Unauthorized
from app.core.tenant import Tenant, bind
from app.models import Organization, OrganizationMember, TelegramAccount, User
from app.models.enums import Role
from app.schemas.common import Message
from app.services import (ai, anomalies as anomaly_service, dashboard, exports, forecast,
                          importer, notifications, telegram_service)
from app.services import audit
from app.models.enums import AuditAction

router = APIRouter(tags=["telegram"])


# ------------------------------------------------------------------ web plane
@router.post("/telegram/link", summary="Create a single-use linking code for the bots")
def create_link(tenant: TenantAdmin):
    result = telegram_service.create_link_code(tenant.db, org_id=tenant.org_id,
                                               user_id=tenant.user_id,
                                               is_demo=tenant.org.is_demo)
    return {**result, "organization": tenant.org.name, "is_demo": tenant.org.is_demo}


@router.get("/telegram/accounts", summary="Telegram accounts linked to this organization")
def list_accounts(tenant: TenantViewer):
    rows = tenant.db.scalars(select(TelegramAccount).where(
        TelegramAccount.organization_id == tenant.org_id,
        TelegramAccount.is_active.is_(True)))
    return {"items": [{"id": a.id, "telegram_user_id": a.telegram_user_id,
                       "telegram_username": a.telegram_username, "language": a.language,
                       "is_demo": a.is_demo, "alerts_enabled": a.alerts_enabled,
                       "created_at": a.created_at} for a in rows]}


@router.delete("/telegram/accounts/{account_id}", response_model=Message,
               summary="Revoke a linked Telegram account")
def revoke_account(account_id: uuid.UUID, tenant: TenantAdmin):
    with AdminSessionLocal() as admin:
        telegram_service.unlink(admin, account_id=account_id, user_id=tenant.user_id,
                                org_id=tenant.org_id)
    return {"message": "Telegram account unlinked"}


@router.post("/telegram/webhook", summary="Webhook endpoint for production bot deployments")
def webhook(request: Request,
            x_telegram_bot_api_secret_token: str | None = Header(default=None),
            update: dict | None = None):
    """Acknowledge webhook deliveries.

    The bots in this repository run in long-polling mode by default; a deployment
    that prefers webhooks points Telegram at this URL with `TELEGRAM_WEBHOOK_SECRET`.
    The payload is acknowledged here and processed by the bot process.
    """
    from app.core.security import constant_time_eq

    from app.core.config import settings

    if settings.TELEGRAM_WEBHOOK_SECRET:
        if not x_telegram_bot_api_secret_token or not constant_time_eq(
                x_telegram_bot_api_secret_token, settings.TELEGRAM_WEBHOOK_SECRET):
            raise Unauthorized("Invalid webhook secret", code="webhook_secret_invalid")
    return {"ok": True, "received_at": datetime.now(UTC)}


# ------------------------------------------------------------------ service plane
class BotSession(BaseModel):
    telegram_user_id: int
    telegram_username: str | None = None


class ServiceChat(BaseModel):
    telegram_user_id: int
    question: str = Field(min_length=3, max_length=1000)
    language: str = Field(default="uz", pattern="^(uz|ru|en|kk|tr|ky)$")


def _bot_tenant(mode: BotMode, telegram_user_id: int) -> Tenant:
    """Resolve the tenant for a bot request — from the linked account only."""
    rate_limit.hit(f"bot:{mode}:{telegram_user_id}", limit=60)
    admin = AdminSessionLocal()
    try:
        account = telegram_service.find_account(admin, telegram_user_id=telegram_user_id,
                                               mode=mode)
        org = admin.get(Organization, account.organization_id)
        member = admin.scalar(select(OrganizationMember).where(
            OrganizationMember.organization_id == account.organization_id,
            OrganizationMember.user_id == account.user_id))
        user = admin.get(User, account.user_id) if account.user_id else None
        if org is None or user is None:
            raise Unauthorized("Linked account is not usable", code="not_linked")
        if not account.alerts_enabled:
            pass  # alerting preference is read by the bot, not enforced here
        tenant_role = Role(member.role) if member else Role.VIEWER
    finally:
        admin.close()

    from app.core.db import SessionLocal
    db = SessionLocal()
    bind(db, org_id=org.id, user_id=user.id)
    return Tenant(db=db, user=user, org=org, membership=member, role=tenant_role,
                  identity=None,  # type: ignore[arg-type]
                  bot_language=account.language,
                  bot_alerts_enabled=bool(account.alerts_enabled))


def _close(tenant: Tenant) -> None:
    tenant.db.close()


@router.post("/telegram/service/demo-session", summary="Demo bot: open a session on the DEMO org")
def demo_session(payload: BotSession, mode: BotMode):
    if mode != "demo":
        raise Forbidden("Only the demo bot may open a demo session", code="environment_mismatch")
    with AdminSessionLocal() as admin:
        return telegram_service.ensure_demo_session(
            admin, telegram_user_id=payload.telegram_user_id,
            telegram_username=payload.telegram_username)


@router.post("/telegram/service/link", summary="Official bot: exchange a code for a session")
def link(payload: BotSession, mode: BotMode, code: str = Query(min_length=4, max_length=32)):
    with AdminSessionLocal() as admin:
        return telegram_service.link_bot_account(
            admin, code=code, telegram_user_id=payload.telegram_user_id,
            telegram_username=payload.telegram_username, mode=mode)


@router.get("/telegram/service/me", summary="Bot: linked account context")
def me(mode: BotMode, telegram_user_id: int):
    tenant = _bot_tenant(mode, telegram_user_id)
    try:
        return {"organization": tenant.org.name, "is_demo": tenant.org.is_demo,
                "role": tenant.role.value, "user": tenant.user.full_name,
                "currency": tenant.org.currency, "timezone": tenant.org.timezone,
                "language": tenant.bot_language or "uz",
                "alerts_enabled": bool(tenant.bot_alerts_enabled)}
    finally:
        _close(tenant)


@router.get("/telegram/service/dashboard", summary="Bot: dashboard summary")
def bot_dashboard(mode: BotMode, telegram_user_id: int, period: str = "month"):
    tenant = _bot_tenant(mode, telegram_user_id)
    try:
        return dashboard.summary(tenant, period=period)
    finally:
        _close(tenant)


@router.get("/telegram/service/anomalies", summary="Bot: latest anomalies")
def bot_anomalies(mode: BotMode, telegram_user_id: int, limit: int = Query(5, ge=1, le=20)):
    tenant = _bot_tenant(mode, telegram_user_id)
    try:
        return anomaly_service.list_stored(tenant, limit=limit)
    finally:
        _close(tenant)


@router.get("/telegram/service/forecast", summary="Bot: forecast")
def bot_forecast(mode: BotMode, telegram_user_id: int, horizon_days: int = Query(30, ge=1, le=180)):
    tenant = _bot_tenant(mode, telegram_user_id)
    try:
        return forecast.generate(tenant, horizon_days=horizon_days, persist=False)
    finally:
        _close(tenant)


@router.post("/telegram/service/chat", summary="Bot: grounded AI question")
def bot_chat(payload: ServiceChat, mode: BotMode):
    tenant = _bot_tenant(mode, payload.telegram_user_id)
    try:
        return ai.ask(tenant, question=payload.question, language=payload.language)
    finally:
        _close(tenant)


@router.post("/telegram/service/upload", summary="Official bot: CSV/XLSX upload")
async def bot_upload(mode: BotMode, telegram_user_id: int = Form(...),
                     file: UploadFile = File(...), meter_id: uuid.UUID | None = Form(default=None),
                     reading_type: str | None = Form(default=None)):
    if mode != "official":
        raise Forbidden("File upload is only available in the official bot",
                        code="demo_read_only")
    from app.api.v1.imports import _read_upload
    content = await _read_upload(file)
    tenant = _bot_tenant(mode, telegram_user_id)
    try:
        if meter_id is None:
            from app.services.meter_service import list_meters
            meters, _total = list_meters(tenant.db, tenant.org_id, limit=1)
            if not meters:
                raise NotFound("No meter exists yet; create one in the web platform first")
            meter_id = meters[0].id
        job = importer.create_job(tenant, filename=file.filename or "upload.csv",
                                  content=content, content_type=file.content_type,
                                  meter_id=meter_id, reading_type=reading_type)
        importer.validate_job(tenant, job.id, content=content, meter_id=meter_id,
                              reading_type=reading_type or job.reading_type, mapping=None,
                              tz_name=tenant.org.timezone, interval_minutes=None,
                              decimal_comma=None)
        tenant.db.refresh(job)
        result = importer.confirm_job(tenant, job.id)
        return {"job_id": str(job.id), **result}
    finally:
        _close(tenant)


@router.post("/telegram/service/report", summary="Bot: generate a report")
def bot_report(mode: BotMode, telegram_user_id: int, kind: str = "dashboard",
               fmt: str = "pdf", period: str = "month"):
    tenant = _bot_tenant(mode, telegram_user_id)
    try:
        row = exports.generate(tenant, kind=kind, fmt=fmt, period=period)
        return {"id": str(row.id), "filename": row.filename, "format": row.format,
                "size_bytes": row.size_bytes}
    finally:
        _close(tenant)


@router.get("/telegram/service/report/{report_id}", summary="Bot: download a report")
def bot_report_download(report_id: uuid.UUID, mode: BotMode, telegram_user_id: int):
    tenant = _bot_tenant(mode, telegram_user_id)
    try:
        path, row = exports.report_path(tenant, report_id)
        return FileResponse(path, media_type="application/octet-stream", filename=row.filename)
    finally:
        _close(tenant)


@router.get("/telegram/service/notifications", summary="Bot: recent notifications")
def bot_notifications(mode: BotMode, telegram_user_id: int, limit: int = Query(10, ge=1, le=50)):
    tenant = _bot_tenant(mode, telegram_user_id)
    try:
        return notifications.list_notifications(tenant, limit=limit)
    finally:
        _close(tenant)


@router.post("/telegram/service/language", summary="Bot: set interface language")
def bot_language(mode: BotMode, telegram_user_id: int, language: str):
    with AdminSessionLocal() as admin:
        telegram_service.set_language(admin, telegram_user_id=telegram_user_id, mode=mode,
                                      language=language)
    return {"language": language}


@router.post("/telegram/service/alerts", summary="Bot: toggle anomaly alerts")
def bot_alerts(mode: BotMode, telegram_user_id: int):
    with AdminSessionLocal() as admin:
        enabled = telegram_service.toggle_alerts(admin, telegram_user_id=telegram_user_id,
                                                 mode=mode)
    return {"alerts_enabled": enabled}


@router.post("/telegram/service/unlink", response_model=Message, summary="Bot: unlink account")
def bot_unlink(mode: BotMode, payload: BotSession):
    with AdminSessionLocal() as admin:
        account = telegram_service.find_account(admin, telegram_user_id=payload.telegram_user_id,
                                                mode=mode)
        telegram_service.unlink(admin, account_id=account.id)
    return {"message": "Unlinked"}


@router.get("/telegram/service/admin-stats", summary="Bot: system statistics for designated admin")
def admin_stats(mode: BotMode, telegram_user_id: int):
    from sqlalchemy import func
    from app.core.config import settings
    from app.models import Anomaly, AuditLog, Meter, MeterReading

    admin_ids = [int(x.strip()) for x in settings.ADMIN_TELEGRAM_IDS.split(",") if x.strip().isdigit()]
    if telegram_user_id not in admin_ids:
        raise Forbidden("Faqat tizim administratorlari uchun", code="admin_only")

    with AdminSessionLocal() as admin:
        orgs_count = admin.scalar(select(func.count()).select_from(Organization)) or 0
        users_count = admin.scalar(select(func.count()).select_from(User)) or 0
        meters_count = admin.scalar(select(func.count()).select_from(Meter)) or 0
        readings_count = admin.scalar(select(func.count()).select_from(MeterReading)) or 0
        anomalies_count = admin.scalar(select(func.count()).select_from(Anomaly)) or 0
        telegram_count = admin.scalar(select(func.count()).select_from(TelegramAccount)) or 0
        audit_count = admin.scalar(select(func.count()).select_from(AuditLog)) or 0

    return {
        "admin_telegram_id": telegram_user_id,
        "organizations": orgs_count,
        "users": users_count,
        "meters": meters_count,
        "readings": readings_count,
        "anomalies": anomalies_count,
        "telegram_accounts": telegram_count,
        "audit_logs": audit_count,
        "environment": settings.ENVIRONMENT,
        "server_time": datetime.now(UTC).isoformat()
    }
