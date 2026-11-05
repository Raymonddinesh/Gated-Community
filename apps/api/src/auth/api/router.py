"""Authentication and Identity Session Management API Endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.auth.dependencies import (
    get_current_session,
    get_current_user,
)
from apps.api.src.auth.schemas import (
    GenericActionResponse,
    LoginRequest,
    LoginResponse,
    PasswordResetConfirmRequest,
    PasswordResetRequest,
    PasswordResetResponse,
    RefreshTokenRequest,
    RefreshTokenResponse,
    SocietyOption,
    SocietySwitchResponse,
    UserMeResponse,
    UserSummary,
)
from apps.api.src.auth.services.auth_service import AuthService
from apps.api.src.database.models.identity import User
from apps.api.src.database.models.session import UserSession
from apps.api.src.database.repositories.authorization_repository import AuthorizationRepository
from apps.api.src.database.repositories.user_repository import UserRepository
from apps.api.src.database.session import get_db_session

router = APIRouter(prefix="/auth", tags=["Authentication & Sessions"])


def _extract_client_ip(request: Request) -> str:
    """Extract true client IP address honoring X-Forwarded-For if behind reverse proxy."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


@router.post("/login", response_model=LoginResponse)
async def login(
    req: LoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db_session),
) -> LoginResponse:
    """Authenticate user with identifier (email/phone) and password."""
    service = AuthService(db)
    client_ip = _extract_client_ip(request)
    user_agent = request.headers.get("User-Agent")
    correlation_id = getattr(request.state, "correlation_id", None)

    return await service.login(
        identifier=req.identifier,
        password=req.password,
        ip_address=client_ip,
        user_agent=user_agent,
        correlation_id=correlation_id,
    )


@router.post("/refresh", response_model=RefreshTokenResponse)
async def refresh_token(
    req: RefreshTokenRequest,
    request: Request,
    db: AsyncSession = Depends(get_db_session),
) -> RefreshTokenResponse:
    """Rotate refresh token and issue a fresh JWT access token."""
    service = AuthService(db)
    client_ip = _extract_client_ip(request)
    user_agent = request.headers.get("User-Agent")
    correlation_id = getattr(request.state, "correlation_id", None)

    return await service.refresh_tokens(
        refresh_token=req.refresh_token,
        ip_address=client_ip,
        user_agent=user_agent,
        correlation_id=correlation_id,
    )


@router.post("/logout", response_model=GenericActionResponse)
async def logout(
    request: Request,
    current_session: UserSession = Depends(get_current_session),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> GenericActionResponse:
    """Terminate the current user session and revoke its refresh token."""
    service = AuthService(db)
    correlation_id = getattr(request.state, "correlation_id", None)
    return await service.logout(
        session_id=current_session.id,
        user_id=current_user.id,
        correlation_id=correlation_id,
    )


@router.post("/logout-all", response_model=GenericActionResponse)
async def logout_all(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> GenericActionResponse:
    """Terminate all active sessions across all devices for this user."""
    service = AuthService(db)
    correlation_id = getattr(request.state, "correlation_id", None)
    return await service.logout_all(
        user_id=current_user.id,
        correlation_id=correlation_id,
    )


@router.post("/password-reset/request", response_model=PasswordResetResponse)
async def request_password_reset(
    req: PasswordResetRequest,
    request: Request,
    db: AsyncSession = Depends(get_db_session),
) -> PasswordResetResponse:
    """Request a single-use password reset link/token."""
    service = AuthService(db)
    correlation_id = getattr(request.state, "correlation_id", None)
    return await service.request_password_reset(
        identifier=req.identifier,
        correlation_id=correlation_id,
    )


@router.post("/password-reset/confirm", response_model=GenericActionResponse)
async def confirm_password_reset(
    req: PasswordResetConfirmRequest,
    request: Request,
    db: AsyncSession = Depends(get_db_session),
) -> GenericActionResponse:
    """Set a new password using a valid single-use reset token and terminate all sessions."""
    service = AuthService(db)
    correlation_id = getattr(request.state, "correlation_id", None)
    return await service.confirm_password_reset(
        token=req.token,
        new_password=req.new_password,
        correlation_id=correlation_id,
    )


@router.post("/societies/{society_id}/switch", response_model=SocietySwitchResponse)
async def switch_society(
    society_id: UUID,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> SocietySwitchResponse:
    """Verify tenant membership and switch active society context."""
    service = AuthService(db)
    correlation_id = getattr(request.state, "correlation_id", None)
    return await service.switch_society(
        user_id=current_user.id,
        target_society_id=society_id,
        correlation_id=correlation_id,
    )


@router.get("/me", response_model=UserMeResponse)
async def get_current_user_profile(
    x_society_id: UUID | None = Header(None, alias="X-Society-ID"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> UserMeResponse:
    """Retrieve authenticated user details and active society role/permission resolution."""
    user_repo = UserRepository(db)
    authz_repo = AuthorizationRepository(db)

    societies = await user_repo.get_user_societies(current_user.id)
    society_options = [
        SocietyOption(id=s.id, legal_name=s.legal_name, display_name=s.display_name) for s in societies
    ]

    active_society_id: UUID | None = None
    if x_society_id and any(s.id == x_society_id for s in societies):
        active_society_id = x_society_id
    elif len(societies) == 1:
        active_society_id = societies[0].id

    roles = await authz_repo.get_user_roles(current_user.id, active_society_id)
    permissions = await authz_repo.get_user_permission_codes(current_user.id, active_society_id)

    return UserMeResponse(
        user=UserSummary(
            id=current_user.id,
            email=current_user.email,
            phone=current_user.phone,
            first_name=current_user.first_name,
            last_name=current_user.last_name,
            display_name=current_user.display_name,
            status=current_user.status,
        ),
        memberships=society_options,
        active_society_id=active_society_id,
        active_roles=[r.code for r in roles],
        active_permissions=permissions,
    )
