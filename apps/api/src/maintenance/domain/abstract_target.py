"""Abstract Assignment Target Interface and Integration Boundaries for Future Phase(s).

This module defines the architectural boundary for future Staff Management (Phase 12+)
and Vendor Management (Phase 13+) integrations without creating incomplete tables.
"""

import uuid
from abc import ABC, abstractmethod

from apps.api.src.maintenance.domain.enums import WorkOrderAssignmentType


class MaintenanceAssignmentTarget(ABC):
    """Conceptual interface for work order assignment targets."""

    @property
    @abstractmethod
    def target_id(self) -> uuid.UUID:
        """Unique identifier of the target (User ID, Staff ID, Team ID, or Vendor ID)."""
        pass

    @property
    @abstractmethod
    def target_type(self) -> WorkOrderAssignmentType:
        """Assignment type classification."""
        pass

    @property
    @abstractmethod
    def display_name(self) -> str:
        """Human-readable target name."""
        pass


class InternalUserAssignmentTarget(MaintenanceAssignmentTarget):
    """Phase 11 internal platform user / role assignment target implementation."""

    def __init__(self, user_id: uuid.UUID, user_name: str):
        self._user_id = user_id
        self._user_name = user_name

    @property
    def target_id(self) -> uuid.UUID:
        return self._user_id

    @property
    def target_type(self) -> WorkOrderAssignmentType:
        return WorkOrderAssignmentType.INTERNAL_USER

    @property
    def display_name(self) -> str:
        return self._user_name


class StaffAssignmentTargetPlaceholder(MaintenanceAssignmentTarget):
    """Future Staff Management integration adapter (Phase 12+)."""

    def __init__(self, staff_id: uuid.UUID, staff_name: str):
        self._staff_id = staff_id
        self._staff_name = staff_name

    @property
    def target_id(self) -> uuid.UUID:
        return self._staff_id

    @property
    def target_type(self) -> WorkOrderAssignmentType:
        return WorkOrderAssignmentType.STAFF

    @property
    def display_name(self) -> str:
        return f"[Staff Placeholder] {self._staff_name}"


class VendorAssignmentTargetPlaceholder(MaintenanceAssignmentTarget):
    """Future Vendor Management integration adapter (Phase 13+)."""

    def __init__(self, vendor_id: uuid.UUID, vendor_name: str):
        self._vendor_id = vendor_id
        self._vendor_name = vendor_name

    @property
    def target_id(self) -> uuid.UUID:
        return self._vendor_id

    @property
    def target_type(self) -> WorkOrderAssignmentType:
        return WorkOrderAssignmentType.VENDOR

    @property
    def display_name(self) -> str:
        return f"[Vendor Placeholder] {self._vendor_name}"
