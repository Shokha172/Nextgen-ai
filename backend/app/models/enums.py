"""Domain enumerations. Stored as VARCHAR + CHECK (native_enum=False) so that
adding a value is a cheap migration instead of a Postgres type rewrite."""
from __future__ import annotations

import enum


class Role(str, enum.Enum):
    OWNER = "owner"
    ADMIN = "admin"
    ANALYST = "analyst"
    VIEWER = "viewer"


ROLE_RANK = {Role.VIEWER: 1, Role.ANALYST: 2, Role.ADMIN: 3, Role.OWNER: 4}


class Industry(str, enum.Enum):
    MANUFACTURING = "manufacturing"
    COMMERCIAL = "commercial"
    LOGISTICS = "logistics"
    DATA_CENTER = "data_center"
    AGRO = "agro"
    OTHER = "other"


class MeterType(str, enum.Enum):
    INTERVAL = "interval"        # readings already are consumption per interval (kWh)
    CUMULATIVE = "cumulative"    # readings are a monotonically growing meter register (kWh)


class ReadingSource(str, enum.Enum):
    IMPORT = "import"
    MANUAL = "manual"
    SEED = "seed"
    API = "api"


class ImportStatus(str, enum.Enum):
    UPLOADED = "uploaded"
    VALIDATED = "validated"
    CONFIRMED = "confirmed"
    FAILED = "failed"


class AnomalyMethod(str, enum.Enum):
    ROLLING_ZSCORE = "rolling_zscore"
    ROBUST_MAD = "robust_mad"
    TIME_OF_DAY = "time_of_day"
    THRESHOLD = "threshold"


class Severity(str, enum.Enum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ForecastMethod(str, enum.Enum):
    MOVING_AVERAGE = "moving_average"
    EXP_SMOOTHING = "exp_smoothing"
    SEASONAL = "seasonal"


class ReportKind(str, enum.Enum):
    CONSUMPTION = "consumption"
    ANOMALIES = "anomalies"
    SAVINGS = "savings"
    FORECAST = "forecast"
    DASHBOARD = "dashboard"


class ReportFormat(str, enum.Enum):
    PDF = "pdf"
    XLSX = "xlsx"
    CSV = "csv"


class NotificationType(str, enum.Enum):
    ANOMALY = "anomaly"
    FORECAST = "forecast"
    IMPORT = "import"
    SYSTEM = "system"
    ALERT = "alert"


class AIKind(str, enum.Enum):
    CHAT = "chat"
    ANALYSIS = "analysis"
    SAVINGS = "savings"


class Language(str, enum.Enum):
    UZ = "uz"
    RU = "ru"
    EN = "en"
    KK = "kk"
    TR = "tr"
    KY = "ky"


class AuditAction(str, enum.Enum):
    LOGIN = "login"
    LOGIN_FAILED = "login_failed"
    LOGOUT = "logout"
    REGISTER = "register"
    ORG_CREATE = "org_create"
    ORG_UPDATE = "org_update"
    MEMBER_INVITE = "member_invite"
    MEMBER_ROLE_CHANGE = "member_role_change"
    MEMBER_REMOVE = "member_remove"
    METER_CREATE = "meter_create"
    METER_UPDATE = "meter_update"
    METER_DELETE = "meter_delete"
    IMPORT_CREATE = "import_create"
    IMPORT_CONFIRM = "import_confirm"
    REPORT_EXPORT = "report_export"
    TELEGRAM_LINK = "telegram_link"
    TELEGRAM_UNLINK = "telegram_unlink"
    AI_QUERY = "ai_query"
    CROSS_ORG_DENIED = "cross_org_denied"
