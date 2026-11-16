"""Authentication endpoints. See docs/API.md for the full contract."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Request, Response
from sqlalchemy import select

from app.api.v1._cookies import clear_session_cookies, set_session_cookies
from app.core.config import settings
from app.core.deps import CurrentIdentity, LoginRateLimit, REFRESH_COOKIE
from app.core.db import AdminSessionLocal
from app.core.errors import Unauthorized
from app.models import Organization, OrganizationMember, User
from app.schemas.auth import (LoginRequest, PasswordChangeRequest, PasswordForgotRequest,
                             PasswordForgotResponse, PasswordResetRequest, ProfileUpdate,
                             RefreshRequest, RegisterRequest, SessionOut, SwitchOrgRequest,
                             UserOut)
from app.schemas.common import Message
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


def _meta(request: Request) -> dict:
    return {"ip": request.client.host if request.client else None,
            "user_agent": request.headers.get("user-agent")}


def _session_payload(result: dict, db) -> SessionOut:
    memberships = result["memberships"]
    org = result.get("org")
    return SessionOut(
        user=UserOut.model_validate(result["user"]),
        memberships=[{"organization_id": m.organization_id, "role": m.role,
                      "status": m.status, "department": m.department, "title": m.title}
                     for m in memberships if m.organization_id],
        active_organization=({"id": org.id, "name": org.name, "slug": org.slug,
                              "is_demo": org.is_demo} if org else None),
        role=result.get("role"),
        token={"access_token": result["token"]["access_token"],
               "token_type": "bearer", "expires_in": result["token"]["expires_in"]},
    )


@router.post("/register", response_model=SessionOut, status_code=201,
             summary="Create an account and (optionally) its first organization")
def register(payload: RegisterRequest, request: Request, response: Response,
             _rl: LoginRateLimit):
    result = auth_service.register(payload, request_meta=_meta(request))
    set_session_cookies(response, result["token"])
    return _session_payload(result, None)


@router.post("/login", response_model=SessionOut, summary="Password login, returns a session")
def login(payload: LoginRequest, request: Request, response: Response, _rl: LoginRateLimit):
    result = auth_service.login(payload.email, payload.password, org_id=payload.organization_id,
                               request_meta=_meta(request))
    set_session_cookies(response, result["token"])
    return _session_payload(result, None)


@router.post("/refresh", summary="Rotate the refresh token and issue a new access token")
def refresh(request: Request, response: Response, payload: RefreshRequest | None = None):
    from_refresh_cookie = request.cookies.get(REFRESH_COOKIE)
    token = (payload.refresh_token if payload and payload.refresh_token else None) \
        or from_refresh_cookie
    if not token:
        raise Unauthorized("Refresh token required", code="refresh_required")
    result = auth_service.refresh(token, request_meta=_meta(request))
    set_session_cookies(response, result["token"])
    return {"access_token": result["token"]["access_token"], "token_type": "bearer",
            "expires_in": result["token"]["expires_in"], "user": UserOut.model_validate(result["user"])}


@router.post("/logout", response_model=Message, summary="Revoke the current session")
def logout(identity: CurrentIdentity, request: Request, response: Response):
    auth_service.logout(identity.session.id if identity.session else None,
                        user_id=identity.user.id, request_meta=_meta(request))
    clear_session_cookies(response)
    return {"message": "Signed out"}


@router.get("/me", summary="Current user, memberships and active organization")
def me(identity: CurrentIdentity):
    """Identity-plane read: the organization list is derived from the caller's own
    membership rows, so it is authorized by construction (no client-supplied ids
    and no reliance on a tenant GUC, which is deliberately unset here).

    The response mirrors the login payload (minus the token) so a client can use
    one shape for both.
    """
    memberships, active = [], None
    if identity.memberships:
        ids = [m.organization_id for m in identity.memberships]
        with AdminSessionLocal() as admin:
            rows = admin.scalars(select(Organization).where(Organization.id.in_(ids))).all()
        by_id = {o.id: o for o in rows}
        for m in identity.memberships:
            org = by_id.get(m.organization_id)
            if org is None or m.status != "active":
                continue
            memberships.append({"organization_id": org.id, "name": org.name, "slug": org.slug,
                                "role": m.role, "status": m.status,
                                "department": m.department, "title": m.title,
                                "is_demo": org.is_demo})
            if identity.active_org_id and org.id == identity.active_org_id:
                active = {"id": org.id, "name": org.name, "slug": org.slug,
                          "is_demo": org.is_demo, "role": identity.role.value
                          if identity.role else m.role}
        if active is None and memberships:
            first = memberships[0]
            org = by_id[first["organization_id"]]
            active = {"id": org.id, "name": org.name, "slug": org.slug,
                      "is_demo": org.is_demo, "role": first["role"]}
    return {"user": UserOut.model_validate(identity.user), "memberships": memberships,
            "active_organization": active,
            "role": identity.role.value if identity.role else None}


@router.patch("/me", response_model=UserOut, summary="Update the caller's own profile")
def update_me(payload: ProfileUpdate, identity: CurrentIdentity):
    """Only the caller's own display name and locale are editable — never role,
    organization or activation state."""
    with AdminSessionLocal() as admin:
        user = admin.get(User, identity.user.id)
        if user is None:
            raise Unauthorized("Session user no longer exists")
        if payload.full_name is not None:
            user.full_name = payload.full_name.strip()
        if payload.locale is not None:
            user.locale = payload.locale.value
        admin.commit()
        admin.refresh(user)
        return UserOut.model_validate(user)


@router.post("/switch-org", summary="Switch the active organization for this session")
def switch_org(payload: SwitchOrgRequest, identity: CurrentIdentity, request: Request,
               response: Response):
    result = auth_service.switch_org(identity.user.id, payload.organization_id,
                                    session_id=identity.session.id if identity.session else None,
                                    request_meta=_meta(request))
    set_session_cookies(response, {"access_token": result["token"]["access_token"],
                                   "expires_in": result["token"]["expires_in"]})
    return {"message": "Organization switched", "organization_id": result["org_id"],
            "role": result["role"]}


@router.post("/forgot-password", response_model=PasswordForgotResponse,
             summary="Request a password reset token")
def forgot_password(payload: PasswordForgotRequest, request: Request, _rl: LoginRateLimit):
    token, message = auth_service.request_password_reset(payload.email, request_meta=_meta(request))
    return {"message": message, "dev_reset_token": token}


@router.post("/reset-password", response_model=Message, summary="Complete a password reset")
def reset_password(payload: PasswordResetRequest, request: Request, _rl: LoginRateLimit):
    auth_service.reset_password(payload.token, payload.new_password, request_meta=_meta(request))
    return {"message": "Password updated. All sessions have been signed out."}


@router.post("/change-password", response_model=Message, summary="Change password (authenticated)")
def change_password(payload: PasswordChangeRequest, identity: CurrentIdentity,
                    response: Response):
    auth_service.change_password(identity.user.id, payload.current_password, payload.new_password)
    clear_session_cookies(response)
    return {"message": "Password updated. Please sign in again."}
