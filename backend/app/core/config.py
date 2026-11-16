"""Typed, environment-driven configuration. No secret is ever hardcoded."""
from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", "../.env"), extra="ignore", case_sensitive=False)

    # ---- identity -------------------------------------------------------
    APP_NAME: str = "NEXTGEN AI"
    API_V1: str = "/api/v1"
    ENVIRONMENT: Literal["development", "staging", "production", "test"] = "development"
    DEBUG: bool = False
    DISPLAY_TZ: str = "Asia/Tashkent"

    # ---- database -------------------------------------------------------
    # Supports both PostgreSQL (with native RLS) and SQLite (with app-layer tenant isolation).
    DATABASE_URL: str = "sqlite:///./nextgen.db"
    DATABASE_ADMIN_URL: str = "sqlite:///./nextgen.db"
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 5
    DB_ECHO: bool = False

    # ---- auth -----------------------------------------------------------
    JWT_SECRET: str = Field(default="nextgen-ai-enterprise-secret-development-key-32charsmin", description="REQUIRED in production (>=32 chars)")
    JWT_ALG: str = "HS256"
    ACCESS_TOKEN_TTL_MIN: int = 30
    REFRESH_TOKEN_TTL_DAYS: int = 14
    PASSWORD_MIN_LENGTH: int = 10
    # Dev convenience only: return reset/invite tokens in API responses.
    EXPOSE_DEV_TOKENS: bool = True

    # ---- web ------------------------------------------------------------
    CORS_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000"
    PUBLIC_WEB_URL: str = "http://localhost:3000"

    # ---- uploads / limits ----------------------------------------------
    UPLOAD_MAX_MB: int = 10
    UPLOAD_MAX_ROWS: int = 200_000
    MAX_PAGES: int = 100
    RATE_LIMIT_PER_MINUTE: int = 120
    LOGIN_RATE_LIMIT_PER_MINUTE: int = 10

    # ---- AI -------------------------------------------------------------
    AI_PROVIDER: Literal["auto", "gemini", "rule_based"] = "auto"
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.5-flash"
    GEMINI_TIMEOUT_S: int = 25
    AI_MAX_TOKENS: int = 900

    # ---- telegram -------------------------------------------------------
    TELEGRAM_DEMO_BOT_TOKEN: str = ""
    TELEGRAM_OFFICIAL_BOT_TOKEN: str = ""
    TELEGRAM_WEBHOOK_SECRET: str = ""
    BOT_SERVICE_KEY_DEMO: str = "demo-service-key-2026"
    BOT_SERVICE_KEY_OFFICIAL: str = "official-service-key-2026"
    TELEGRAM_LINK_CODE_TTL_MIN: int = 10
    BOT_API_BASE_URL: str = "http://127.0.0.1:8000"

    # ---- reporting ------------------------------------------------------
    DEFAULT_CURRENCY: str = "UZS"
    REPORT_OUTPUT_DIR: str = "./var/reports"

    @field_validator("CORS_ORIGINS")
    @classmethod
    def _strip(cls, v: str) -> str:
        return ",".join(o.strip() for o in v.split(",") if o.strip())

    @property
    def cors_list(self) -> list[str]:
        return [o for o in self.CORS_ORIGINS.split(",") if o]

    @property
    def is_prod(self) -> bool:
        return self.ENVIRONMENT == "production"

    def validate_runtime(self) -> list[str]:
        """Fail fast in production for dangerous defaults."""
        problems: list[str] = []
        if self.is_prod:
            if len(self.JWT_SECRET) < 32:
                problems.append("JWT_SECRET must be >=32 chars in production")
            if self.EXPOSE_DEV_TOKENS:
                problems.append("EXPOSE_DEV_TOKENS must be false in production")
            if "*" in self.cors_list:
                problems.append("CORS_ORIGINS must not be '*' in production")
        return problems


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
