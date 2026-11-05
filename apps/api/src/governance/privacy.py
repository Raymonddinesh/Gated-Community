"""Phase 18 Governance Privacy Filter."""

from typing import Any
from uuid import UUID


class GovernancePrivacyFilter:
    """Masks individual voting choices and internal committee discussions for non-admin residents."""

    @staticmethod
    def filter_votes(
        votes: list[dict[str, Any]], current_user_id: UUID, has_admin_perm: bool
    ) -> list[dict[str, Any]]:
        """Non-admin users only see their own vote choice or aggregate counts."""
        if has_admin_perm:
            return votes

        filtered = []
        for v in votes:
            if v.get("user_id") == str(current_user_id) or v.get("user_id") == current_user_id:
                filtered.append(v)
            else:
                filtered.append(
                    {
                        "id": v.get("id"),
                        "resolution_id": v.get("resolution_id"),
                        "voted_at": v.get("voted_at"),
                        "is_masked": True,
                    }
                )
        return filtered

    @staticmethod
    def filter_meeting_notes(meeting_dict: dict[str, Any], has_admin_perm: bool) -> dict[str, Any]:
        """Sanitizes internal committee notes for public resident view."""
        if not has_admin_perm and "internal_notes" in meeting_dict:
            meeting_dict["internal_notes"] = "[RESTRICTED TO COMMITTEE MEMBERS]"
        return meeting_dict
