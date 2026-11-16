from __future__ import annotations

import uuid

from fastapi import APIRouter

from app.core.db import AdminSessionLocal
from app.models import Organization
from app.core.deps import CurrentIdentity, TenantAdmin, TenantOwner, TenantViewer
from app.core.errors import Forbidden, NotFound
from app.core.tenant import Tenant
from app.schemas.common import Message
from app.schemas.org import (InviteOut, MemberInvite, MemberOut, MemberRoleUpdate, OrgCreate,
                            OrgOut, OrgUpdate, TariffCreate, TariffOut)
from app.services import org_service

router = APIRouter(tags=["organizations"])


@router.get("/organizations", summary="Organizations the caller belongs to")
def list_organizations(identity: CurrentIdentity):
    with AdminSessionLocal() as admin:
        rows = org_service.list_for_user(admin, identity.user.id)
    return {"items": [{"id": o.id, "name": o.name, "slug": o.slug, "industry": o.industry,
                       "city": o.city, "currency": o.currency, "is_demo": o.is_demo,
                       "role": role, "created_at": o.created_at} for o, role in rows],
            "total": len(rows)}


@router.post("/organizations", response_model=OrgOut, status_code=201,
             summary="Create a new organization (caller becomes owner)")
def create_organization(payload: OrgCreate, identity: CurrentIdentity):
    org = org_service.create(identity.user.id, payload)
    return OrgOut.model_validate(org)


@router.get("/organizations/{org_id}", response_model=OrgOut,
            summary="Organization profile (members only)")
def get_organization(org_id: uuid.UUID, identity: CurrentIdentity):
    if identity.role_in(org_id) is None:
        raise Forbidden("You do not have access to this organization", code="cross_org_denied")
    with AdminSessionLocal() as admin:
        org = admin.get(Organization, org_id)
    if org is None:
        raise NotFound("Organization not found")
    return OrgOut.model_validate(org)


@router.get("/organization", response_model=OrgOut, summary="Active organization profile")
def active_organization(tenant: TenantViewer):
    return OrgOut.model_validate(tenant.org)


@router.patch("/organization", response_model=OrgOut, summary="Update active organization settings")
def update_organization(payload: OrgUpdate, tenant: TenantAdmin):
    return OrgOut.model_validate(org_service.update(tenant, payload))


@router.get("/members", summary="Members of the active organization")
def list_members(tenant: TenantViewer):
    items = org_service.list_members(tenant)
    return {"items": items, "total": len(items)}


@router.post("/members/invite", response_model=InviteOut, status_code=201,
             summary="Invite a member by email")
def invite_member(payload: MemberInvite, tenant: TenantAdmin):
    member, invite_token = org_service.invite_member(tenant, payload)
    from app.core.config import settings
    # No SMTP transport in this build: the token is returned to the inviter and the
    # admin shares the link out of band. Hidden in production until mail is configured.
    return InviteOut(member_id=member.id, email=payload.email, role=member.role,
                     status=member.status,
                     invite_token=invite_token if settings.EXPOSE_DEV_TOKENS else None)


@router.patch("/members/{member_id}", response_model=Message, summary="Change a member's role")
def update_member(member_id: uuid.UUID, payload: MemberRoleUpdate, tenant: TenantAdmin):
    member = org_service.update_member_role(tenant, member_id, payload.role)
    return {"message": f"Role updated to {member.role}"}


@router.delete("/members/{member_id}", response_model=Message, summary="Remove a member")
def remove_member(member_id: uuid.UUID, tenant: TenantOwner):
    org_service.remove_member(tenant, member_id)
    return {"message": "Member removed"}


@router.get("/tariffs", summary="Organization tariffs")
def list_tariffs(tenant: TenantViewer):
    rows = org_service.list_tariffs(tenant)
    return {"items": [TariffOut.model_validate(t) for t in rows], "total": len(rows)}


@router.post("/tariffs", response_model=TariffOut, status_code=201,
             summary="Configure an electricity tariff")
def create_tariff(payload: TariffCreate, tenant: TenantAdmin):
    return TariffOut.model_validate(org_service.create_tariff(tenant, payload))
