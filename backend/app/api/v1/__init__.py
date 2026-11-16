from fastapi import APIRouter

from app.api.v1 import (ai, analytics, anomalies, auth, dashboard, forecast, imports, meters,
                        notifications, organizations, reports, savings,
                        telegram)

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(organizations.router)
api_router.include_router(meters.router)
api_router.include_router(imports.router)
api_router.include_router(analytics.router)
api_router.include_router(dashboard.router)
api_router.include_router(anomalies.router)
api_router.include_router(forecast.router)
api_router.include_router(ai.router)
api_router.include_router(savings.router)
api_router.include_router(reports.router)
api_router.include_router(notifications.router)
api_router.include_router(telegram.router)

__all__ = ["api_router"]
