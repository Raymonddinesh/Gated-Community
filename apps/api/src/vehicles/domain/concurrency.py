"""Concurrency and synchronization primitives for vehicle operations."""

import asyncio
from collections import defaultdict
from uuid import UUID

_vehicle_locks: dict[UUID, asyncio.Lock] = defaultdict(asyncio.Lock)
_registration_locks: dict[tuple[UUID, str], asyncio.Lock] = defaultdict(asyncio.Lock)


def get_vehicle_lock(vehicle_id: UUID) -> asyncio.Lock:
    """
    Retrieve an asyncio.Lock bound to a specific Vehicle ID.
    Provides in-process serialization for concurrent operations on the same vehicle
    (e.g., simultaneous verifications or association changes).
    """
    return _vehicle_locks[vehicle_id]


def get_registration_lock(society_id: UUID, normalized_reg: str) -> asyncio.Lock:
    """
    Retrieve an asyncio.Lock bound to (society_id, normalized_registration_number).
    Guarantees deterministic in-process synchronization against concurrent vehicle
    registration races with the same plate number.
    """
    return _registration_locks[(society_id, normalized_reg)]
