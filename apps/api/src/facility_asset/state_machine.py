"""State Machine logic for Assets and Facilities."""

from apps.api.src.facility_asset.enums import AssetStatus, FacilityStatus
from apps.api.src.facility_asset.exceptions import InvalidStateTransitionError

ALLOWED_ASSET_TRANSITIONS: dict[AssetStatus, set[AssetStatus]] = {
    AssetStatus.IN_SERVICE: {
        AssetStatus.UNDER_MAINTENANCE,
        AssetStatus.OUT_OF_SERVICE,
        AssetStatus.DECOMMISSIONED,
        AssetStatus.DISPOSED,
    },
    AssetStatus.UNDER_MAINTENANCE: {
        AssetStatus.IN_SERVICE,
        AssetStatus.OUT_OF_SERVICE,
        AssetStatus.DECOMMISSIONED,
        AssetStatus.DISPOSED,
    },
    AssetStatus.OUT_OF_SERVICE: {
        AssetStatus.IN_SERVICE,
        AssetStatus.UNDER_MAINTENANCE,
        AssetStatus.DECOMMISSIONED,
        AssetStatus.DISPOSED,
    },
    AssetStatus.DECOMMISSIONED: {
        AssetStatus.DISPOSED,
    },
    AssetStatus.DISPOSED: set(),
}

ALLOWED_FACILITY_TRANSITIONS: dict[FacilityStatus, set[FacilityStatus]] = {
    FacilityStatus.ACTIVE: {
        FacilityStatus.UNDER_MAINTENANCE,
        FacilityStatus.TEMPORARILY_CLOSED,
        FacilityStatus.DECOMMISSIONED,
    },
    FacilityStatus.UNDER_MAINTENANCE: {
        FacilityStatus.ACTIVE,
        FacilityStatus.TEMPORARILY_CLOSED,
        FacilityStatus.DECOMMISSIONED,
    },
    FacilityStatus.TEMPORARILY_CLOSED: {
        FacilityStatus.ACTIVE,
        FacilityStatus.UNDER_MAINTENANCE,
        FacilityStatus.DECOMMISSIONED,
    },
    FacilityStatus.DECOMMISSIONED: set(),
}


def validate_asset_status_transition(current: AssetStatus, target: AssetStatus) -> None:
    if current == target:
        return
    allowed = ALLOWED_ASSET_TRANSITIONS.get(current, set())
    if target not in allowed:
        raise InvalidStateTransitionError(current_status=current.value, target_status=target.value)


def validate_facility_status_transition(current: FacilityStatus, target: FacilityStatus) -> None:
    if current == target:
        return
    allowed = ALLOWED_FACILITY_TRANSITIONS.get(current, set())
    if target not in allowed:
        raise InvalidStateTransitionError(current_status=current.value, target_status=target.value)
