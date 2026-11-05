"""Server-side State Machine for Maintenance Work Order Status Lifecycle."""

from apps.api.src.maintenance.domain.enums import WorkOrderStatus
from apps.api.src.maintenance.domain.exceptions import InvalidWorkOrderTransitionError

VALID_WORK_ORDER_TRANSITIONS: dict[WorkOrderStatus, set[WorkOrderStatus]] = {
    WorkOrderStatus.DRAFT: {
        WorkOrderStatus.OPEN,
        WorkOrderStatus.CANCELLED,
    },
    WorkOrderStatus.OPEN: {
        WorkOrderStatus.ASSIGNED,
        WorkOrderStatus.SCHEDULED,
        WorkOrderStatus.IN_PROGRESS,
        WorkOrderStatus.CANCELLED,
    },
    WorkOrderStatus.ASSIGNED: {
        WorkOrderStatus.SCHEDULED,
        WorkOrderStatus.IN_PROGRESS,
        WorkOrderStatus.ON_HOLD,
        WorkOrderStatus.CANCELLED,
    },
    WorkOrderStatus.SCHEDULED: {
        WorkOrderStatus.IN_PROGRESS,
        WorkOrderStatus.ON_HOLD,
        WorkOrderStatus.CANCELLED,
    },
    WorkOrderStatus.IN_PROGRESS: {
        WorkOrderStatus.ON_HOLD,
        WorkOrderStatus.WAITING_FOR_PARTS,
        WorkOrderStatus.WAITING_FOR_RESIDENT,
        WorkOrderStatus.COMPLETED,
        WorkOrderStatus.VERIFIED,
        WorkOrderStatus.CANCELLED,
    },
    WorkOrderStatus.ON_HOLD: {
        WorkOrderStatus.IN_PROGRESS,
        WorkOrderStatus.CANCELLED,
    },
    WorkOrderStatus.WAITING_FOR_PARTS: {
        WorkOrderStatus.IN_PROGRESS,
        WorkOrderStatus.CANCELLED,
    },
    WorkOrderStatus.WAITING_FOR_RESIDENT: {
        WorkOrderStatus.IN_PROGRESS,
        WorkOrderStatus.CANCELLED,
    },
    WorkOrderStatus.COMPLETED: {
        WorkOrderStatus.VERIFIED,
        WorkOrderStatus.CLOSED,
        WorkOrderStatus.REOPENED,
    },
    WorkOrderStatus.VERIFIED: {
        WorkOrderStatus.CLOSED,
        WorkOrderStatus.REOPENED,
    },
    WorkOrderStatus.CLOSED: {
        WorkOrderStatus.REOPENED,
    },
    WorkOrderStatus.REOPENED: {
        WorkOrderStatus.ASSIGNED,
        WorkOrderStatus.IN_PROGRESS,
    },
    WorkOrderStatus.CANCELLED: set(),  # Terminal state
}


def validate_status_transition(
    current_status: WorkOrderStatus | str, target_status: WorkOrderStatus | str
) -> None:
    """Validate whether transitioning from current_status to target_status is permitted."""
    current_enum = WorkOrderStatus(current_status)
    target_enum = WorkOrderStatus(target_status)

    if current_enum == target_enum:
        return

    allowed_targets = VALID_WORK_ORDER_TRANSITIONS.get(current_enum, set())
    if target_enum not in allowed_targets:
        raise InvalidWorkOrderTransitionError(
            current_status=current_enum.value, target_status=target_enum.value
        )
