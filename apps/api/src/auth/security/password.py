"""Password Hashing, Verification, and Policy Validation using Argon2id."""

import logging

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from apps.api.src.core.config import get_settings
from apps.api.src.core.exceptions import AppException

logger = logging.getLogger("societysphere.auth.password")

# Production-grade Argon2id hasher configuration
# RFC 9106 recommended parameters for sensitive systems
_hasher = PasswordHasher(
    time_cost=3,
    memory_cost=65536,  # 64 MiB
    parallelism=4,
    hash_len=32,
    salt_len=16,
)

# Precomputed dummy hash used to equalize timing when non-existent users are queried
_DUMMY_HASH = _hasher.hash("dummy_constant_time_comparison_password")

COMMON_WEAK_PASSWORDS = {
    "password",
    "password123",
    "12345678",
    "123456789",
    "qwerty123",
    "admin123",
    "societysphere",
}


def hash_password(password: str) -> str:
    """Hash a plaintext password using Argon2id."""
    return _hasher.hash(password)


def verify_password(plain_password: str, hashed_password: str | None) -> bool:
    """
    Verify a plaintext password against an Argon2id hash in constant time.
    Returns False safely if hash is None or verification fails.
    """
    if not hashed_password:
        return False
    try:
        return _hasher.verify(hashed_password, plain_password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False
    except Exception as exc:
        logger.warning(f"Unexpected error during password verification: {exc}")
        return False


def verify_dummy_password() -> None:
    """
    Perform a constant-time dummy verification when an account is not found.
    Prevents account enumeration via response latency timing attacks.
    """
    try:
        _hasher.verify(_DUMMY_HASH, "dummy_password_attempt")
    except Exception:
        pass


def validate_password_policy(password: str) -> None:
    """
    Validate that password meets the server-enforced security policy.
    Raises AppException with code WEAK_PASSWORD (HTTP 400) if invalid.
    """
    settings = get_settings()

    if not password or len(password) < settings.AUTH_PASSWORD_MIN_LENGTH:
        raise AppException(
            code="WEAK_PASSWORD",
            message=f"Password must be at least {settings.AUTH_PASSWORD_MIN_LENGTH} characters long.",
            status_code=400,
        )

    if len(password) > settings.AUTH_PASSWORD_MAX_LENGTH:
        raise AppException(
            code="WEAK_PASSWORD",
            message=f"Password cannot exceed {settings.AUTH_PASSWORD_MAX_LENGTH} characters.",
            status_code=400,
        )

    if password.lower() in COMMON_WEAK_PASSWORDS:
        raise AppException(
            code="WEAK_PASSWORD",
            message="Password is too common and easily guessed. Please select a stronger password.",
            status_code=400,
        )
