"""Concurrency and synchronization primitives for unit-level operations."""

import asyncio
from collections import defaultdict
from uuid import UUID

_unit_locks: dict[UUID, asyncio.Lock] = defaultdict(asyncio.Lock)


def get_unit_lock(unit_id: UUID) -> asyncio.Lock:
    """
    Retrieve an asyncio.Lock bound to a specific Unit ID.
    Provides in-process serialization for concurrent operations on the same unit
    (e.g., simultaneous ownership allocations or tenant move-ins) in addition to
    PostgreSQL row-level locks (SELECT ... FOR UPDATE).
    """
    return _unit_locks[unit_id]
