"""Tests for Argon2id Password Hashing, Verification, and Password Policy Validation."""

import pytest

from apps.api.src.auth.security.password import (
    hash_password,
    validate_password_policy,
    verify_dummy_password,
    verify_password,
)
from apps.api.src.core.exceptions import AppException


def test_argon2id_hashing_and_verification() -> None:
    """Argon2id produces standard hashes and verifies identical plaintexts."""
    password = "SuperSecurePassword123!"
    hashed = hash_password(password)

    assert hashed.startswith("$argon2id$")
    assert verify_password(password, hashed) is True
    assert verify_password("WrongPassword123!", hashed) is False
    assert verify_password("", hashed) is False
    assert verify_password(password, None) is False


def test_constant_time_dummy_verification() -> None:
    """Dummy verification runs safely without throwing exceptions."""
    verify_dummy_password()


def test_password_policy_minimum_length() -> None:
    """Password below minimum length is rejected with HTTP 400 WEAK_PASSWORD."""
    with pytest.raises(AppException) as exc_info:
        validate_password_policy("short")
    assert exc_info.value.code == "WEAK_PASSWORD"
    assert exc_info.value.status_code == 400


def test_password_policy_maximum_length() -> None:
    """Password exceeding maximum length is rejected."""
    with pytest.raises(AppException) as exc_info:
        validate_password_policy("A" * 129)
    assert exc_info.value.code == "WEAK_PASSWORD"
    assert exc_info.value.status_code == 400


def test_password_policy_common_weak_passwords() -> None:
    """Common dictionary passwords are unconditionally rejected."""
    for weak in ["password", "password123", "12345678", "societysphere", "admin123"]:
        with pytest.raises(AppException) as exc_info:
            validate_password_policy(weak)
        assert exc_info.value.code == "WEAK_PASSWORD"


def test_password_policy_valid_passwords() -> None:
    """Compliant strong passwords pass validation cleanly."""
    valid_passwords = [
        "ComplexP@ssw0rd!",
        "SocietySphere2026Secure",
        "Correct-Horse-Battery-Staple-99",
    ]
    for pw in valid_passwords:
        validate_password_policy(pw)
