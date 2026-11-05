"""Phase 17 Event Participant Privacy Filter."""

from typing import Any
from uuid import UUID


class EventParticipantPrivacyFilter:
    """Masks individual participant identifiers for regular residents without explicit admin permissions."""

    @staticmethod
    def filter_participant_details(
        participants: list[dict[str, Any]],
        current_user_id: UUID,
        has_admin_permission: bool,
    ) -> list[dict[str, Any]]:
        """If user has admin permissions, return full participant details.

        Otherwise, return only the user's own registration detail or anonymized summary counts.
        """
        if has_admin_permission:
            return participants

        # Non-admin users only see their own entry
        filtered = []
        for p in participants:
            if p.get("user_id") == str(current_user_id) or p.get("user_id") == current_user_id:
                filtered.append(p)
            else:
                filtered.append(
                    {
                        "id": p.get("id"),
                        "event_id": p.get("event_id"),
                        "status": p.get("status"),
                        "registered_at": p.get("registered_at"),
                        "is_masked": True,
                    }
                )
        return filtered
