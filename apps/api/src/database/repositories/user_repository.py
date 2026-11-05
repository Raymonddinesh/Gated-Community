"""Repository for Global User Identity."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.database.models.identity import User
from apps.api.src.database.models.membership import UserSocietyMembership
from apps.api.src.database.models.society import Society


class UserRepository:
    """Data access layer for global user accounts."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, user_id: UUID) -> User | None:
        """Fetch user by primary key if active (not soft-deleted)."""
        result = await self.session.execute(
            select(User).where(User.id == user_id, User.archived_at.is_(None))
        )
        return result.scalar_one_or_none()

    async def get_by_identifier(self, identifier: str) -> User | None:
        """
        Lookup user by email (case-insensitive) or normalized phone number.
        Only returns active (non-archived) users.
        """
        cleaned = identifier.strip()
        lower_cleaned = cleaned.lower()
        result = await self.session.execute(
            select(User).where(
                or_(
                    func.lower(User.email) == lower_cleaned,
                    User.phone == cleaned,
                ),
                User.archived_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def update_last_login(self, user_id: UUID) -> None:
        """Update last login timestamp."""
        user = await self.get_by_id(user_id)
        if user:
            user.last_login_at = datetime.now(UTC)

    async def update_password(self, user_id: UUID, password_hash: str) -> None:
        """Update password hash."""
        user = await self.get_by_id(user_id)
        if user:
            user.password_hash = password_hash

    async def get_user_societies(self, user_id: UUID) -> list[Society]:
        """Fetch all active societies where user holds an active membership."""
        result = await self.session.execute(
            select(Society)
            .join(UserSocietyMembership, Society.id == UserSocietyMembership.society_id)
            .where(
                UserSocietyMembership.user_id == user_id,
                UserSocietyMembership.membership_status == "ACTIVE",
                Society.archived_at.is_(None),
            )
            .order_by(Society.display_name)
        )
        return list(result.scalars().all())
