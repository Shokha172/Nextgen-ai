"""Organization profile, members, invitations and tariffs (all org-scoped)."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.db import AdminSessionLocal
from app.core.errors import Conflict, Forbidden, NotFound, ValidationFailed
from app.core.security import hash_opaque_token, new_opaque_token
from app.core.tenant import Tenant
from app.models import Organization, OrganizationMember, Tariff, User
from app.models.enums import AuditAction, ROLE_RANK, Role
from app.services import audit


def list_for_user(admin_db: Session, user_id: uuid.UUID) -> list[tuple[Organization, str]]:
    rows = admin_db.execute(
        select(Organization, OrganizationMember.role)
        .join(OrganizationMember, OrganizationMember.organization_id == Organization.id)
        .where(OrganizationMember.user_id == user_id, OrganizationMember.status == "active")
        .order_by(Organization.name)).all()
    return [(r[0], r[1]) for r in rows]


def create(user_id: uuid.UUID, payload) -> Organization:
    from app.services.auth_service import _unique_slug
    with AdminSessionLocal() as db:
        org = Organization(name=payload.name.strip(), slug=_unique_slug(db, payload.name),
                           industry=payload.industry.value if hasattr(payload.industry, "value") else payload.industry,
                           region=payload.region, city=payload.city, address=payload.address,
                           currency=payload.currency, timezone=payload.timezone, created_by=user_id)
        db.add(org)
        db.flush()
        db.add(OrganizationMember(organization_id=org.id, user_id=user_id,
                                  role=Role.OWNER.value, status="active",
                                  accepted_at=datetime.now(UTC)))
        db.commit()
        db.refresh(org)
        audit.record(AuditAction.ORG_CREATE, org_id=org.id, user_id=user_id,
                     meta={"name": org.name})
        return org


def update(tenant: Tenant, payload) -> Organization:
    tenant.require(Role.ADMIN)
    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        if key == "industry" and value is not None:
            value = value.value if hasattr(value, "value") else value
        setattr(tenant.org, key, value)
    tenant.db.commit()
    tenant.db.refresh(tenant.org)
    audit.record(AuditAction.ORG_UPDATE, org_id=tenant.org_id, user_id=tenant.user_id,
                 meta={"fields": sorted(data)})
    return tenant.org


# ---- members -------------------------------------------------------------
def list_members(tenant: Tenant) -> list[dict]:
    """Membership rows come from the RLS-bound tenant session; the identity fields
    (email, name) are joined in from a privileged read, because `users` is not
    granted to the tenant role. Only emails of *this* org's members are returned."""
    members = list(tenant.db.scalars(
        select(OrganizationMember)
        .where(OrganizationMember.organization_id == tenant.org_id)
        .order_by(OrganizationMember.created_at)))
    user_ids = [m.user_id for m in members if m.user_id]
    people: dict[uuid.UUID, User] = {}
    if user_ids:
        with AdminSessionLocal() as admin:
            for u in admin.scalars(select(User).where(User.id.in_(user_ids))):
                people[u.id] = u
    out = []
    for m in members:
        u = people.get(m.user_id) if m.user_id else None
        out.append({
            "id": m.id, "user_id": m.user_id, "role": m.role,
            "status": m.status, "title": m.title, "department": m.department,
            "invited_email": m.invited_email, "accepted_at": m.accepted_at,
            "created_at": m.created_at,
            "email": u.email if u else (m.invited_email or ""),
            "full_name": u.full_name if u else "",
        })
    return out


def invite_member(tenant: Tenant, payload) -> tuple[OrganizationMember, str | None]:
    tenant.require(Role.ADMIN)
    email = payload.email.lower()
    if ROLE_RANK[Role(payload.role)] > ROLE_RANK[tenant.role]:
        raise Forbidden("You cannot invite someone with a role above your own",
                        code="role_escalation")
    with AdminSessionLocal() as admin:
        existing_user = admin.scalar(select(User).where(func.lower(User.email) == email))
    # duplicate check must see rows outside RLS (the user may exist in another org)
    already = tenant.db.scalar(select(func.count()).select_from(OrganizationMember).where(
        OrganizationMember.organization_id == tenant.org_id,
        OrganizationMember.invited_email == email))
    if already:
        raise Conflict("This email has already been invited to the organization",
                       code="already_invited")
    invite_token = new_opaque_token(24)
    member = OrganizationMember(
        organization_id=tenant.org_id,
        user_id=existing_user.id if existing_user else None,
        role=payload.role.value, status="invited", invited_email=email,
        invited_by=tenant.user_id, invited_at=datetime.now(UTC),
        invite_token_hash=hash_opaque_token(invite_token),
        department=payload.department, title=payload.title)
    tenant.db.add(member)
    tenant.db.commit()
    tenant.db.refresh(member)
    audit.record(AuditAction.MEMBER_INVITE, org_id=tenant.org_id, user_id=tenant.user_id,
                 target_type="member", target_id=str(member.id),
                 meta={"email": email, "role": payload.role.value})
    # The plaintext token is returned exactly once, to the inviter.
    return member, invite_token


def update_member_role(tenant: Tenant, member_id: uuid.UUID, new_role: Role) -> OrganizationMember:
    tenant.require(Role.ADMIN)
    member = tenant.db.scalar(select(OrganizationMember).where(
        OrganizationMember.id == member_id, OrganizationMember.organization_id == tenant.org_id))
    if member is None:
        raise NotFound("Member not found")
    if ROLE_RANK[new_role] >= ROLE_RANK[Role.OWNER] and not tenant.can(Role.OWNER):
        raise Forbidden("Only an owner can grant the owner role", code="role_escalation")
    if member.user_id == tenant.user_id and ROLE_RANK[new_role] < ROLE_RANK[Role.ADMIN]:
        raise ValidationFailed("You cannot demote yourself below admin", code="self_demote")
    owners = tenant.db.scalar(select(func.count()).select_from(OrganizationMember).where(
        OrganizationMember.organization_id == tenant.org_id,
        OrganizationMember.role == Role.OWNER.value, OrganizationMember.status == "active"))
    if member.role == Role.OWNER.value and new_role != Role.OWNER and owners <= 1:
        raise ValidationFailed("An organization must keep at least one owner",
                               code="last_owner")
    member.role = new_role.value
    tenant.db.commit()
    audit.record(AuditAction.MEMBER_ROLE_CHANGE, org_id=tenant.org_id, user_id=tenant.user_id,
                 target_type="member", target_id=str(member.id), meta={"role": new_role.value})
    return member


def remove_member(tenant: Tenant, member_id: uuid.UUID) -> None:
    tenant.require(Role.ADMIN)
    member = tenant.db.scalar(select(OrganizationMember).where(
        OrganizationMember.id == member_id, OrganizationMember.organization_id == tenant.org_id))
    if member is None:
        raise NotFound("Member not found")
    if member.role == Role.OWNER.value:
        owners = tenant.db.scalar(select(func.count()).select_from(OrganizationMember).where(
            OrganizationMember.organization_id == tenant.org_id,
            OrganizationMember.role == Role.OWNER.value))
        if owners <= 1:
            raise ValidationFailed("An organization must keep at least one owner",
                                   code="last_owner")
    tenant.db.delete(member)
    tenant.db.commit()
    audit.record(AuditAction.MEMBER_REMOVE, org_id=tenant.org_id, user_id=tenant.user_id,
                 target_type="member", target_id=str(member_id))


# ---- tariffs -------------------------------------------------------------
def list_tariffs(tenant: Tenant) -> list[Tariff]:
    return list(tenant.db.scalars(select(Tariff).where(Tariff.organization_id == tenant.org_id)
                                  .order_by(Tariff.valid_from.desc())))


def create_tariff(tenant: Tenant, payload) -> Tariff:
    tenant.require(Role.ADMIN)
    if payload.valid_to and payload.valid_to < payload.valid_from:
        raise ValidationFailed("valid_to must not be before valid_from", code="invalid_period")
    tariff = Tariff(organization_id=tenant.org_id, **payload.model_dump())
    if payload.is_default:
        for t in list_tariffs(tenant):
            t.is_default = False
    tenant.db.add(tariff)
    tenant.db.commit()
    tenant.db.refresh(tariff)
    return tariff


def default_tariff(db: Session, org_id: uuid.UUID, on_date=None):
    """Tariff valid on a date, preferring the org default. Returns None when the
    organization has not configured a price — callers must then show 'no tariff'
    instead of inventing a number."""
    q = select(Tariff).where(Tariff.organization_id == org_id)
    if on_date is not None:
        q = q.where(Tariff.valid_from <= on_date,
                    (Tariff.valid_to.is_(None)) | (Tariff.valid_to >= on_date))
    q = q.order_by(Tariff.is_default.desc(), Tariff.valid_from.desc()).limit(1)
    return db.scalar(q)
