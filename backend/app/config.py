"""Centralized, validated configuration loaded from environment variables."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: Literal["development", "staging", "production"] = "development"
    log_level: str = "INFO"
    log_json: bool = False
    cors_allow_origins: str = "*"

    database_url: str = Field(
        default="postgresql+psycopg2://postgres:postgres@db:5432/ai_receptionist",
        alias="DATABASE_URL",
    )
    db_reset_schema: bool = False

    admin_api_key: str = Field(default="", alias="ADMIN_API_KEY")
    admin_api_key_previous: str = Field(default="", alias="ADMIN_API_KEY_PREVIOUS")
    session_secret: str = Field(default="", alias="SESSION_SECRET")
    jwt_secret: str = Field(default="", alias="JWT_SECRET")
    jwt_expire_minutes: int = 60
    admin_totp_secret: str = Field(default="", alias="ADMIN_TOTP_SECRET")
    field_encryption_key: str = Field(default="", alias="FIELD_ENCRYPTION_KEY")
    rate_limit: str = Field(default="60/minute", alias="RATE_LIMIT")

    sentry_dsn: str = Field(default="", alias="SENTRY_DSN")
    alert_webhook_url: str = Field(default="", alias="ALERT_WEBHOOK_URL")

    llm_enabled: bool = False
    llm_provider: str = ""
    llm_model: str = ""
    api_key: str = ""
    llm_api_key: str = ""
    llm_timeout_seconds: int = 15
    llm_max_history_messages: int = 20
    llm_chat_temperature: float = 0.6
    llm_chat_max_tokens: int = 450

    email_enabled: bool = False
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    email_from: str = ""
    hotel_name: str = "SMART Hotel"
    booking_notify_email: str = ""
    email_provider: str = "auto"
    resend_api_key: str = ""
    resend_from: str = ""
    resend_allowed_to: str = ""
    smtp_use_tls: bool = True
    smtp_use_ssl: bool = False
    mailpit_ui_url: str = "http://localhost:8025"

    @field_validator("log_level")
    @classmethod
    def _normalize_log_level(cls, value: str) -> str:
        return (value or "INFO").upper()

    @field_validator("db_reset_schema", mode="before")
    @classmethod
    def _parse_bool(cls, value: object) -> bool:
        if isinstance(value, bool):
            return value
        return str(value or "").lower() in ("1", "true", "yes")

    def cors_origins(self) -> list[str]:
        value = (self.cors_allow_origins or "").strip()
        if not value or value == "*":
            return ["*"]
        return [part.strip() for part in value.split(",") if part.strip()]

    def llm_api_key_resolved(self) -> str:
        return self.api_key.strip() or self.llm_api_key.strip() or ""

    def validate_startup(self) -> list[str]:
        warnings: list[str] = []
        errors: list[str] = []

        if self.app_env == "production":
            if self.cors_allow_origins.strip() == "*":
                errors.append("CORS_ALLOW_ORIGINS must not be '*' in production")
            if not self.admin_api_key.strip() or len(self.admin_api_key.strip()) < 32:
                errors.append("ADMIN_API_KEY must be at least 32 characters in production")
            if not self.session_secret.strip():
                errors.append("SESSION_SECRET is required in production")
            if not self.admin_totp_secret.strip():
                warnings.append("ADMIN_TOTP_SECRET unset — MFA disabled in production")
            if not self.field_encryption_key.strip():
                warnings.append("FIELD_ENCRYPTION_KEY unset — PII stored without encryption at rest")

        if self.email_enabled and not self.smtp_user and not self.resend_api_key:
            if self.smtp_host not in ("mailpit", "localhost", "127.0.0.1"):
                warnings.append("EMAIL_ENABLED but no SMTP user or Resend API key configured")

        if errors:
            raise RuntimeError("Configuration validation failed: " + "; ".join(errors))
        return warnings


@lru_cache
def get_settings() -> Settings:
    return Settings()
