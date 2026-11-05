"""Repository for User Sessions, Token Families, and Password Reset Tokens."""

import uuid
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.database.models.session import PasswordResetToken, UserSession


class SessionRepository:
    """Data access layer for sessions, refresh token families, and reset tokens."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_session(
        self,
        user_id: UUID,
        refresh_token_hash: str,
        expires_at: datetime,
        family_id: UUID | None = None,
        user_agent: str | None = None,
        ip_address: str | None = None,
    ) -> UserSession:
        """Create and persist a new user session."""
        session_obj = UserSession(
            id=uuid.uuid4(),
            user_id=user_id,
            family_id=family_id or uuid.uuid4(),
            refresh_token_hash=refresh_token_hash,
            user_agent=user_agent[:500] if user_agent else None,
            ip_address=ip_address[:45] if ip_address else None,
            is_revoked=False,
            expires_at=expires_at,
            last_used_at=datetime.now(UTC),
        )
        self.session.add(session_obj)
        await self.session.flush()
        return session_obj

    async def get_session_by_token_hash(self, token_hash: str) -> UserSession | None:
        """Fetch session by SHA-256 digest of refresh token."""
        result = await self.session.execute(
            select(UserSession).where(UserSession.refresh_token_hash == token_hash)
        )
        return result.scalar_one_or_none()

    async def get_session_by_id(self, session_id: UUID) -> UserSession | None:
        """Fetch session by primary key."""
        result = await self.session.execute(select(UserSession).where(UserSession.id == session_id))
        return result.scalar_one_or_none()

    async def revoke_session(self, session_id: UUID, reason: str = "LOGOUT") -> None:
        """Revoke a single session."""
        await self.session.execute(
            update(UserSession)
            .where(UserSession.id == session_id, UserSession.is_revoked.is_(False))
            .values(
                is_revoked=True,
                revoked_at=datetime.now(UTC),
                revoke_reason=reason,
            )
        )

    async def revoke_session_family(self, family_id: UUID, reason: str = "REPLAY_DETECTED") -> int:
        """
        Revoke all sessions belonging to the same token family.
        Triggered when refresh token reuse or replay attacks are detected.
        """
        result = await self.session.execute(
            update(UserSession)
            .where(UserSession.family_id == family_id, UserSession.is_revoked.is_(False))
            .values(
                is_revoked=True,
                revoked_at=datetime.now(UTC),
                revoke_reason=reason,
            )
        )
        return int(getattr(result, "rowcount", 0))

    async def revoke_all_user_sessions(self, user_id: UUID, reason: str = "LOGOUT_ALL") -> int:
        """Revoke all active sessions for a user across all devices."""
        result = await self.session.execute(
            update(UserSession)
            .where(UserSession.user_id == user_id, UserSession.is_revoked.is_(False))
            .values(
                is_revoked=True,
                revoked_at=datetime.now(UTC),
                revoke_reason=reason,
            )
        )
        return int(getattr(result, "rowcount", 0))

    async def create_password_reset_token(
        self,
        user_id: UUID,
        token_hash: str,
        expires_at: datetime,
    ) -> PasswordResetToken:
        """Create and persist a single-use password reset token."""
        reset_token = PasswordResetToken(
            id=uuid.uuid4(),
            user_id=user_id,
            token_hash=token_hash,
            expires_at=expires_at,
            is_used=False,
            created_at=datetime.now(UTC),
        )
        self.session.add(reset_token)
        await self.session.flush()
        return reset_token

    async def get_reset_token_by_hash(self, token_hash: str) -> PasswordResetToken | None:
        """Fetch password reset token by SHA-256 digest."""
        result = await self.session.execute(
            select(PasswordResetToken).where(PasswordResetToken.token_hash == token_hash)
        )
        return result.scalar_one_or_none()

    async def mark_reset_token_used(self, token_id: UUID) -> None:
        """Consume single-use password reset token."""
        await self.session.execute(
            update(PasswordResetToken)
            .where(PasswordResetToken.id == token_id)
            .values(
                is_used=True,
                used_at=datetime.now(UTC),
            )
        )
