"""Tenant and User Request Context using contextvars for async task safety."""

import contextvars
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from uuid import UUID

_current_tenant_id: contextvars.ContextVar[UUID | None] = contextvars.ContextVar(
    "current_tenant_id", default=None
)
_current_user_id: contextvars.ContextVar[UUID | None] = contextvars.ContextVar(
    "current_user_id", default=None
)


def get_current_tenant_id() -> UUID | None:
    """Retrieve the active tenant society ID for the current async task context."""
    return _current_tenant_id.get()


def set_current_tenant_id(society_id: UUID | None) -> contextvars.Token[UUID | None]:
    """Set the active tenant society ID for the current async task context."""
    return _current_tenant_id.set(society_id)


def reset_current_tenant_id(token: contextvars.Token[UUID | None]) -> None:
    """Reset the tenant context to its previous state."""
    _current_tenant_id.reset(token)


def get_current_user_id() -> UUID | None:
    """Retrieve the authenticated user ID for the current async task context."""
    return _current_user_id.get()


def set_current_user_id(user_id: UUID | None) -> contextvars.Token[UUID | None]:
    """Set the authenticated user ID for the current async task context."""
    return _current_user_id.set(user_id)


def reset_current_user_id(token: contextvars.Token[UUID | None]) -> None:
    """Reset the user context to its previous state."""
    _current_user_id.reset(token)


@asynccontextmanager
async def tenant_context(society_id: UUID | None) -> AsyncGenerator[UUID | None, None]:
    """Context manager for safely executing a code block within a specific tenant context."""
    token = set_current_tenant_id(society_id)
    try:
        yield society_id
    finally:
        reset_current_tenant_id(token)
