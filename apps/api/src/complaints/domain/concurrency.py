"""Concurrency protection primitives for Complaints Domain."""

import asyncio
import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

_complaint_locks: dict[uuid.UUID, asyncio.Lock] = {}
_complaint_number_locks: dict[uuid.UUID, asyncio.Lock] = {}
_global_lock = asyncio.Lock()


@asynccontextmanager
async def get_complaint_lock(complaint_id: uuid.UUID) -> AsyncGenerator[None, None]:
    """In-memory concurrency lock per complaint entity to prevent race conditions."""
    async with _global_lock:
        if complaint_id not in _complaint_locks:
            _complaint_locks[complaint_id] = asyncio.Lock()
        lock = _complaint_locks[complaint_id]

    async with lock:
        try:
            yield
        finally:
            pass


@asynccontextmanager
async def get_complaint_number_lock(society_id: uuid.UUID) -> AsyncGenerator[None, None]:
    """In-memory concurrency lock for complaint number generation per society."""
    async with _global_lock:
        if society_id not in _complaint_number_locks:
            _complaint_number_locks[society_id] = asyncio.Lock()
        lock = _complaint_number_locks[society_id]

    async with lock:
        try:
            yield
        finally:
            pass
