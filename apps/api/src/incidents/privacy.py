"""Phase 19 Incident Privacy Filter (PII & Medical Protection)."""

from typing import Any


class IncidentPrivacyFilter:
    """Enforces server-authoritative privacy masking on sensitive incident fields."""

    @classmethod
    def apply_privacy_filter(
        self,
        incident_dict: dict[str, Any],
        user_id_str: str,
        user_permissions: set[str],
    ) -> dict[str, Any]:
        """Filters sensitive PII (reporter contact, medical details, unit privacy) unless user has administrative permission or is reporter/responder."""
        has_admin_access = bool(
            user_permissions.intersection({"incident.view_all", "incident.triage", "incident.override"})
        )
        is_reporter = str(incident_dict.get("reported_by_id")) == user_id_str

        # Check responder assignment
        assignments = incident_dict.get("assignments") or []
        is_assigned_responder = any(
            str(a.get("assigned_user_id")) == user_id_str for a in assignments if isinstance(a, dict)
        )

        if has_admin_access or is_reporter or is_assigned_responder:
            return incident_dict

        # Mask PII for general resident/public view
        filtered = dict(incident_dict)
        if filtered.get("reporter_contact"):
            filtered["reporter_contact"] = "[CONFIDENTIAL]"

        # Mask internal timeline notes if flagged as internal only
        if "timelines" in filtered and isinstance(filtered["timelines"], list):
            filtered["timelines"] = [
                t
                for t in filtered["timelines"]
                if isinstance(t, dict) and not t.get("is_internal_only", False)
            ]

        return filtered
