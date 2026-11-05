"""Application Configuration Management with Pydantic v2 Settings."""

from enum import StrEnum
from functools import lru_cache

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class EnvironmentType(StrEnum):
    DEVELOPMENT = "development"
    TESTING = "testing"
    STAGING = "staging"
    PRODUCTION = "production"


class Settings(BaseSettings):
    """Strongly typed application configuration."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", case_sensitive=True, extra="ignore"
    )

    # Application Metadata
    APP_NAME: str = "SocietySphere"
    APP_ENV: EnvironmentType = EnvironmentType.DEVELOPMENT
    DEBUG: bool = False
    API_PREFIX: str = "/api/v1"
    PORT: int = 8000
    HOST: str = "0.0.0.0"

    # Security & CORS
    CORS_ALLOWED_ORIGINS: str | list[str] = Field(default=["http://localhost:3000", "http://127.0.0.1:3000"])
    ALLOWED_HOSTS: str | list[str] = Field(default=["localhost", "127.0.0.1"])
    SECRET_KEY: str = Field(
        default="dev-insecure-secret-key-change-in-production-min-32-chars", min_length=32
    )
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    PASSWORD_RESET_TOKEN_EXPIRE_MINUTES: int = 15

    # Password Policy
    AUTH_PASSWORD_MIN_LENGTH: int = 8
    AUTH_PASSWORD_MAX_LENGTH: int = 128

    # Rate Limiting & Account Protection (per minute)
    AUTH_LOGIN_RATE_LIMIT_PER_MINUTE: int = 10
    AUTH_PASSWORD_RESET_RATE_LIMIT_PER_MINUTE: int = 5
    AUTH_REFRESH_RATE_LIMIT_PER_MINUTE: int = 30

    # Database
    DATABASE_URL: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/societysphere_dev"
    )
    DATABASE_POOL_SIZE: int = 10
    DATABASE_MAX_OVERFLOW: int = 20
    DATABASE_POOL_TIMEOUT: int = 30

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_POOL_SIZE: int = 10
    REDIS_TIMEOUT: int = 5

    # RabbitMQ
    RABBITMQ_URL: str = "amqp://guest:guest@localhost:5672/"
    RABBITMQ_ENABLED: bool = True
    RABBITMQ_CONNECTION_TIMEOUT: int = 5

    # Object Storage (S3 / MinIO)
    OBJECT_STORAGE_ENDPOINT: str = "http://localhost:9000"
    OBJECT_STORAGE_ACCESS_KEY: str = "minioadmin"
    OBJECT_STORAGE_SECRET_KEY: str = "minioadmin"
    OBJECT_STORAGE_BUCKET: str = "societysphere-documents"
    OBJECT_STORAGE_REGION: str = "us-east-1"
    OBJECT_STORAGE_USE_SSL: bool = False

    # Statutory Billing Issuer Configuration (Configurable - Not Hardcoded)
    ISSUER_LEGAL_NAME: str = "SocietySphere Technologies India Private Limited"
    ISSUER_TRADE_NAME: str = "SocietySphere SaaS"
    ISSUER_CIN: str = "U72900MH2026PTC987654"
    ISSUER_PAN: str = "AABCS1429B"
    ISSUER_GSTIN: str = "27AABCS1429B1Z1"
    ISSUER_REGISTERED_ADDRESS: str = "Level 8, Tower B, Cyber City, Magarpatta, Pune, Maharashtra 411028, India"
    ISSUER_BILLING_EMAIL: str = "billing@societysphere.com"
    ISSUER_SUPPORT_PHONE: str = "+91 20 4000 8000"
    ISSUER_STATE_CODE: str = "27"
    ISSUER_STATE_NAME: str = "Maharashtra"

    # Billing Email Delivery Provider Configuration
    EMAIL_PROVIDER: str = "MOCK"  # 'MOCK', 'SMTP', 'SES'
    EMAIL_FROM_ADDRESS: str = "billing@societysphere.com"
    EMAIL_FROM_NAME: str = "SocietySphere Billing"
    SMTP_HOST: str = "localhost"
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_USE_TLS: bool = True

    # Logging & Monitoring
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "json"

    # Rate Limiting & Request Constraints
    RATE_LIMIT_PER_MINUTE: int = 100
    MAX_REQUEST_SIZE_BYTES: int = 10 * 1024 * 1024  # 10MB

    @field_validator("CORS_ALLOWED_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @field_validator("ALLOWED_HOSTS", mode="before")
    @classmethod
    def parse_allowed_hosts(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, str):
            return [host.strip() for host in value.split(",") if host.strip()]
        return value

    @model_validator(mode="after")
    def validate_production_constraints(self) -> "Settings":
        """Enforce strict security constraints in production."""
        if self.APP_ENV == EnvironmentType.PRODUCTION:
            if self.DEBUG:
                raise ValueError("DEBUG must be False in production environments.")
            if "insecure" in self.SECRET_KEY.lower() or len(self.SECRET_KEY) < 32:
                raise ValueError(
                    "A secure SECRET_KEY (minimum 32 characters) must be configured in production."
                )
            if "*" in self.CORS_ALLOWED_ORIGINS:
                raise ValueError("Wildcard '*' CORS origins are strictly forbidden in production.")
        return self


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings singleton."""
    return Settings()
