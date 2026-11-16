"""Import every model so metadata is complete for Alembic autogenerate."""
from app.models.base import Base, JSONType, TimestampMixin, UUIDMixin, utcnow
from app.models.enums import *  # noqa: F401,F403
from app.models.identity import AuthSession, PasswordResetToken, User
from app.models.organization import Organization, OrganizationMember
from app.models.meter import Meter, MeterReading, Tariff
from app.models.imports import ImportJob, ImportStagingRow
from app.models.intelligence import AIInsight, Anomaly, Forecast, SavingsReport
from app.models.ops import AuditLog, Notification, Report
from app.models.telegram import TelegramAccount, TelegramLinkCode

__all__ = [
    "Base", "JSONType", "TimestampMixin", "UUIDMixin", "utcnow",
    "User", "AuthSession", "PasswordResetToken",
    "Organization", "OrganizationMember",
    "Meter", "MeterReading", "Tariff", "ImportJob", "ImportStagingRow",
    "Anomaly", "Forecast", "AIInsight", "SavingsReport",
    "Report", "Notification", "AuditLog",
    "TelegramAccount", "TelegramLinkCode",
]
