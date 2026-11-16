from __future__ import annotations

import uuid

from fastapi import APIRouter, Query

from app.core.deps import TenantViewer
from app.schemas.common import Message
from app.services import notifications

router = APIRouter(tags=["notifications"])


@router.get("/notifications", summary="In-app notifications")
def list_notifications(tenant: TenantViewer, unread_only: bool = False,
                       limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)):
    return notifications.list_notifications(tenant, unread_only=unread_only,
                                            limit=limit, offset=offset)


@router.post("/notifications/{notification_id}/read", response_model=Message,
             summary="Mark a notification as read")
def mark_read(notification_id: uuid.UUID, tenant: TenantViewer):
    notifications.mark_read(tenant, notification_id)
    return {"message": "Marked as read"}
