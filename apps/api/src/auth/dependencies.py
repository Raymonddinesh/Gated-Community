"""FastAPI Authentication and RBAC Authorization Dependencies."""

from collections.abc import Callable
from typing import Any
from uuid import UUID

from fastapi import Depends, Header, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.auth.repositories.session_repository import SessionRepository
from apps.api.src.auth.security.tokens import decode_access_token
from apps.api.src.core.exceptions import (
    AuthenticationException,
    AuthorizationException,
    TenantContextMismatchException,
)
from apps.api.src.core.tenant_context import set_current_tenant_id, set_current_user_id
from apps.api.src.database.models.identity import User
from apps.api.src.database.models.session import UserSession
from apps.api.src.database.repositories.authorization_repository import AuthorizationRepository
from apps.api.src.database.repositories.membership_repository import MembershipRepository
from apps.api.src.database.repositories.user_repository import UserRepository
from apps.api.src.database.session import get_db_session, set_db_tenant_context

http_bearer = HTTPBearer(auto_error=False)


async def get_current_session(
    credentials: HTTPAuthorizationCredentials | None = Depends(http_bearer),
    db: AsyncSession = Depends(get_db_session),
) -> UserSession:
    """Validate access token and verify that the session has not been revoked."""
    if not credentials:
        raise AuthenticationException(
            "Authentication required. Missing Bearer token.",
            details={"code": "MISSING_CREDENTIALS"},
        )

    token = credentials.credentials
    payload = decode_access_token(token)

    try:
        session_id = UUID(payload["sid"])
    except (KeyError, ValueError):
        raise AuthenticationException("Invalid session identifier in access token.")

    session_repo = SessionRepository(db)
    session = await session_repo.get_session_by_id(session_id)

    if not session or session.is_revoked:
        raise AuthenticationException(
            "Session is invalid or has been revoked. Please log in again.",
            details={"code": "SESSION_REVOKED"},
        )

    return session


async def get_current_user(
    session: UserSession = Depends(get_current_session),
    db: AsyncSession = Depends(get_db_session),
) -> User:
    """Retrieve authenticated user associated with the verified session."""
    user_repo = UserRepository(db)
    user = await user_repo.get_by_id(session.user_id)

    if not user or user.status != "ACTIVE":
        raise AuthenticationException(
            "User account is inactive or disabled.",
            details={"code": "ACCOUNT_INACTIVE"},
        )

    # Bind user ID to request context
    set_current_user_id(user.id)
    return user


async def resolve_society_context(
    request: Request,
    x_society_id: UUID | None = Header(None, alias="X-Society-ID"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> UUID | None:
    """
    Resolve and validate tenant society context.
    Strictly verifies that header hints and URL parameters do not contradict each other,
    and guarantees the user is an active member of the resolved society.
    Configures PostgreSQL RLS context when applicable.
    """
    path_soc_raw = request.path_params.get("society_id")
    society_id: UUID | None = None
    if path_soc_raw:
        try:
            society_id = UUID(str(path_soc_raw))
        except (ValueError, TypeError):
            society_id = None

    # Check if URL parameter and header conflict
    target_society_id = society_id or x_society_id

    if society_id is not None and x_society_id is not None and society_id != x_society_id:
        raise TenantContextMismatchException(
            f"Tenant context mismatch: URL society '{society_id}' does not match header hint '{x_society_id}'."
        )

    if target_society_id is not None:
        membership_repo = MembershipRepository(db)
        is_member = await membership_repo.verify_user_society_membership(current_user.id, target_society_id)

        # Allow platform SUPER_ADMIN bypass if assigned
        if not is_member:
            authz_repo = AuthorizationRepository(db)
            roles = await authz_repo.get_user_roles(current_user.id, None)
            is_super_admin = any(r.code == "SUPER_ADMIN" for r in roles)
            if not is_super_admin:
                raise AuthorizationException(
                    "Access denied: You are not an active member of this society.",
                    details={"society_id": str(target_society_id)},
                )

        # Configure session RLS and context
        set_current_tenant_id(target_society_id)
        await set_db_tenant_context(db, target_society_id)

    return target_society_id


def require_permission(permission_code: str) -> Callable[..., Any]:
    """Factory creating a FastAPI dependency that verifies the user possesses a specific permission."""

    async def _permission_dependency(
        current_user: User = Depends(get_current_user),
        society_id: UUID | None = Depends(resolve_society_context),
        db: AsyncSession = Depends(get_db_session),
    ) -> User:
        authz_repo = AuthorizationRepository(db)
        roles = await authz_repo.get_user_roles(current_user.id, society_id)

        # SUPER_ADMIN inherits full authority
        if any(r.code == "SUPER_ADMIN" for r in roles):
            return current_user

        permissions = await authz_repo.get_user_permission_codes(current_user.id, society_id)
        if permission_code not in permissions:
            raise AuthorizationException(
                f"Forbidden: You lack the required permission '{permission_code}'.",
                details={"required_permission": permission_code},
            )
        return current_user

    return _permission_dependency


def require_role(role_code: str) -> Callable[..., Any]:
    """Factory creating a FastAPI dependency that verifies the user holds a specific role."""

    async def _role_dependency(
        current_user: User = Depends(get_current_user),
        society_id: UUID | None = Depends(resolve_society_context),
        db: AsyncSession = Depends(get_db_session),
    ) -> User:
        authz_repo = AuthorizationRepository(db)
        roles = await authz_repo.get_user_roles(current_user.id, society_id)
        role_codes = {r.code for r in roles}

        if "SUPER_ADMIN" in role_codes or role_code in role_codes:
            return current_user

        raise AuthorizationException(
            f"Forbidden: You do not possess the required role '{role_code}'.",
            details={"required_role": role_code},
        )

    return _role_dependency
