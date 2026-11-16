"""Session cookies: httpOnly, SameSite=Lax, Secure in production.

The Next.js server forwards these cookies to the API, so the browser never holds
tokens in JavaScript-accessible storage.
"""
from __future__ import annotations

from fastapi import Response

from app.core.config import settings
from app.core.deps import ACCESS_COOKIE, REFRESH_COOKIE


def set_session_cookies(response: Response, token: dict) -> None:
    secure = settings.is_prod
    response.set_cookie(ACCESS_COOKIE, token["access_token"],
                        max_age=token.get("expires_in", settings.ACCESS_TOKEN_TTL_MIN * 60),
                        httponly=True, samesite="lax", secure=secure, path="/")
    if token.get("refresh_token"):
        response.set_cookie(REFRESH_COOKIE, token["refresh_token"],
                            max_age=settings.REFRESH_TOKEN_TTL_DAYS * 86400,
                            httponly=True, samesite="lax", secure=secure, path="/")


def clear_session_cookies(response: Response) -> None:
    for name in (ACCESS_COOKIE, REFRESH_COOKIE):
        response.delete_cookie(name, path="/")
