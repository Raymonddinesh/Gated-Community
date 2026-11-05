"""Facility Booking Event Hooks for Notification Readiness."""

import logging
from typing import Any
from uuid import UUID

logger = logging.getLogger(__name__)


async def emit_booking_event(
    event_type: str,
    society_id: UUID,
    booking_id: UUID,
    facility_id: UUID | None = None,
    user_id: UUID | None = None,
    payload: dict[str, Any] | None = None,
) -> None:
    """Emit a decoupled event hook for booking lifecycle changes (notification readiness)."""
    logger.info(
        "FacilityBookingEvent emitted: type=%s, society_id=%s, booking_id=%s, facility_id=%s, user_id=%s",
        event_type,
        society_id,
        booking_id,
        facility_id,
        user_id,
    )


class FacilityBookingEventHooks:
    """Decoupled event hooks for facility booking lifecycle events."""

    @staticmethod
    def on_booking_created(
        booking_id: UUID,
        society_id: UUID,
        facility_id: UUID,
        user_id: UUID,
        booking_code: str,
        status: str,
    ) -> None:
        logger.info(
            "Booking created event: id=%s, code=%s, status=%s",
            booking_id,
            booking_code,
            status,
        )

    @staticmethod
    def on_booking_approved(
        booking_id: UUID,
        society_id: UUID,
        user_id: UUID,
        booking_code: str,
    ) -> None:
        logger.info("Booking approved event: id=%s, code=%s", booking_id, booking_code)

    @staticmethod
    def on_booking_rejected(
        booking_id: UUID,
        society_id: UUID,
        user_id: UUID,
        booking_code: str,
        reason: str | None = None,
    ) -> None:
        logger.info("Booking rejected event: id=%s, code=%s, reason=%s", booking_id, booking_code, reason)

    @staticmethod
    def on_booking_cancelled(
        booking_id: UUID,
        society_id: UUID,
        user_id: UUID,
        booking_code: str,
        reason: str | None = None,
    ) -> None:
        logger.info("Booking cancelled event: id=%s, code=%s, reason=%s", booking_id, booking_code, reason)

    @staticmethod
    def on_booking_checked_in(
        booking_id: UUID,
        society_id: UUID,
        booking_code: str,
    ) -> None:
        logger.info("Booking checked-in event: id=%s, code=%s", booking_id, booking_code)

    @staticmethod
    def on_booking_completed(
        booking_id: UUID,
        society_id: UUID,
        booking_code: str,
    ) -> None:
        logger.info("Booking completed event: id=%s, code=%s", booking_id, booking_code)

    @staticmethod
    def on_booking_no_show(
        booking_id: UUID,
        society_id: UUID,
        booking_code: str,
    ) -> None:
        logger.info("Booking no-show event: id=%s, code=%s", booking_id, booking_code)
