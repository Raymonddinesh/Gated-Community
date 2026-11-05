"""Authentication, Session Lifecycle, and RBAC Resolution Service."""

import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.auth.repositories.session_repository import SessionRepository
from apps.api.src.auth.schemas import (
    GenericActionResponse,
    LoginResponse,
    PasswordResetResponse,
    RefreshTokenResponse,
    SocietyOption,
    SocietySwitchResponse,
    UserSummary,
)
from apps.api.src.auth.security.password import (
    hash_password,
    validate_password_policy,
    verify_dummy_password,
    verify_password,
)
from apps.api.src.auth.security.rate_limiter import check_rate_limit
from apps.api.src.auth.security.tokens import (
    create_access_token,
    generate_opaque_token,
    hash_token,
)
from apps.api.src.core.config import get_settings
from apps.api.src.core.exceptions import (
    AppException,
    AuthenticationException,
    AuthorizationException,
    NotFoundException,
)
from apps.api.src.database.repositories.audit_repository import AuditRepository
from apps.api.src.database.repositories.authorization_repository import AuthorizationRepository
from apps.api.src.database.repositories.membership_repository import MembershipRepository
from apps.api.src.database.repositories.society_repository import SocietyRepository
from apps.api.src.database.repositories.user_repository import UserRepository

logger = logging.getLogger("societysphere.auth.service")


class AuthService:
    """Core domain service orchestrating authentication, sessions, and credential management."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.user_repo = UserRepository(db)
        self.session_repo = SessionRepository(db)
        self.society_repo = SocietyRepository(db)
        self.membership_repo = MembershipRepository(db)
        self.authz_repo = AuthorizationRepository(db)
        self.audit_repo = AuditRepository(db)

    async def login(
        self,
        identifier: str,
        password: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
        correlation_id: str | None = None,
    ) -> LoginResponse:
        """
        Authenticate user credentials, rotate sessions, and generate access tokens.
        Defends against timing attacks, brute-force attempts, and user enumeration.
        """
        settings = get_settings()

        # Enforce rate limiting per client IP
        rate_key = f"login:{ip_address or 'global'}"
        await check_rate_limit(
            rate_key,
            max_requests=settings.AUTH_LOGIN_RATE_LIMIT_PER_MINUTE,
            window_seconds=60,
        )

        user = await self.user_repo.get_by_identifier(identifier)
        if not user:
            # Constant-time dummy verification prevents response timing enumeration
            verify_dummy_password()
            await self.audit_repo.log_event(
                action="AUTH_LOGIN_FAILED",
                entity_type="user",
                entity_id=identifier,
                actor_user_id=None,
                correlation_id=correlation_id,
                after_state={"reason": "USER_NOT_FOUND"},
            )
            raise AuthenticationException("Invalid username or password.")

        if user.status != "ACTIVE":
            verify_dummy_password()
            await self.audit_repo.log_event(
                action="AUTH_LOGIN_FAILED",
                entity_type="user",
                entity_id=str(user.id),
                actor_user_id=user.id,
                correlation_id=correlation_id,
                after_state={"reason": "ACCOUNT_INACTIVE"},
            )
            raise AuthenticationException("Account is inactive or suspended. Please contact administrator.")

        if not verify_password(password, user.password_hash):
            await self.audit_repo.log_event(
                action="AUTH_LOGIN_FAILED",
                entity_type="user",
                entity_id=str(user.id),
                actor_user_id=user.id,
                correlation_id=correlation_id,
                after_state={"reason": "INVALID_PASSWORD"},
            )
            raise AuthenticationException("Invalid username or password.")

        # Update last login
        await self.user_repo.update_last_login(user.id)

        # Issue rotating refresh token
        raw_refresh_token = generate_opaque_token()
        refresh_hash = hash_token(raw_refresh_token)
        refresh_expires = datetime.now(UTC) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

        session_obj = await self.session_repo.create_session(
            user_id=user.id,
            refresh_token_hash=refresh_hash,
            expires_at=refresh_expires,
            user_agent=user_agent,
            ip_address=ip_address,
        )

        # Issue short-lived access token
        access_token = create_access_token(user_id=user.id, session_id=session_obj.id)

        # Retrieve user societies
        societies = await self.user_repo.get_user_societies(user.id)
        society_options = [
            SocietyOption(id=s.id, legal_name=s.legal_name, display_name=s.display_name) for s in societies
        ]

        # If user is in exactly one society, auto-select it; otherwise leave active_society_id None
        active_society_id = societies[0].id if len(societies) == 1 else None

        await self.audit_repo.log_event(
            action="AUTH_LOGIN_SUCCESS",
            entity_type="session",
            entity_id=str(session_obj.id),
            actor_user_id=user.id,
            correlation_id=correlation_id,
            after_state={"ip_address": ip_address, "user_agent": user_agent[:100] if user_agent else None},
        )

        return LoginResponse(
            access_token=access_token,
            token_type="bearer",
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            refresh_token=raw_refresh_token,
            user=UserSummary(
                id=user.id,
                email=user.email,
                phone=user.phone,
                first_name=user.first_name,
                last_name=user.last_name,
                display_name=user.display_name,
                status=user.status,
            ),
            active_society_id=active_society_id,
            available_societies=society_options,
        )

    async def refresh_tokens(
        self,
        refresh_token: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
        correlation_id: str | None = None,
    ) -> RefreshTokenResponse:
        """
        Rotate refresh token and issue a fresh access token.
        Detects token replay attacks: if a revoked/previously rotated token is presented,
        the entire token family is revoked immediately.
        """
        settings = get_settings()

        rate_key = f"refresh:{ip_address or 'global'}"
        await check_rate_limit(
            rate_key,
            max_requests=settings.AUTH_REFRESH_RATE_LIMIT_PER_MINUTE,
            window_seconds=60,
        )

        token_hash = hash_token(refresh_token)
        existing_session = await self.session_repo.get_session_by_token_hash(token_hash)

        if not existing_session:
            raise AuthenticationException(
                "Invalid refresh token.",
                details={"code": "INVALID_REFRESH_TOKEN"},
            )

        # REPLAY ATTACK DETECTION
        if existing_session.is_revoked:
            logger.warning(
                f"Refresh token replay attack detected for family {existing_session.family_id}, "
                f"user {existing_session.user_id} from IP {ip_address}"
            )
            # Neutralize attack: Revoke ALL sessions sharing this family
            revoked_count = await self.session_repo.revoke_session_family(
                existing_session.family_id,
                reason="REPLAY_DETECTED",
            )

            await self.audit_repo.log_event(
                action="AUTH_REFRESH_REPLAY_DETECTED",
                entity_type="session_family",
                entity_id=str(existing_session.family_id),
                actor_user_id=existing_session.user_id,
                correlation_id=correlation_id,
                after_state={
                    "revoked_count": revoked_count,
                    "attempted_session_id": str(existing_session.id),
                    "ip_address": ip_address,
                },
            )

            raise AuthenticationException(
                "Token reuse detected. All sessions in this chain have been revoked for your security.",
                details={"code": "TOKEN_REPLAY_DETECTED"},
            )

        # Check expiration
        now = datetime.now(UTC)
        if existing_session.expires_at.tzinfo is None:
            # Handle naive datetime from SQLite in tests
            session_expires = existing_session.expires_at.replace(tzinfo=UTC)
        else:
            session_expires = existing_session.expires_at

        if session_expires < now:
            await self.session_repo.revoke_session(existing_session.id, reason="EXPIRED")
            raise AuthenticationException(
                "Refresh token has expired. Please log in again.",
                details={"code": "TOKEN_EXPIRED"},
            )

        # Check user account status
        user = await self.user_repo.get_by_id(existing_session.user_id)
        if not user or user.status != "ACTIVE":
            await self.session_repo.revoke_session_family(
                existing_session.family_id, reason="ACCOUNT_INACTIVE"
            )
            raise AuthenticationException("User account is inactive or disabled.")

        # Rotate token: revoke current token
        await self.session_repo.revoke_session(existing_session.id, reason="ROTATED")

        # Generate new child token in the SAME family
        new_raw_token = generate_opaque_token()
        new_token_hash = hash_token(new_raw_token)
        new_expires = now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

        new_session = await self.session_repo.create_session(
            user_id=existing_session.user_id,
            refresh_token_hash=new_token_hash,
            expires_at=new_expires,
            family_id=existing_session.family_id,
            user_agent=user_agent,
            ip_address=ip_address,
        )

        new_access_token = create_access_token(user_id=user.id, session_id=new_session.id)

        await self.audit_repo.log_event(
            action="AUTH_REFRESH_SUCCESS",
            entity_type="session",
            entity_id=str(new_session.id),
            actor_user_id=user.id,
            correlation_id=correlation_id,
            after_state={"family_id": str(existing_session.family_id)},
        )

        return RefreshTokenResponse(
            access_token=new_access_token,
            token_type="bearer",
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            refresh_token=new_raw_token,
        )

    async def logout(
        self,
        session_id: UUID,
        user_id: UUID,
        correlation_id: str | None = None,
    ) -> GenericActionResponse:
        """Revoke a single active session."""
        await self.session_repo.revoke_session(session_id, reason="USER_LOGOUT")
        await self.audit_repo.log_event(
            action="AUTH_LOGOUT",
            entity_type="session",
            entity_id=str(session_id),
            actor_user_id=user_id,
            correlation_id=correlation_id,
        )
        return GenericActionResponse(message="Successfully logged out.")

    async def logout_all(
        self,
        user_id: UUID,
        correlation_id: str | None = None,
    ) -> GenericActionResponse:
        """Revoke all active sessions across all devices for this user."""
        count = await self.session_repo.revoke_all_user_sessions(user_id, reason="LOGOUT_ALL_DEVICES")
        await self.audit_repo.log_event(
            action="AUTH_LOGOUT_ALL",
            entity_type="user",
            entity_id=str(user_id),
            actor_user_id=user_id,
            correlation_id=correlation_id,
            after_state={"revoked_sessions": count},
        )
        return GenericActionResponse(message=f"Successfully terminated {count} active session(s).")

    async def request_password_reset(
        self,
        identifier: str,
        correlation_id: str | None = None,
    ) -> PasswordResetResponse:
        """
        Generate a single-use high-entropy password reset token.
        Never reveals whether an account exists to prevent user enumeration.
        """
        settings = get_settings()

        user = await self.user_repo.get_by_identifier(identifier)
        if not user or user.status != "ACTIVE":
            return PasswordResetResponse(
                message="If an account matches this identifier, password reset instructions have been sent."
            )

        raw_token = generate_opaque_token()
        token_hash = hash_token(raw_token)
        expires_at = datetime.now(UTC) + timedelta(minutes=settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES)

        await self.session_repo.create_password_reset_token(
            user_id=user.id,
            token_hash=token_hash,
            expires_at=expires_at,
        )

        await self.audit_repo.log_event(
            action="PASSWORD_RESET_REQUESTED",
            entity_type="user",
            entity_id=str(user.id),
            actor_user_id=user.id,
            correlation_id=correlation_id,
        )

        # In non-production environments (test/development), expose token for automated verification
        debug_token = raw_token if settings.APP_ENV.value in ("development", "testing") else None

        return PasswordResetResponse(
            message="If an account matches this identifier, password reset instructions have been sent.",
            reset_token=debug_token,
        )

    async def confirm_password_reset(
        self,
        token: str,
        new_password: str,
        correlation_id: str | None = None,
    ) -> GenericActionResponse:
        """
        Consume single-use password reset token, update password hash,
        and revoke all existing user sessions across all devices.
        """
        validate_password_policy(new_password)

        token_hash = hash_token(token)
        reset_token = await self.session_repo.get_reset_token_by_hash(token_hash)

        now = datetime.now(UTC)
        if not reset_token or reset_token.is_used:
            raise AppException(
                code="INVALID_RESET_TOKEN",
                message="Password reset token is invalid or has already been used.",
                status_code=400,
            )

        token_expires = (
            reset_token.expires_at.replace(tzinfo=UTC)
            if reset_token.expires_at.tzinfo is None
            else reset_token.expires_at
        )

        if token_expires < now:
            raise AppException(
                code="EXPIRED_RESET_TOKEN",
                message="Password reset token has expired. Please request a new one.",
                status_code=400,
            )

        # Consume token
        await self.session_repo.mark_reset_token_used(reset_token.id)

        # Hash and update password
        new_hash = hash_password(new_password)
        await self.user_repo.update_password(reset_token.user_id, new_hash)

        # Terminate all active sessions (mandatory security control)
        await self.session_repo.revoke_all_user_sessions(
            reset_token.user_id,
            reason="PASSWORD_RESET",
        )

        await self.audit_repo.log_event(
            action="PASSWORD_RESET_CONFIRMED",
            entity_type="user",
            entity_id=str(reset_token.user_id),
            actor_user_id=reset_token.user_id,
            correlation_id=correlation_id,
        )

        return GenericActionResponse(
            message="Password has been successfully updated. All active sessions have been terminated. Please log in with your new password."
        )

    async def switch_society(
        self,
        user_id: UUID,
        target_society_id: UUID,
        correlation_id: str | None = None,
    ) -> SocietySwitchResponse:
        """
        Validate user membership in target society and return resolved roles and permissions.
        Ensures tenant isolation and verifies membership before switching context.
        """
        is_member = await self.membership_repo.verify_user_society_membership(user_id, target_society_id)
        if not is_member:
            raise AuthorizationException(
                "Access denied: You are not an active member of this society.",
                details={"target_society_id": str(target_society_id)},
            )

        society = await self.society_repo.get_society_by_id(target_society_id)
        if not society or society.archived_at is not None:
            raise NotFoundException("Target society not found or inactive.")

        roles = await self.authz_repo.get_user_roles(user_id, target_society_id)
        permissions = await self.authz_repo.get_user_permission_codes(user_id, target_society_id)

        await self.audit_repo.log_event(
            action="SOCIETY_SWITCHED",
            entity_type="society",
            entity_id=str(target_society_id),
            society_id=target_society_id,
            actor_user_id=user_id,
            correlation_id=correlation_id,
        )

        return SocietySwitchResponse(
            society_id=society.id,
            display_name=society.display_name,
            roles=[r.code for r in roles],
            permissions=permissions,
        )
