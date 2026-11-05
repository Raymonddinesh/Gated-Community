"""Tests for Strongly Typed Configuration."""

import pytest
from pydantic import ValidationError

from apps.api.src.core.config import EnvironmentType, Settings


def test_default_development_config():
    settings = Settings()
    assert settings.APP_NAME == "SocietySphere"
    assert settings.API_PREFIX == "/api/v1"
    assert isinstance(settings.CORS_ALLOWED_ORIGINS, list)
    assert len(settings.CORS_ALLOWED_ORIGINS) > 0


def test_production_constraints_validation():
    # Production with debug=True should raise ValidationError
    with pytest.raises(ValidationError):
        Settings(
            APP_ENV=EnvironmentType.PRODUCTION,
            DEBUG=True,
            SECRET_KEY="a-sufficiently-long-secret-key-32-chars-at-least",
            CORS_ALLOWED_ORIGINS=["https://app.societysphere.com"],
        )

    # Production with insecure default secret key should raise ValidationError
    with pytest.raises(ValidationError):
        Settings(
            APP_ENV=EnvironmentType.PRODUCTION,
            DEBUG=False,
            SECRET_KEY="dev-insecure-secret-key-change-in-production-min-32-chars",
            CORS_ALLOWED_ORIGINS=["https://app.societysphere.com"],
        )

    # Production with wildcard CORS should raise ValidationError
    with pytest.raises(ValidationError):
        Settings(
            APP_ENV=EnvironmentType.PRODUCTION,
            DEBUG=False,
            SECRET_KEY="valid-secure-random-production-key-minimum-32",
            CORS_ALLOWED_ORIGINS=["*"],
        )


def test_comma_separated_cors_and_hosts_parsing():
    settings = Settings(
        CORS_ALLOWED_ORIGINS="http://localhost:3000, https://socapp.com",
        ALLOWED_HOSTS="localhost, api.socapp.com",
    )
    assert settings.CORS_ALLOWED_ORIGINS == ["http://localhost:3000", "https://socapp.com"]
    assert settings.ALLOWED_HOSTS == ["localhost", "api.socapp.com"]
