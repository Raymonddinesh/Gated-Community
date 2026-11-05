"""Tests for Tenant Isolation, Tenant Context Verification, and Cross-Tenant Security."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.core.exceptions import (
    AuthorizationException,
    NotFoundException,
    TenantContextMismatchException,
    TenantContextRequiredException,
)
from apps.api.src.core.tenant_context import (
    get_current_tenant_id,
    reset_current_tenant_id,
    set_current_tenant_id,
    tenant_context,
)
from apps.api.src.database.models.identity import User
from apps.api.src.database.models.membership import UserSocietyMembership
from apps.api.src.database.repositories.authorization_repository import AuthorizationRepository
from apps.api.src.database.repositories.membership_repository import MembershipRepository
from apps.api.src.database.repositories.society_repository import SocietyRepository
from apps.api.src.database.session import set_db_tenant_context
from apps.api.src.services.tenant_service import TenantService
from infrastructure.scripts.seed_dev_data import (
    UUID_SOCIETY_A,
    UUID_SOCIETY_B,
    UUID_SUPER_ADMIN,
    UUID_USER_MEMBER_B,
    UUID_USER_OWNER_A,
)


@pytest.mark.asyncio
async def test_tenant_context_vars_isolation():
    """Verify contextvars set and reset correctly in async task scope."""
    tenant_id = uuid.uuid4()

    assert get_current_tenant_id() is None

    async with tenant_context(tenant_id):
        assert get_current_tenant_id() == tenant_id

    # Must be reset after context exit
    assert get_current_tenant_id() is None


@pytest.mark.asyncio
async def test_tenant_context_manual_reset():
    """Verify manual token-based reset functionality."""
    tenant_id = uuid.uuid4()
    token = set_current_tenant_id(tenant_id)
    assert get_current_tenant_id() == tenant_id

    reset_current_tenant_id(token)
    assert get_current_tenant_id() is None


@pytest.mark.asyncio
async def test_tenant_service_validates_active_membership(seeded_session: AsyncSession):
    """Member of Society A can access Society A."""
    service = TenantService(seeded_session)
    verified = await service.verify_tenant_access(
        user_id=UUID_USER_OWNER_A,
        requested_society_id=UUID_SOCIETY_A,
    )
    assert verified == UUID_SOCIETY_A


@pytest.mark.asyncio
async def test_tenant_service_rejects_cross_tenant_access(seeded_session: AsyncSession):
    """
    Security Guarantee: Member of Society A cannot access Society B.
    Attempts to forge or pass X-Society-ID of Society B must raise 403 Forbidden.
    """
    service = TenantService(seeded_session)
    with pytest.raises(AuthorizationException) as exc_info:
        await service.verify_tenant_access(
            user_id=UUID_USER_OWNER_A,
            requested_society_id=UUID_SOCIETY_B,
        )
    assert "Access forbidden" in str(exc_info.value.message)
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_tenant_service_rejects_non_existent_society(seeded_session: AsyncSession):
    """Requested tenant hint pointing to non-existent society raises 404."""
    service = TenantService(seeded_session)
    random_society_id = uuid.uuid4()
    with pytest.raises(NotFoundException):
        await service.verify_tenant_access(
            user_id=UUID_USER_OWNER_A,
            requested_society_id=random_society_id,
        )


@pytest.mark.asyncio
async def test_platform_super_admin_has_cross_tenant_access(seeded_session: AsyncSession):
    """Platform Super Admin holds platform-level authorization to access any valid society."""
    service = TenantService(seeded_session)
    # Super Admin can access Society A
    verified_a = await service.verify_tenant_access(
        user_id=UUID_SUPER_ADMIN,
        requested_society_id=UUID_SOCIETY_A,
    )
    assert verified_a == UUID_SOCIETY_A

    # Super Admin can access Society B
    verified_b = await service.verify_tenant_access(
        user_id=UUID_SUPER_ADMIN,
        requested_society_id=UUID_SOCIETY_B,
    )
    assert verified_b == UUID_SOCIETY_B


@pytest.mark.asyncio
async def test_society_repository_strict_tenant_data_isolation(seeded_session: AsyncSession):
    """
    SocietyRepository queries strictly partition data by tenant boundary.
    Blocks for Society A must NEVER include blocks from Society B.
    """
    repo = SocietyRepository(seeded_session)

    blocks_a = await repo.get_blocks_for_society(UUID_SOCIETY_A)
    blocks_b = await repo.get_blocks_for_society(UUID_SOCIETY_B)

    assert len(blocks_a) >= 1
    assert len(blocks_b) >= 1

    # Verify no block overlap
    block_a_ids = {b.id for b in blocks_a}
    block_b_ids = {b.id for b in blocks_b}
    assert block_a_ids.isdisjoint(block_b_ids)

    # Verify code uniqueness within tenants
    assert all(b.society_id == UUID_SOCIETY_A for b in blocks_a)
    assert all(b.society_id == UUID_SOCIETY_B for b in blocks_b)


@pytest.mark.asyncio
async def test_membership_verification_checks(seeded_session: AsyncSession):
    """Verify membership repository accurately evaluates active association."""
    repo = MembershipRepository(seeded_session)

    # Owner A in Society A -> True
    assert await repo.verify_user_society_membership(UUID_USER_OWNER_A, UUID_SOCIETY_A) is True
    # Owner A in Society B -> False
    assert await repo.verify_user_society_membership(UUID_USER_OWNER_A, UUID_SOCIETY_B) is False

    # Member B in Society B -> True
    assert await repo.verify_user_society_membership(UUID_USER_MEMBER_B, UUID_SOCIETY_B) is True
    # Member B in Society A -> False
    assert await repo.verify_user_society_membership(UUID_USER_MEMBER_B, UUID_SOCIETY_A) is False


@pytest.mark.asyncio
async def test_postgres_rls_set_local_pooling_safety():
    """
    Verify SET LOCAL app.current_society_id execution:
    - On PostgreSQL engines, session executes 'SET LOCAL app.current_society_id = :val'.
    - On non-PostgreSQL engines, it gracefully skips without error.
    """
    # 1. PostgreSQL dialect mock
    pg_session = AsyncMock()
    pg_bind = MagicMock()
    pg_bind.dialect.name = "postgresql"
    pg_session.bind = pg_bind

    test_society_id = uuid.uuid4()
    await set_db_tenant_context(pg_session, test_society_id)

    # Ensure execute was called with SET LOCAL
    pg_session.execute.assert_called_once()
    call_args = pg_session.execute.call_args
    sql_text = str(call_args[0][0])
    params = call_args[0][1]
    assert "set_config('app.current_society_id'" in sql_text or "SET LOCAL app.current_society_id" in sql_text
    assert params["val"] == str(test_society_id)

    # 2. SQLite dialect (does not call SET LOCAL)
    sqlite_session = AsyncMock()
    sqlite_bind = MagicMock()
    sqlite_bind.dialect.name = "sqlite"
    sqlite_session.bind = sqlite_bind

    await set_db_tenant_context(sqlite_session, test_society_id)
    sqlite_session.execute.assert_not_called()


# ==============================================================================
# PHASE 2 SECURITY FINALIZATION VERIFICATION TESTS (A - F)
# ==============================================================================


@pytest.mark.asyncio
async def test_normal_user_cannot_activate_rls_bypass():
    """
    Test A: Verify RLS policies and application session management do not support
    client-driven RLS bypass.
    - Migration file contains NO 'app.bypass_rls' references.
    - set_db_tenant_context NEVER sets bypass_rls.
    """
    from pathlib import Path

    migration_file = Path("apps/api/alembic/versions/20261002_0002_multi_tenancy.py")
    content = migration_file.read_text(encoding="utf-8")
    assert "bypass_rls" not in content, "Vulnerability: Migration contains obsolete app.bypass_rls reference!"

    # Ensure set_db_tenant_context strictly binds society_id without bypass mechanisms
    session = AsyncMock()
    bind = MagicMock()
    bind.dialect.name = "postgresql"
    session.bind = bind

    await set_db_tenant_context(session, uuid.uuid4())
    call_args = session.execute.call_args
    sql = str(call_args[0][0])
    assert "bypass_rls" not in sql
    assert "set_config('app.current_society_id'" in sql or "SET LOCAL app.current_society_id" in sql


@pytest.mark.asyncio
async def test_super_admin_does_not_receive_unrestricted_database_bypass(seeded_session: AsyncSession):
    """
    Test B: SUPER_ADMIN does NOT receive unrestricted database RLS bypass.
    - When accessing tenant resources, SUPER_ADMIN must explicitly target a society.
    - If neither URL nor header is supplied, resolve_and_verify_tenant raises TenantContextRequiredException.
    - When verified, returns explicit society ID to be bound to SET LOCAL app.current_society_id.
    """
    service = TenantService(seeded_session)

    # 1. Unspecified tenant context for Super Admin must fail deterministically
    with pytest.raises(TenantContextRequiredException) as exc_info:
        await service.resolve_and_verify_tenant(
            user_id=UUID_SUPER_ADMIN,
            url_society_id=None,
            header_society_id=None,
        )
    assert exc_info.value.code == "TENANT_CONTEXT_REQUIRED"
    assert "Super Admin must provide an explicit" in exc_info.value.message

    # 2. When explicit target is provided, returns the target ID to bind session context
    target = await service.resolve_and_verify_tenant(
        user_id=UUID_SUPER_ADMIN,
        url_society_id=UUID_SOCIETY_A,
    )
    assert target == UUID_SOCIETY_A


@pytest.mark.asyncio
async def test_memberships_cannot_leak_across_societies(seeded_session: AsyncSession):
    """
    Test C: Tenant-owned membership records cannot leak across societies.
    A query for Society A memberships must never yield Society B records.
    """
    # Query memberships for Society A directly
    res_a = await seeded_session.execute(
        select(UserSocietyMembership).where(UserSocietyMembership.society_id == UUID_SOCIETY_A)
    )
    memberships_a = res_a.scalars().all()

    res_b = await seeded_session.execute(
        select(UserSocietyMembership).where(UserSocietyMembership.society_id == UUID_SOCIETY_B)
    )
    memberships_b = res_b.scalars().all()

    assert len(memberships_a) >= 1
    assert len(memberships_b) >= 1

    members_a_users = {m.user_id for m in memberships_a}
    members_b_users = {m.user_id for m in memberships_b}

    # Verify memberships are strictly partitioned
    assert all(m.society_id == UUID_SOCIETY_A for m in memberships_a)
    assert all(m.society_id == UUID_SOCIETY_B for m in memberships_b)
    assert UUID_USER_MEMBER_B not in members_a_users
    assert UUID_USER_OWNER_A not in members_b_users


@pytest.mark.asyncio
async def test_role_assignments_cannot_leak_across_societies(seeded_session: AsyncSession):
    """
    Test D: Role assignments cannot leak across societies.
    Society roles in Society A are completely invisible to queries scoped to Society B.
    """
    auth_repo = AuthorizationRepository(seeded_session)

    # Owner A has SOCIETY_ADMIN role in Society A
    roles_a = await auth_repo.get_user_roles(UUID_USER_OWNER_A, society_id=UUID_SOCIETY_A)
    assert any(r.code == "SOCIETY_ADMIN" for r in roles_a)

    # Querying Owner A's roles in Society B must return NO society roles
    roles_b = await auth_repo.get_user_roles(UUID_USER_OWNER_A, society_id=UUID_SOCIETY_B)
    society_roles_in_b = [r for r in roles_b if r.scope_type == "SOCIETY"]
    assert len(society_roles_in_b) == 0


@pytest.mark.asyncio
async def test_url_society_id_and_header_mismatch_is_rejected(seeded_session: AsyncSession):
    """
    Test E: URL society ID + X-Society-ID mismatch is rejected immediately with
    HTTP 400 TENANT_CONTEXT_MISMATCH.
    """
    service = TenantService(seeded_session)

    with pytest.raises(TenantContextMismatchException) as exc_info:
        await service.resolve_and_verify_tenant(
            user_id=UUID_USER_OWNER_A,
            url_society_id=UUID_SOCIETY_A,
            header_society_id=UUID_SOCIETY_B,  # Deliberate conflict
        )

    assert exc_info.value.code == "TENANT_CONTEXT_MISMATCH"
    assert exc_info.value.status_code == 400
    assert "Tenant context mismatch" in exc_info.value.message
    assert exc_info.value.details["url_society_id"] == str(UUID_SOCIETY_A)
    assert exc_info.value.details["header_society_id"] == str(UUID_SOCIETY_B)


@pytest.mark.asyncio
async def test_multi_society_user_ambiguous_tenant_context_handled_deterministically(
    seeded_session: AsyncSession,
):
    """
    Test F: Multi-society user without unambiguous tenant context is handled deterministically:
    1. A user belonging to multiple societies without explicit URL or header hint triggers
       HTTP 400 TENANT_CONTEXT_REQUIRED (never silently picks a society).
    2. A user belonging to a single society resolves automatically to that single society.
    3. Explicit X-Society-ID resolves to the requested society.
    """
    service = TenantService(seeded_session)

    # Create a user with active memberships in BOTH Society A and Society B
    multi_user = User(
        email="multi_society_resident@example.com",
        first_name="Arun",
        last_name="Sharma",
        display_name="Arun Sharma",
        status="ACTIVE",
    )
    seeded_session.add(multi_user)
    await seeded_session.flush()

    m_a = UserSocietyMembership(user_id=multi_user.id, society_id=UUID_SOCIETY_A, membership_status="ACTIVE")
    m_b = UserSocietyMembership(user_id=multi_user.id, society_id=UUID_SOCIETY_B, membership_status="ACTIVE")
    seeded_session.add_all([m_a, m_b])
    await seeded_session.commit()

    # 1. Ambiguous resolution with no URL and no header -> MUST FAIL with TENANT_CONTEXT_REQUIRED
    with pytest.raises(TenantContextRequiredException) as exc_info:
        await service.resolve_and_verify_tenant(
            user_id=multi_user.id,
            url_society_id=None,
            header_society_id=None,
        )
    assert exc_info.value.code == "TENANT_CONTEXT_REQUIRED"
    assert exc_info.value.status_code == 400
    assert len(exc_info.value.details["available_societies"]) == 2

    # 2. When explicit header is provided -> Resolves cleanly
    target_a = await service.resolve_and_verify_tenant(
        user_id=multi_user.id,
        url_society_id=None,
        header_society_id=UUID_SOCIETY_A,
    )
    assert target_a == UUID_SOCIETY_A

    target_b = await service.resolve_and_verify_tenant(
        user_id=multi_user.id,
        url_society_id=None,
        header_society_id=UUID_SOCIETY_B,
    )
    assert target_b == UUID_SOCIETY_B

    # 3. Single-membership user (Member B) without URL or header -> Resolves unambiguously to Society B
    single_target = await service.resolve_and_verify_tenant(
        user_id=UUID_USER_MEMBER_B,
        url_society_id=None,
        header_society_id=None,
    )
    assert single_target == UUID_SOCIETY_B
