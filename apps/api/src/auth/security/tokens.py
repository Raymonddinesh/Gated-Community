"""Cryptographic Token Management: JWT Access Tokens and Hashed Opaque Tokens."""

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import jwt

from apps.api.src.core.config import get_settings
from apps.api.src.core.exceptions import AuthenticationException


def generate_opaque_token() -> str:
    """Generate a high-entropy, cryptographically random opaque token (384-bit entropy)."""
    return secrets.token_urlsafe(48)


def hash_token(token: str) -> str:
    """Compute the SHA-256 digest of an opaque token for secure storage and indexing."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_access_token(user_id: UUID, session_id: UUID) -> str:
    """
    Generate a short-lived signed JWT access token.
    Contains identity and session pointer; does NOT contain mutable society permissions.
    """
    settings = get_settings()
    now = datetime.now(UTC)
    expires_at = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    payload: dict[str, Any] = {
        "sub": str(user_id),
        "sid": str(session_id),
        "jti": str(uuid.uuid4()),
        "type": "access",
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
    }

    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any]:
    """
    Decode and validate a signed JWT access token.
    Raises AuthenticationException on expiration or invalid cryptographic signature.
    """
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
            options={"require": ["sub", "sid", "exp", "iat"]},
        )
        if payload.get("type") != "access":
            raise AuthenticationException(message="Invalid token type", details={"code": "INVALID_TOKEN"})
        return payload
    except jwt.ExpiredSignatureError:
        raise AuthenticationException(
            message="Access token has expired. Please refresh your session.",
            details={"code": "TOKEN_EXPIRED"},
        )
    except jwt.InvalidTokenError as exc:
        raise AuthenticationException(
            message="Invalid or tampered access token.",
            details={"code": "INVALID_TOKEN", "reason": str(exc)},
        )
