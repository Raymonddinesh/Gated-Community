"""Tenant Resolution and Verification Domain Service."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.core.exceptions import (
    AuthorizationException,
    NotFoundException,
    TenantContextMismatchException,
    TenantContextRequiredException,
)
from apps.api.src.database.repositories.authorization_repository import AuthorizationRepository
from apps.api.src.database.repositories.membership_repository import MembershipRepository
from apps.api.src.database.repositories.society_repository import SocietyRepository


class TenantService:
    """Service orchestrating tenant validation, verification, and boundary checks."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.society_repo = SocietyRepository(session)
        self.membership_repo = MembershipRepository(session)
        self.auth_repo = AuthorizationRepository(session)

    async def verify_tenant_access(self, user_id: UUID, requested_society_id: UUID) -> UUID:
        """
        Core verification pipeline:
        Authenticated User -> Membership Lookup -> Validate Requested Society Hint -> Tenant Bound.
        Raises AuthorizationException (HTTP 403) if client hint does not match verified memberships.
        NOTE: Even for platform SUPER_ADMIN, returns the explicit requested_society_id,
        ensuring SUPER_ADMIN queries execute within the explicit target tenant sandbox,
        NOT an unrestricted RLS bypass.
        """
        # 1. Verify that the requested society actually exists
        society = await self.society_repo.get_society_by_id(requested_society_id)
        if not society:
            raise NotFoundException(f"Society with ID '{requested_society_id}' does not exist.")

        # 2. Check if user holds platform Super Admin role (cross-tenant administrative privilege)
        platform_roles = await self.auth_repo.get_user_roles(user_id, society_id=None)
        if any(role.code == "SUPER_ADMIN" for role in platform_roles):
            return requested_society_id

        # 3. Verify user has an ACTIVE membership in this society
        is_member = await self.membership_repo.verify_user_society_membership(user_id, requested_society_id)
        if not is_member:
            raise AuthorizationException(
                message=f"Access forbidden: User has no active membership in society '{requested_society_id}'."
            )

        return requested_society_id

    async def resolve_and_verify_tenant(
        self,
        user_id: UUID,
        url_society_id: UUID | None = None,
        header_society_id: UUID | None = None,
    ) -> UUID:
        """
        Canonical Tenant Context Resolver:
        Enforces deterministic precedence between URL, X-Society-ID header, and user memberships.

        Rules:
        1. Both provided: url_society_id and header_society_id MUST match identically.
           Mismatch raises TenantContextMismatchException (HTTP 400 TENANT_CONTEXT_MISMATCH).
        2. URL provided: target = url_society_id.
        3. Header provided: target = header_society_id.
        4. Neither provided:
           - Retrieve active society memberships for user_id.
           - If 0 active memberships:
             - If SUPER_ADMIN: raises TenantContextRequiredException (HTTP 400 TENANT_CONTEXT_REQUIRED),
               because SUPER_ADMIN must explicitly specify target society.
             - Else: raises AuthorizationException (HTTP 403 AUTHORIZATION_ERROR).
           - If exactly 1 active membership: target = that single society_id.
           - If > 1 active memberships: raises TenantContextRequiredException (HTTP 400 TENANT_CONTEXT_REQUIRED).
             Never silently chooses an arbitrary society.
        5. Calls verify_tenant_access(user_id, target) to guarantee authorization.
        """
        # Step 1: Check for explicit conflict between URL resource and header hint
        if url_society_id is not None and header_society_id is not None:
            if url_society_id != header_society_id:
                raise TenantContextMismatchException(
                    message=(
                        f"Tenant context mismatch: URL resource specifies society '{url_society_id}' "
                        f"but X-Society-ID header specifies '{header_society_id}'."
                    ),
                    details={
                        "url_society_id": str(url_society_id),
                        "header_society_id": str(header_society_id),
                    },
                )
            target_society_id = url_society_id
        elif url_society_id is not None:
            target_society_id = url_society_id
        elif header_society_id is not None:
            target_society_id = header_society_id
        else:
            # Step 2: Neither URL nor Header provided; resolve from memberships
            active_societies = await self.membership_repo.list_user_societies(user_id)
            if len(active_societies) == 0:
                platform_roles = await self.auth_repo.get_user_roles(user_id, society_id=None)
                if any(role.code == "SUPER_ADMIN" for role in platform_roles):
                    raise TenantContextRequiredException(
                        message=(
                            "Tenant context required: Platform Super Admin must provide an explicit "
                            "URL society parameter or X-Society-ID header to access tenant resources."
                        )
                    )
                raise AuthorizationException(message="User has no active society memberships.")
            if len(active_societies) == 1:
                target_society_id = active_societies[0]
            else:
                # Multiple societies: Ambiguous! Must never guess.
                raise TenantContextRequiredException(
                    message=(
                        "Ambiguous tenant context: User holds active memberships in multiple societies. "
                        "An explicit X-Society-ID header or URL society parameter is required."
                    ),
                    details={"available_societies": [str(sid) for sid in active_societies]},
                )

        # Step 3: Verify access against the resolved tenant
        return await self.verify_tenant_access(user_id, target_society_id)
