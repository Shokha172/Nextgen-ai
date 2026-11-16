"""In-app notifications.

Notifications are derived from real events (a confirmed import, a detected
anomaly, a generated report). They are never generated speculatively, and the
Telegram bots read the same rows — `delivered_telegram` tracks delivery.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import func, select, update

from app.core.errors import NotFound
from app.core.tenant import Tenant
from app.models import Notification
from app.models.enums import NotificationType

MAX_ANOMALY_NOTIFICATIONS = 5


def serialize(row: Notification) -> dict:
    payload = row.payload or {}
    return {
        "id": row.id, "type": row.type, "severity": row.severity, "title": row.title,
        "body": row.body, "payload": payload, "read_at": row.read_at,
        "delivered_telegram": row.delivered_telegram, "created_at": row.created_at,
    }


def _add(tenant: Tenant, *, kind: NotificationType, title: str, body: str,
         severity: str = "info", payload: dict | None = None) -> Notification:
    row = Notification(organization_id=tenant.org_id, user_id=None, type=kind.value,
                       severity=severity, title=title[:200], body=body,
                       payload=payload or {}, created_at=datetime.now(UTC))
    tenant.db.add(row)
    return row


def notify_anomalies(tenant: Tenant, anomalies: list[dict]) -> int:
    """One notification per anomaly, capped, so a burst cannot flood the feed."""
    if not anomalies:
        return 0
    ordered = sorted(anomalies, key=lambda item: abs(float(item["deviation_pct"])), reverse=True)
    created = 0
    for item in ordered[:MAX_ANOMALY_NOTIFICATIONS]:
        severity = "critical" if item["severity"] == "critical" else "warning"
        _add(tenant, kind=NotificationType.ANOMALY,
             title=f"Anomaliya: {item['meter']}",
             body=(f"{item['ts_local'] if isinstance(item.get('ts_local'), str) else item['ts']}: "
                   f"{Decimal(str(item['observed_kwh'])):.1f} kWh — kutilgan "
                   f"{Decimal(str(item['expected_kwh'])):.1f} kWh "
                   f"(og'ish {Decimal(str(item['deviation_pct'])):.1f}%)."),
             severity=severity,
             payload={"meter_id": str(item.get("meter_id")), "observed_kwh":
                      str(item["observed_kwh"]), "expected_kwh": str(item["expected_kwh"]),
                      "deviation_pct": str(item["deviation_pct"]),
                      "method": item.get("method")})
        created += 1
    tenant.db.commit()
    return created


def notify_import(tenant: Tenant, *, inserted: int, skipped: int = 0,
                  job_id: uuid.UUID | None = None) -> None:
    """Called by the importer after a confirmed import."""
    _add(tenant, kind=NotificationType.IMPORT, severity="info",
         title="Import yakunlandi",
         body=f"{inserted} qator yozildi, {skipped} qator o'tkazib yuborildi.",
         payload={"import_job_id": str(job_id) if job_id else None,
                  "inserted": inserted, "skipped": skipped})
    tenant.db.commit()


def notify_report(tenant: Tenant, *, report_id: uuid.UUID, title: str, fmt: str) -> None:
    _add(tenant, kind=NotificationType.SYSTEM, title="Hisobot tayyor",
         body=f"{title} ({fmt.upper()}) yaratildi.",
         payload={"report_id": str(report_id), "format": fmt})
    tenant.db.commit()


def list_notifications(tenant: Tenant, *, unread_only: bool = False, limit: int = 50,
                       offset: int = 0) -> dict:
    base = select(Notification).where(Notification.organization_id == tenant.org_id)
    if unread_only:
        base = base.where(Notification.read_at.is_(None))
    total = tenant.db.scalar(select(func.count()).select_from(base.subquery())) or 0
    unread = tenant.db.scalar(select(func.count()).select_from(Notification).where(
        Notification.organization_id == tenant.org_id,
        Notification.read_at.is_(None))) or 0
    rows = tenant.db.scalars(base.order_by(Notification.created_at.desc())
                             .limit(limit).offset(offset))
    return {"items": [serialize(row) for row in rows], "total": total, "unread": unread,
            "limit": limit, "offset": offset}


def mark_read(tenant: Tenant, notification_id: uuid.UUID) -> None:
    row = tenant.db.scalar(select(Notification).where(
        Notification.id == notification_id,
        Notification.organization_id == tenant.org_id))
    if row is None:
        raise NotFound("Notification not found")
    if row.read_at is None:
        row.read_at = datetime.now(UTC)
        tenant.db.commit()


def mark_all_read(tenant: Tenant) -> int:
    result = tenant.db.execute(update(Notification).where(
        Notification.organization_id == tenant.org_id,
        Notification.read_at.is_(None)).values(read_at=datetime.now(UTC)))
    tenant.db.commit()
    return int(result.rowcount or 0)
