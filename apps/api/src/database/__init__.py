"""Database package using SQLAlchemy 2.x Async."""

from apps.api.src.database.base import Base
from apps.api.src.database.models import (
    AuditLog,
    Block,
    Floor,
    Permission,
    ResidentProfile,
    Role,
    RoleAssignment,
    RolePermission,
    Society,
    Unit,
    UnitOccupancy,
    User,
    UserSocietyMembership,
)
from apps.api.src.database.session import (
    check_database_health,
    close_db,
    get_db_session,
    init_db,
)

__all__ = [
    "Base",
    "get_db_session",
    "check_database_health",
    "init_db",
    "close_db",
    "User",
    "Society",
    "Block",
    "Floor",
    "Unit",
    "UserSocietyMembership",
    "UnitOccupancy",
    "ResidentProfile",
    "Role",
    "Permission",
    "RolePermission",
    "RoleAssignment",
    "AuditLog",
]
