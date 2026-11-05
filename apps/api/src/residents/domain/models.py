"""Domain models, value objects, and deterministic business rules for resident management."""

from datetime import date
from enum import StrEnum


class ResidentType(StrEnum):
    """Types of residency relationship within a unit."""

    OWNER = "OWNER"
    TENANT = "TENANT"
    FAMILY_MEMBER = "FAMILY_MEMBER"
    AUTHORIZED_DELEGATE = "AUTHORIZED_DELEGATE"


class OccupancyStatus(StrEnum):
    """Occupancy lifecycle states."""

    ACTIVE = "ACTIVE"
    ENDED = "ENDED"
    CANCELLED = "CANCELLED"


class OwnershipStatus(StrEnum):
    """Unit ownership lifecycle states."""

    ACTIVE = "ACTIVE"
    TRANSFERRED = "TRANSFERRED"
    CANCELLED = "CANCELLED"


class FamilyRelationshipType(StrEnum):
    """Supported family relationship designations."""

    SPOUSE = "SPOUSE"
    PARENT = "PARENT"
    CHILD = "CHILD"
    SIBLING = "SIBLING"
    OTHER = "OTHER"


class DelegateStatus(StrEnum):
    """Delegate authorization states."""

    ACTIVE = "ACTIVE"
    REVOKED = "REVOKED"
    EXPIRED = "EXPIRED"


class ResidentProfileStatus(StrEnum):
    """Status of the society-scoped resident profile."""

    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    MOVED_OUT = "MOVED_OUT"
    SUSPENDED = "SUSPENDED"


ALLOWED_DELEGATE_PERMISSIONS = {
    "resident.view",
    "resident.update",
    "unit.view",
    "billing.view",
    "payment.view",
    "complaint.create",
    "visitor.manage",
}


def mask_phone(phone: str | None) -> str | None:
    """
    Mask a phone number for privacy preservation.
    Example: '+919876543210' -> '+9198****3210' or '******3210'.
    """
    if not phone or len(phone) < 6:
        return "******" if phone else None
    visible_prefix = phone[:4]
    visible_suffix = phone[-4:]
    masked_middle = "*" * (len(phone) - 8 if len(phone) > 8 else 4)
    return f"{visible_prefix}{masked_middle}{visible_suffix}"


def mask_email(email: str | None) -> str | None:
    """
    Mask an email address for privacy preservation.
    Example: 'resident@example.com' -> 'r***t@example.com'.
    """
    if not email or "@" not in email:
        return "****" if email else None
    local_part, domain = email.split("@", 1)
    if len(local_part) <= 2:
        masked_local = f"{local_part[0]}*"
    else:
        masked_local = f"{local_part[0]}{'*' * (len(local_part) - 2)}{local_part[-1]}"
    return f"{masked_local}@{domain}"


def check_date_overlap(
    start_a: date,
    end_a: date | None,
    start_b: date,
    end_b: date | None,
) -> bool:
    """
    Determine whether two time intervals overlap.
    A None end date represents an open-ended/current interval [start, +inf).
    Overlap exists if: (end_a is None or end_a >= start_b) and (end_b is None or end_b >= start_a).
    """
    if end_a is not None and end_a < start_b:
        return False
    if end_b is not None and end_b < start_a:
        return False
    return True


def calculate_profile_completeness(
    display_name: str | None,
    phone: str | None,
    email: str | None,
    alternate_phone: str | None,
    emergency_contact_name: str | None,
    emergency_contact_phone: str | None,
    preferred_language: str | None,
) -> dict[str, object]:
    """
    Deterministic calculation of resident profile completeness.
    Required fields: Display Name, Primary Phone.
    Optional fields: Email, Alternate Phone, Emergency Contact Name, Emergency Contact Phone, Preferred Language.
    Returns:
        is_complete (bool): True if all required fields are satisfied.
        score_percent (int): 0 to 100 percentage.
        missing_fields (list[str]): List of missing field keys.
    """
    field_status = {
        "display_name": bool(display_name and display_name.strip()),
        "phone": bool(phone and phone.strip()),
        "email": bool(email and email.strip()),
        "alternate_phone": bool(alternate_phone and alternate_phone.strip()),
        "emergency_contact_name": bool(emergency_contact_name and emergency_contact_name.strip()),
        "emergency_contact_phone": bool(emergency_contact_phone and emergency_contact_phone.strip()),
        "preferred_language": bool(preferred_language and preferred_language.strip()),
    }

    required_keys = ["display_name", "phone"]
    missing_required = [k for k in required_keys if not field_status[k]]
    missing_all = [k for k, present in field_status.items() if not present]

    total_weight = len(field_status)
    present_weight = sum(1 for present in field_status.values() if present)
    score_percent = int(round((present_weight / total_weight) * 100))

    return {
        "is_complete": len(missing_required) == 0,
        "score_percent": score_percent,
        "missing_required": missing_required,
        "missing_fields": missing_all,
    }
