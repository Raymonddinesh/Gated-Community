"""Vehicle registration number normalization domain utility."""

import re


def normalize_registration_number(registration_number: str) -> str:
    """
    Deterministically normalizes a vehicle registration number.

    Rules:
    - Strips all non-alphanumeric characters (spaces, dashes, dots, slashes)
    - Uppercases all characters
    - Example: 'mh-02 ab 1234' -> 'MH02AB1234'
    - Example: 'TN 38 / CD-9988' -> 'TN38CD9988'
    """
    if not registration_number:
        raise ValueError("Registration number cannot be empty")

    normalized = re.sub(r"[^A-Za-z0-9]", "", registration_number).upper()

    if len(normalized) < 3:
        raise ValueError(
            f"Registration number '{registration_number}' is too short (min 3 alphanumeric characters)"
        )
    if len(normalized) > 20:
        raise ValueError(
            f"Registration number '{registration_number}' is too long (max 20 alphanumeric characters)"
        )

    return normalized
