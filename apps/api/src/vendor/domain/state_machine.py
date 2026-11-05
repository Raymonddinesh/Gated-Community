"""Vendor Status State Machine and Lifecycle Governance."""

from apps.api.src.vendor.domain.enums import VendorStatus
from apps.api.src.vendor.domain.exceptions import VendorInvalidStatusTransitionException

VALID_STATUS_TRANSITIONS: dict[VendorStatus, set[VendorStatus]] = {
    VendorStatus.ONBOARDING: {
        VendorStatus.ACTIVE,
        VendorStatus.INACTIVE,
        VendorStatus.OFFBOARDED,
    },
    VendorStatus.ACTIVE: {
        VendorStatus.INACTIVE,
        VendorStatus.SUSPENDED,
        VendorStatus.BLACKLISTED,
        VendorStatus.OFFBOARDED,
    },
    VendorStatus.INACTIVE: {
        VendorStatus.ACTIVE,
        VendorStatus.OFFBOARDED,
    },
    VendorStatus.SUSPENDED: {
        VendorStatus.ACTIVE,
        VendorStatus.INACTIVE,
        VendorStatus.BLACKLISTED,
        VendorStatus.OFFBOARDED,
    },
    VendorStatus.BLACKLISTED: {
        VendorStatus.OFFBOARDED,
        # Admin override can restore to ACTIVE if explicitly requested with audit log
        VendorStatus.ACTIVE,
    },
    VendorStatus.OFFBOARDED: set(),  # Terminal state
}


def validate_status_transition(
    current_status: VendorStatus | str,
    target_status: VendorStatus | str,
    is_admin_override: bool = False,
) -> None:
    """Validate vendor lifecycle status transition rules.

    Raises VendorInvalidStatusTransitionException if transition is disallowed.
    """
    curr = VendorStatus(current_status)
    tgt = VendorStatus(target_status)

    if curr == tgt:
        return

    allowed = VALID_STATUS_TRANSITIONS.get(curr, set())
    if tgt not in allowed and not (is_admin_override and curr != VendorStatus.OFFBOARDED):
        raise VendorInvalidStatusTransitionException(
            current_status=str(curr),
            target_status=str(tgt),
            reason=f"Transition from {curr} to {tgt} is not permitted.",
        )
