"""Phase 21E.4A — Indian GSTIN Format and Checksum Validator.

Provides syntactic and Luhn Mod-36 checksum validation for Indian Goods and Services
Tax Identification Numbers (GSTIN) under the GST Network (GSTN) specification:
- 15 characters alphanumeric format.
- Chars 1-2: State code (01-38, 97).
- Chars 3-12: Permanent Account Number (PAN).
- Char 13: Entity code (1-9, A-Z).
- Char 14: Default character 'Z'.
- Char 15: Check digit (Luhn Mod-36).

Mandatory Requirement:
- Format and checksum validation confirms structural validity only.
- Does NOT verify active registration status with GSTN/government portals (requires live GSP integration).
"""

import re
from typing import Final

from pydantic import BaseModel, ConfigDict

from apps.api.src.subscriptions.tax.state_codes import GST_STATE_CODES

# Base-36 alphabet defined in GSTN specification
BASE36_ALPHABET: Final[str] = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
MOD_BASE: Final[int] = 36

# Syntactic pattern for 15-character GSTIN
GSTIN_REGEX: Final[re.Pattern[str]] = re.compile(
    r"^(?P<state>[0-9]{2})"
    r"(?P<pan>[A-Z]{5}[0-9]{4}[A-Z]{1})"
    r"(?P<entity>[1-9A-Z]{1})"
    r"Z"
    r"(?P<checksum>[0-9A-Z]{1})$"
)

# Valid PAN 4th characters for entity types:
# C: Company, P: Person, H: HUF, F: Firm/LLP, A: AOP, T: Trust, B: BOI, L: Local Auth, J: Juridical, G: Govt
VALID_PAN_ENTITY_TYPES: Final[set[str]] = {
    "C", "P", "H", "F", "A", "T", "B", "L", "J", "G"
}

REGISTRATION_DISCLAIMER: Final[str] = (
    "Syntactic and checksum validation confirms structural correctness only. "
    "Active registration status, taxpayer trade name, and return filing status "
    "must be verified through an authorized GST Suvidha Provider (GSP) or official GSTN portal."
)


class GSTINValidationResult(BaseModel):
    """Result of validating a GSTIN format and structure."""

    model_config = ConfigDict(frozen=True)

    gstin: str
    is_valid: bool
    syntactic_valid: bool
    checksum_valid: bool
    state_code: str | None = None
    state_name: str | None = None
    pan: str | None = None
    entity_code: str | None = None
    calculated_checksum: str | None = None
    error_message: str | None = None
    is_active_registration: bool | None = None  # Always None in format validation
    disclaimer: str = REGISTRATION_DISCLAIMER


class GSTINValidator:
    """Validator for Indian GSTIN format, structure, and Luhn Mod-36 checksum."""

    @classmethod
    def calculate_checksum(cls, gstin_14: str) -> str:
        """Calculate the 15th check digit for a 14-character GSTIN prefix using Luhn Mod-36."""
        if len(gstin_14) != 14:
            raise ValueError(f"Expected exactly 14 characters for checksum calculation, got {len(gstin_14)}.")

        factor = 1
        total = 0

        for char in gstin_14.upper():
            code = BASE36_ALPHABET.find(char)
            if code < 0:
                raise ValueError(f"Invalid alphanumeric character '{char}' in GSTIN.")

            digit = factor * code
            # Mod-36 digit reduction
            digit = (digit // MOD_BASE) + (digit % MOD_BASE)
            total += digit

            # Alternate factor between 1 and 2
            factor = 2 if factor == 1 else 1

        rem = total % MOD_BASE
        check_code = (MOD_BASE - rem) % MOD_BASE
        return BASE36_ALPHABET[check_code]

    @classmethod
    def validate(
        cls,
        gstin: str | None,
        verify_checksum: bool = True,
    ) -> GSTINValidationResult:
        """Validate GSTIN structure, state code, PAN entity, and Luhn Mod-36 checksum."""
        if not gstin or not isinstance(gstin, str):
            return GSTINValidationResult(
                gstin="" if gstin is None else str(gstin),
                is_valid=False,
                syntactic_valid=False,
                checksum_valid=False,
                error_message="GSTIN must be a non-empty string.",
            )

        cleaned = gstin.strip().upper()
        if len(cleaned) != 15:
            return GSTINValidationResult(
                gstin=cleaned,
                is_valid=False,
                syntactic_valid=False,
                checksum_valid=False,
                error_message=f"GSTIN must be exactly 15 characters long (got {len(cleaned)}).",
            )

        match = GSTIN_REGEX.match(cleaned)
        if not match:
            return GSTINValidationResult(
                gstin=cleaned,
                is_valid=False,
                syntactic_valid=False,
                checksum_valid=False,
                error_message="GSTIN does not match official syntactic pattern.",
            )

        state_code = match.group("state")
        pan = match.group("pan")
        entity_code = match.group("entity")
        actual_checksum = match.group("checksum")

        # 1. Validate State Code
        if state_code not in GST_STATE_CODES:
            return GSTINValidationResult(
                gstin=cleaned,
                is_valid=False,
                syntactic_valid=False,
                checksum_valid=False,
                state_code=state_code,
                error_message=f"Invalid state code '{state_code}' in GSTIN.",
            )

        state_name = GST_STATE_CODES[state_code]

        # 2. Validate PAN 4th character (entity type)
        pan_entity_type = pan[3]
        if pan_entity_type not in VALID_PAN_ENTITY_TYPES:
            return GSTINValidationResult(
                gstin=cleaned,
                is_valid=False,
                syntactic_valid=False,
                checksum_valid=False,
                state_code=state_code,
                state_name=state_name,
                pan=pan,
                error_message=f"Invalid PAN entity type character '{pan_entity_type}' in GSTIN.",
            )

        # 3. Validate Luhn Mod-36 Checksum
        calculated_checksum = None
        checksum_valid = True

        if verify_checksum:
            try:
                calculated_checksum = cls.calculate_checksum(cleaned[:14])
                checksum_valid = calculated_checksum == actual_checksum
            except Exception as exc:
                checksum_valid = False
                return GSTINValidationResult(
                    gstin=cleaned,
                    is_valid=False,
                    syntactic_valid=True,
                    checksum_valid=False,
                    state_code=state_code,
                    state_name=state_name,
                    pan=pan,
                    entity_code=entity_code,
                    error_message=f"Checksum calculation error: {exc}",
                )

        is_overall_valid = checksum_valid

        return GSTINValidationResult(
            gstin=cleaned,
            is_valid=is_overall_valid,
            syntactic_valid=True,
            checksum_valid=checksum_valid,
            state_code=state_code,
            state_name=state_name,
            pan=pan,
            entity_code=entity_code,
            calculated_checksum=calculated_checksum,
            error_message=None if is_overall_valid else f"Checksum mismatch: expected '{calculated_checksum}', got '{actual_checksum}'.",
        )

    @classmethod
    def extract_state_code(cls, gstin: str | None) -> str | None:
        """Extract valid 2-digit state code from GSTIN if valid; otherwise None."""
        if not gstin:
            return None
        res = cls.validate(gstin, verify_checksum=False)
        return res.state_code if res.syntactic_valid else None
