"""Phase 20 Notification Preference Service with Emergency Override."""

import uuid
from datetime import datetime, time

from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.database.models.notifications import (
    NotificationChannelPreference,
    NotificationPreference,
)
from apps.api.src.notifications.enums import PriorityLevel
from apps.api.src.notifications.repositories import PreferenceRepository


class PreferenceService:
    """Service for Category Preferences, Channel Preferences, and Quiet Hours."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = PreferenceRepository(db)

    async def is_notification_allowed(
        self,
        society_id: uuid.UUID,
        user_id: uuid.UUID,
        category: str,
        priority: str,
        channel: str,
        current_dt: datetime | None = None,
    ) -> bool:
        """Evaluate if notification is permitted.

        CRITICAL priority (Phase 19 Emergency) BYPASSES all user preferences & quiet hours.
        """
        if priority == PriorityLevel.CRITICAL.value:
            return True

        # Check Category Preference
        pref = await self.repo.get_preference(society_id, user_id, category)
        if pref and not pref.is_enabled:
            return False

        # Check Quiet Hours if enabled
        if pref and pref.quiet_hours_enabled and pref.quiet_hours_start and pref.quiet_hours_end:
            now = (current_dt or datetime.now()).time()
            if self._is_in_quiet_hours(now, pref.quiet_hours_start, pref.quiet_hours_end):
                return False

        # Check Channel Opt-In Preference
        channel_pref = await self.repo.get_channel_preference(
            society_id, user_id, category, channel
        )
        if channel_pref and not channel_pref.is_enabled:
            return False

        return True

    def _is_in_quiet_hours(self, now: time, start_str: str, end_str: str) -> bool:
        """Parse HH:MM quiet hours start/end and test if current time falls within window."""
        try:
            start_parts = [int(x) for x in start_str.split(":")]
            end_parts = [int(x) for x in end_str.split(":")]
            start_time = time(start_parts[0], start_parts[1])
            end_time = time(end_parts[0], end_parts[1])

            if start_time <= end_time:
                return start_time <= now <= end_time
            else:
                # Overnight quiet hours e.g. 22:00 to 07:00
                return now >= start_time or now <= end_time
        except (ValueError, IndexError):
            return False

    async def update_category_preference(
        self,
        society_id: uuid.UUID,
        user_id: uuid.UUID,
        category: str,
        is_enabled: bool,
        quiet_hours_enabled: bool = False,
        quiet_hours_start: str | None = None,
        quiet_hours_end: str | None = None,
    ) -> NotificationPreference:
        return await self.repo.set_preference(
            society_id,
            user_id,
            category,
            is_enabled,
            quiet_hours_enabled,
            quiet_hours_start,
            quiet_hours_end,
        )

    async def update_channel_preference(
        self,
        society_id: uuid.UUID,
        user_id: uuid.UUID,
        category: str,
        channel: str,
        is_enabled: bool,
    ) -> NotificationChannelPreference:
        return await self.repo.set_channel_preference(
            society_id, user_id, category, channel, is_enabled
        )
