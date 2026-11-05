"""Concurrency and synchronization primitives for visitor operations."""

import asyncio
from collections import defaultdict
from uuid import UUID

_visitor_locks: dict[UUID, asyncio.Lock] = defaultdict(asyncio.Lock)
_invitation_locks: dict[UUID, asyncio.Lock] = defaultdict(asyncio.Lock)
_visitor_entry_locks: dict[tuple[UUID, UUID, UUID], asyncio.Lock] = defaultdict(asyncio.Lock)


def get_visitor_lock(visitor_id: UUID) -> asyncio.Lock:
    """Retrieve an asyncio.Lock bound to a specific Visitor ID."""
    return _visitor_locks[visitor_id]


def get_invitation_lock(invitation_id: UUID) -> asyncio.Lock:
    """Retrieve an asyncio.Lock bound to a specific Visitor Invitation ID."""
    return _invitation_locks[invitation_id]


def get_visitor_entry_lock(society_id: UUID, unit_id: UUID, visitor_id: UUID) -> asyncio.Lock:
    """
    Retrieve an asyncio.Lock bound to (society_id, unit_id, visitor_id).
    Guarantees in-process synchronization against concurrent entry races for the same visitor & unit.
    """
    return _visitor_entry_locks[(society_id, unit_id, visitor_id)]
