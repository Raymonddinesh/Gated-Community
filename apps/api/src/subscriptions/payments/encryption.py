"""Phase 21E.3 — Gateway Credential Encryption and Sensitive Data Protection.

Provides symmetric encryption for payment gateway API secrets and webhook signing
keys using Fernet (AES-128-CBC + HMAC-SHA256). Derives a stable 32-byte key from
the application SECRET_KEY to ensure zero plaintext storage of payment credentials.
"""

import base64
import hashlib
import re
from typing import Any

from cryptography.fernet import Fernet

from apps.api.src.core.config import get_settings


def _get_fernet_instance() -> Fernet:
    """Derive a 32-byte urlsafe base64-encoded key from settings.SECRET_KEY."""
    settings = get_settings()
    # SHA-256 yields 32 bytes; encode to standard base64 for Fernet key
    derived_bytes = hashlib.sha256(settings.SECRET_KEY.encode("utf-8")).digest()
    urlsafe_key = base64.urlsafe_b64encode(derived_bytes)
    return Fernet(urlsafe_key)


def encrypt_secret(plaintext: str) -> str:
    """Encrypt a plaintext gateway secret or webhook signing key."""
    if not plaintext:
        return ""
    fernet = _get_fernet_instance()
    return fernet.encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_secret(ciphertext: str) -> str:
    """Decrypt an encrypted gateway secret or webhook signing key."""
    if not ciphertext:
        return ""
    fernet = _get_fernet_instance()
    return fernet.decrypt(ciphertext.encode("utf-8")).decode("utf-8")


def mask_secret(secret: str | None, prefix_len: int = 4, suffix_len: int = 4) -> str:
    """Safely mask a sensitive secret for logs and diagnostic payloads.

    Example: 'rzp_test_secret12345678' -> 'rzp_...5678'
    """
    if not secret:
        return "[EMPTY]"
    if len(secret) <= (prefix_len + suffix_len):
        return "[REDACTED]"
    return f"{secret[:prefix_len]}...{secret[-suffix_len:]}"


def redact_sensitive_dict(data: dict[str, Any]) -> dict[str, Any]:
    """Recursively scrub sensitive keys from dictionaries for audit logs and error messages."""
    sensitive_keys = {
        "secret",
        "secret_key",
        "key_secret",
        "encrypted_secret",
        "webhook_secret",
        "webhook_secret_primary",
        "webhook_secret_secondary",
        "password",
        "access_token",
        "cvv",
        "card_number",
        "authorization",
        "x-razorpay-signature",
    }
    redacted: dict[str, Any] = {}
    for k, v in data.items():
        if k.lower() in sensitive_keys:
            redacted[k] = "[REDACTED]"
        elif isinstance(v, dict):
            redacted[k] = redact_sensitive_dict(v)
        elif isinstance(v, list):
            redacted[k] = [
                redact_sensitive_dict(item) if isinstance(item, dict) else item
                for item in v
            ]
        elif isinstance(v, str) and re.search(r"rzp_(live|test)_[a-zA-Z0-9]+", v):
            redacted[k] = mask_secret(v)
        else:
            redacted[k] = v
    return redacted
