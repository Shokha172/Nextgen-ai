"""NEXTGEN AI — FastAPI application factory.

Layering: api -> services -> models. Routers never build SQL; services never parse
HTTP. Tenant scope is resolved once per request by `app.core.deps.get_tenant`.
"""
from __future__ import annotations

import time
import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1 import api_router
from app.core.config import settings
from app.core.db import healthcheck
from app.core.errors import install_error_handlers
from app.core.logging import configure_logging, log, request_id_ctx

DESCRIPTION = """
Enterprise energy intelligence API for Uzbek businesses.

**Conventions**
* All timestamps are UTC (`TIMESTAMPTZ`); the web client renders `Asia/Tashkent`.
* `consumption_kwh` is *energy* accumulated over an interval; `power_kw` is the
  average *power* over the same interval. They are never interchangeable.
* Every endpoint below `/api/v1` (except auth and bot webhooks) is scoped to one
  organization, and additionally enforced by PostgreSQL Row Level Security.
* Errors always share one envelope: `{"error": {"code", "message", "request_id"}}`.

**Roles**: owner > admin > analyst > viewer. Write endpoints state the minimum role.
"""

TAGS = [
    {"name": "auth", "description": "Registration, login, refresh rotation, password reset"},
    {"name": "organizations", "description": "Organization profile, members, tariffs"},
    {"name": "meters", "description": "Meters and interval readings"},
    {"name": "imports", "description": "CSV/XLSX import pipeline"},
    {"name": "analytics", "description": "Consumption aggregation and comparison"},
    {"name": "dashboard", "description": "Executive dashboard summary"},
    {"name": "anomalies", "description": "Explainable anomaly detection"},
    {"name": "forecast", "description": "Forecasting with accuracy backtest"},
    {"name": "ai", "description": "Grounded AI advisor"},
    {"name": "savings", "description": "Verified savings reports"},
    {"name": "reports", "description": "PDF / XLSX / CSV exports"},
    {"name": "notifications", "description": "In-app alerts"},
    {"name": "telegram", "description": "Bot linking and webhooks"},
    {"name": "system", "description": "Health and metadata"},
]


def create_app() -> FastAPI:
    configure_logging(settings.DEBUG)
    problems = settings.validate_runtime()
    if problems:
        raise RuntimeError("Unsafe production configuration: " + "; ".join(problems))

    app = FastAPI(
        title=f"{settings.APP_NAME} API",
        version="1.0.0",
        description=DESCRIPTION,
        openapi_tags=TAGS,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Bot-Service-Key", "X-Bot-Mode",
                       "X-Requested-With"],
        max_age=600,
    )

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
        token = request_id_ctx.set(rid)
        started = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            request_id_ctx.reset(token)
        duration_ms = round((time.perf_counter() - started) * 1000, 1)
        response.headers["x-request-id"] = rid
        response.headers["x-response-time-ms"] = str(duration_ms)
        response.headers["x-content-type-options"] = "nosniff"
        response.headers["x-frame-options"] = "DENY"
        response.headers["referrer-policy"] = "no-referrer"
        response.headers["cache-control"] = response.headers.get(
            "cache-control", "no-store" if request.url.path.startswith("/api/") else "no-cache")
        log.info("%s %s -> %s", request.method, request.url.path, response.status_code,
                 extra={"path": request.url.path, "status": response.status_code,
                        "duration_ms": duration_ms})
        return response

    install_error_handlers(app)
    app.include_router(api_router, prefix=settings.API_V1)

    @app.get("/health", tags=["system"], summary="Liveness")
    def health():
        return {"status": "ok", "service": settings.APP_NAME, "version": "1.0.0",
                "environment": settings.ENVIRONMENT}

    @app.get("/health/ready", tags=["system"], summary="Readiness (database reachable)")
    def ready():
        ok, detail = healthcheck()
        return JSONResponse(
            {"status": "ready" if ok else "degraded", "database": detail},
            status_code=200 if ok else 503)

    @app.get("/api/v1/meta", tags=["system"], summary="Product metadata for clients")
    def meta():
        return {
            "product": settings.APP_NAME,
            "tagline": "Transform Energy Data Into Intelligent Decisions.",
            "market": "Uzbekistan",
            "languages": ["uz", "ru", "en"],
            "units": {"energy": "kWh", "power": "kW", "currency": ["UZS", "USD"]},
            "display_timezone": settings.DISPLAY_TZ,
            "ai_provider": settings.AI_PROVIDER if settings.GEMINI_API_KEY else "rule_based",
        }

    return app


app = create_app()
