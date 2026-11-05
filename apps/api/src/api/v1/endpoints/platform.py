"""Phase 21C/21D — Platform SaaS Administration & Society Governance Endpoints."""

import uuid
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.auth.dependencies import require_role
from apps.api.src.database.models.identity import User
from apps.api.src.database.session import get_db_session
from apps.api.src.subscriptions.platform_admin_service import PlatformAdminService
from apps.api.src.subscriptions.provisioning_engine import SocietyProvisioningEngine
from apps.api.src.subscriptions.schemas import (
    ProvisionSocietyRequest,
    ProvisionSocietyResponse,
    SocietyAdminDetailResponse,
    SocietyDirectoryResponse,
    SocietyLifecycleActionRequest,
    SocietyLifecycleActionResponse,
    SocietyProvisioningDiagnosticsResponse,
    SocietySubscriptionOverviewResponse,
)

router = APIRouter(prefix="/platform", tags=["Platform SaaS Administration"])


# ==============================================================================
# 1. Society Directory & Inspection
# ==============================================================================


@router.get(
    "/societies",
    response_model=SocietyDirectoryResponse,
    status_code=status.HTTP_200_OK,
)
async def list_societies(
    search: str | None = Query(None, description="Search legal name, display name, or registration number"),
    status: str | None = Query(None, description="Filter by society status (ACTIVE, SUSPENDED, IN_PROGRESS, FAILED)"),
    onboarding_status: str | None = Query(None, description="Filter by onboarding status (COMPLETED, IN_PROGRESS, FAILED)"),
    state: str | None = Query(None, description="Filter by state"),
    city: str | None = Query(None, description="Filter by city"),
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    sort_by: str = Query("created_at", pattern="^(created_at|legal_name|status)$"),
    sort_order: str = Query("desc", pattern="^(asc|desc)$"),
    current_user: User = Depends(require_role("SUPER_ADMIN")),
    session: AsyncSession = Depends(get_db_session),
) -> SocietyDirectoryResponse:
    """List, search, filter, and paginate societies from global platform records."""
    admin_svc = PlatformAdminService(session)
    return await admin_svc.list_societies(
        search=search,
        status=status,
        onboarding_status=onboarding_status,
        state=state,
        city=city,
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        sort_order=sort_order,
    )


@router.get(
    "/societies/{society_id}",
    response_model=SocietyAdminDetailResponse,
    status_code=status.HTTP_200_OK,
)
async def get_society_detail(
    society_id: UUID,
    current_user: User = Depends(require_role("SUPER_ADMIN")),
    session: AsyncSession = Depends(get_db_session),
) -> SocietyAdminDetailResponse:
    """Retrieve comprehensive society metadata, subscription details, and primary admin info."""
    admin_svc = PlatformAdminService(session)
    return await admin_svc.get_society_detail(society_id=society_id)


# ==============================================================================
# 2. Society Lifecycle State Transitions (Mandatory Condition 2)
# ==============================================================================


@router.post(
    "/societies/{society_id}/suspend",
    response_model=SocietyLifecycleActionResponse,
    status_code=status.HTTP_200_OK,
)
async def suspend_society(
    society_id: UUID,
    payload: SocietyLifecycleActionRequest,
    request: Request,
    current_user: User = Depends(require_role("SUPER_ADMIN")),
    session: AsyncSession = Depends(get_db_session),
) -> SocietyLifecycleActionResponse:
    """Administratively suspend a society with pessimistic row locking and audit trail.

    Guarantees:
    - Serializes on SELECT FOR UPDATE row lock.
    - Requires administrative reason >= 10 non-whitespace characters.
    - Rejects duplicate suspension (409 Conflict).
    - Preserves logical decoupling from commercial subscription status.
    """
    correlation_id = getattr(request.state, "correlation_id", None) or str(uuid.uuid4())
    admin_svc = PlatformAdminService(session)
    return await admin_svc.suspend_society(
        society_id=society_id,
        actor_user_id=current_user.id,
        reason=payload.reason,
        notes=payload.notes,
        correlation_id=correlation_id,
    )


@router.post(
    "/societies/{society_id}/reactivate",
    response_model=SocietyLifecycleActionResponse,
    status_code=status.HTTP_200_OK,
)
async def reactivate_society(
    society_id: UUID,
    payload: SocietyLifecycleActionRequest,
    request: Request,
    current_user: User = Depends(require_role("SUPER_ADMIN")),
    session: AsyncSession = Depends(get_db_session),
) -> SocietyLifecycleActionResponse:
    """Administratively reactivate a suspended society with pessimistic row locking.

    Guarantees:
    - Serializes on SELECT FOR UPDATE row lock.
    - Requires administrative reason >= 10 non-whitespace characters.
    - Rejects duplicate reactivation (409 Conflict).
    - STRICT DECOUPLING: NEVER reactivates a CANCELLED subscription or clears PAST_DUE restrictions.
    """
    correlation_id = getattr(request.state, "correlation_id", None) or str(uuid.uuid4())
    admin_svc = PlatformAdminService(session)
    return await admin_svc.reactivate_society(
        society_id=society_id,
        actor_user_id=current_user.id,
        reason=payload.reason,
        notes=payload.notes,
        correlation_id=correlation_id,
    )


# ==============================================================================
# 3. Subscription & Quota Overview (Phase 21B Integration)
# ==============================================================================


@router.get(
    "/societies/{society_id}/subscription-overview",
    response_model=SocietySubscriptionOverviewResponse,
    status_code=status.HTTP_200_OK,
)
@router.get(
    "/societies/{society_id}/subscription",
    response_model=SocietySubscriptionOverviewResponse,
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
async def get_subscription_overview(
    society_id: UUID,
    current_user: User = Depends(require_role("SUPER_ADMIN")),
    session: AsyncSession = Depends(get_db_session),
) -> SocietySubscriptionOverviewResponse:
    """Consolidated subscription, feature entitlement, and quota usage overview.

    Directly delegates to Phase 21B EntitlementService and QuotaEnforcementService
    within a properly scoped tenant context.
    """
    admin_svc = PlatformAdminService(session)
    return await admin_svc.get_subscription_overview(society_id=society_id)


# ==============================================================================
# 4. Provisioning Diagnostics (Mandatory Condition 1: FORCE RLS Compliance)
# ==============================================================================


@router.get(
    "/societies/{society_id}/provisioning-logs",
    response_model=SocietyProvisioningDiagnosticsResponse,
    status_code=status.HTTP_200_OK,
)
async def get_provisioning_diagnostics(
    society_id: UUID,
    current_user: User = Depends(require_role("SUPER_ADMIN")),
    session: AsyncSession = Depends(get_db_session),
) -> SocietyProvisioningDiagnosticsResponse:
    """Retrieve step-by-step provisioning logs and failure diagnostics under FORCE RLS.

    Executes within transaction-scoped tenant context (set_config), guaranteeing
    compliance with FORCE ROW LEVEL SECURITY on society_provisioning_logs.
    """
    admin_svc = PlatformAdminService(session)
    return await admin_svc.get_provisioning_diagnostics(society_id=society_id)


# ==============================================================================
# 5. Provisioning & Concurrency-Safe Retry (Mandatory Condition 3)
# ==============================================================================


@router.post(
    "/societies/provision",
    response_model=ProvisionSocietyResponse,
    status_code=status.HTTP_201_CREATED,
)
async def provision_society(
    payload: ProvisionSocietyRequest,
    request: Request,
    response: Response,
    x_idempotency_key: str | None = Header(None, alias="X-Idempotency-Key"),
    current_user: User = Depends(require_role("SUPER_ADMIN")),
    session: AsyncSession = Depends(get_db_session),
) -> ProvisionSocietyResponse:
    """Provision a new tenant society into the platform.

    Security & Authorization:
    - Strictly restricted to platform users holding the 'SUPER_ADMIN' role.

    Guarantees:
    - Atomicity: executes in a single PostgreSQL transaction with complete rollback on error.
    - Idempotency: replaying an identical key and payload returns HTTP 200 OK with cached result.
    - Replay with mutated payload: returns HTTP 422 Unprocessable Entity (IDEMPOTENCY_PAYLOAD_MISMATCH).
    - Concurrency Safety: non-blocking advisory locks reject in-progress attempts with HTTP 409 and Retry-After: 5.
    - Zero RLS Bypass: establishes transaction-local tenant context to populate tenant-owned tables.
    """
    if x_idempotency_key:
        try:
            payload.provisioning_request_id = UUID(x_idempotency_key)
        except ValueError:
            pass

    correlation_id = getattr(request.state, "correlation_id", None) or str(uuid.uuid4())

    engine = SocietyProvisioningEngine(session)
    result = await engine.provision_society(
        request=payload,
        current_user_id=current_user.id,
        correlation_id=correlation_id,
    )

    if result.is_idempotent_replay:
        response.status_code = status.HTTP_200_OK

    return result


@router.post(
    "/societies/{society_id}/provisioning-retry",
    response_model=ProvisionSocietyResponse,
    status_code=status.HTTP_201_CREATED,
)
@router.post(
    "/societies/{society_id}/provisioning/retry",
    response_model=ProvisionSocietyResponse,
    status_code=status.HTTP_201_CREATED,
    include_in_schema=False,
)
async def retry_provisioning(
    society_id: UUID,
    request: Request,
    response: Response,
    payload: ProvisionSocietyRequest | None = None,
    current_user: User = Depends(require_role("SUPER_ADMIN")),
    session: AsyncSession = Depends(get_db_session),
) -> ProvisionSocietyResponse:
    """Retry a failed provisioning request safely.

    Guarantees:
    - Rejects retry if onboarding is already COMPLETED (409 Conflict).
    - Rejects retry if concurrent operation is running via advisory lock (409 Conflict, Retry-After: 5).
    - Reuses SocietyProvisioningEngine with single-transaction atomicity and rollback.
    """
    correlation_id = getattr(request.state, "correlation_id", None) or str(uuid.uuid4())
    admin_svc = PlatformAdminService(session)
    result = await admin_svc.retry_provisioning(
        society_id=society_id,
        current_user_id=current_user.id,
        correlation_id=correlation_id,
        override_request=payload,
    )

    if result.is_idempotent_replay:
        response.status_code = status.HTTP_200_OK

    return result
