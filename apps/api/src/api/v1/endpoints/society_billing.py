"""Phase 21E.5 — Tenant-Facing SaaS Commercial Billing API Router.

Mounted at: /api/v1/societies/{society_id}/billing

Exposes self-service subscription and commercial billing endpoints for tenant administrators:
1. Subscription Overview & Plan Catalog:
   - GET  /subscription           - Active subscription status, current plan, limits, and renewal dates.
   - GET  /plans                  - Active public plan catalog with monthly/annual pricing and entitlements.
   - GET  /subscription/usage     - Real-time usage metrics and quota limits.
   - GET  /subscription/history   - Immutable audit log of plan and lifecycle changes.
2. Plan Change Management:
   - POST /subscription/upgrade-preview - Non-mutating simulation of mid-cycle upgrade charges/credits.
   - POST /subscription/upgrade         - Execute immediate mid-cycle upgrade and proration.
   - POST /subscription/downgrade       - Schedule plan downgrade effective at renewal boundary.
3. Subscription Lifecycle Governance:
   - POST /subscription/cancel   - Schedule cancellation at period end (disables auto-renew).
   - POST /subscription/resume   - Resume scheduled cancellation (re-enables auto-renew).
4. Platform Invoices:
   - GET  /invoices               - Paginated invoices for this tenant society only.
   - GET  /invoices/{invoice_id}  - Itemized invoice details with GST breakdown.
   - GET  /invoices/{invoice_id}/pdf - Binary immutable PDF stream.
   - GET  /invoices/{invoice_id}/download-url - Short-lived presigned download URL.
   - POST /invoices/{invoice_id}/send-email   - Outbox email dispatch request.
   - POST /invoices/{invoice_id}/checkout     - Authoritative server-side checkout payment order.
5. Platform Credit Notes:
   - GET  /credit-notes           - Paginated credit notes for this tenant society only.
   - GET  /credit-notes/{id}      - Itemized credit note details with GST reversal.
   - GET  /credit-notes/{id}/pdf  - Binary immutable credit note PDF stream.
   - GET  /credit-notes/{id}/download-url - Short-lived presigned download URL.
   - POST /credit-notes/{id}/send-email   - Outbox credit note email dispatch request.
6. Gateway Payments:
   - POST /payments/verify        - Cryptographic checkout signature verification and atomic settlement.
   - GET  /payments               - Paginated captured payment records for this tenant.
7. Advance Balance & Delivery Tracking:
   - GET  /balance                - Consolidated advance credits and balance summary.
   - GET  /balance/transactions   - Paginated credit balance adjustment ledger.
   - GET  /documents/{doc_id}/deliveries - Delivery audit history and provider attempts.

Security & Multi-Tenancy:
- Enforces resolve_society_context (validates active membership, sets session RLS).
- Strict RBAC:
  - Write: SOCIETY_ADMIN, TREASURER (and SUPER_ADMIN).
  - Read: SOCIETY_ADMIN, TREASURER, SECRETARY, COMMITTEE_MEMBER (and SUPER_ADMIN).
  - Denied: RESIDENT, TENANT (HTTP 403 Forbidden).
"""

import logging
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from apps.api.src.auth.dependencies import get_current_user, resolve_society_context
from apps.api.src.core.exceptions import (
    AuthorizationException,
    NotFoundException,
)
from apps.api.src.database.models.identity import User
from apps.api.src.database.models.platform_billing import (
    PlatformCreditNote,
    PlatformInvoice,
    PlatformPayment,
    PlatformSubscriptionAuditLog,
    PlatformSubscriptionHistory,
)
from apps.api.src.database.models.subscription import (
    PlatformSubscriptionPlan,
    SocietySubscription,
    SocietyUsageMetric,
)
from apps.api.src.database.repositories.authorization_repository import AuthorizationRepository
from apps.api.src.database.session import get_db_session
from apps.api.src.subscriptions.billing_admin_service import PlatformBillingAdminService
from apps.api.src.subscriptions.billing_api_schemas import (
    PaginatedResponse,
    PlatformBillingAdjustmentResponse,
    PlatformPaymentListItemResponse,
    PlatformSubscriptionPlanResponse,
    SocietyAdvanceBalanceResponse,
    SubscriptionHistoryItemResponse,
    TenantCheckoutRequest,
    TenantCheckoutResponse,
    TenantDowngradeRequest,
    TenantPaymentVerifyRequest,
    TenantSubscriptionCancelRequest,
    TenantSubscriptionOverview,
    TenantSubscriptionResumeResponse,
    TenantUpgradeExecuteRequest,
    TenantUpgradePreviewRequest,
    TenantUsageMetricItemResponse,
)
from apps.api.src.subscriptions.credit_notes.schemas import PlatformCreditNoteResponse
from apps.api.src.subscriptions.documents.document_orchestrator import (
    PlatformBillingDocumentService,
)
from apps.api.src.subscriptions.documents.schemas import (
    PlatformDocumentDeliveryResponse,
    PlatformDocumentDownloadUrlResponse,
    PlatformDocumentEmailRequest,
)
from apps.api.src.subscriptions.downgrade_service import SubscriptionDowngradeService
from apps.api.src.subscriptions.enums import SubscriptionStatus
from apps.api.src.subscriptions.exceptions import (
    SubscriptionAlreadyCancelledException,
    SubscriptionNotFoundException,
)
from apps.api.src.subscriptions.invoicing.schemas import PlatformInvoiceResponse
from apps.api.src.subscriptions.payments.order_service import PaymentOrderService
from apps.api.src.subscriptions.payments.schemas import PaymentVerificationResponse
from apps.api.src.subscriptions.payments.verification_service import (
    PaymentVerificationService,
)
from apps.api.src.subscriptions.quota_enforcement_service import QuotaEnforcementService
from apps.api.src.subscriptions.schemas import (
    ScheduledDowngradeResponse,
    UpgradeCalculationResult,
)
from apps.api.src.subscriptions.upgrade_service import SubscriptionUpgradeService

logger = logging.getLogger("societysphere.api.society_billing")

router = APIRouter(
    prefix="/societies/{society_id}/billing",
    tags=["Tenant Commercial Billing"],
)


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


# ==============================================================================
# RBAC Authorization Dependencies
# ==============================================================================


async def require_billing_access(
    society_id: UUID,
    current_user: User,
    db: AsyncSession,
    write: bool,
) -> User:
    """Validate canonical society roles for billing operations."""
    authz_repo = AuthorizationRepository(db)
    roles = await authz_repo.get_user_roles(current_user.id, society_id)
    platform_roles = await authz_repo.get_user_roles(current_user.id, None)
    all_role_codes = {r.code for r in roles} | {r.code for r in platform_roles}

    if "SUPER_ADMIN" in all_role_codes:
        return current_user

    if write:
        write_roles = {"SOCIETY_ADMIN", "TREASURER"}
        if not (all_role_codes & write_roles):
            raise AuthorizationException(
                "Forbidden: Write access to commercial billing requires SOCIETY_ADMIN or TREASURER role.",
                details={"required_roles": list(write_roles), "user_roles": list(all_role_codes)},
            )
    else:
        read_roles = {"SOCIETY_ADMIN", "TREASURER", "SECRETARY", "COMMITTEE_MEMBER"}
        if not (all_role_codes & read_roles):
            raise AuthorizationException(
                "Forbidden: Billing access requires an administrative role (SOCIETY_ADMIN, TREASURER, SECRETARY, or COMMITTEE_MEMBER).",
                details={"required_roles": list(read_roles), "user_roles": list(all_role_codes)},
            )
    return current_user


async def require_billing_read(
    society_id: UUID = Depends(resolve_society_context),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> tuple[UUID, User]:
    """Dependency verifying read access to society billing."""
    await require_billing_access(society_id, current_user, db, write=False)
    return society_id, current_user


async def require_billing_write(
    society_id: UUID = Depends(resolve_society_context),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> tuple[UUID, User]:
    """Dependency verifying write access to society billing."""
    await require_billing_access(society_id, current_user, db, write=True)
    return society_id, current_user


# ==============================================================================
# 1. Tenant Subscription & Usage APIs
# ==============================================================================


@router.get(
    "/subscription",
    response_model=TenantSubscriptionOverview,
    status_code=status.HTTP_200_OK,
    summary="Get Tenant Subscription Overview",
)
async def get_tenant_subscription(
    auth_ctx: tuple[UUID, User] = Depends(require_billing_read),
    session: AsyncSession = Depends(get_db_session),
) -> TenantSubscriptionOverview:
    """Retrieve society subscription overview including active plan, cycle, and renewal dates."""
    society_id, _ = auth_ctx

    stmt = (
        select(SocietySubscription)
        .options(
            selectinload(SocietySubscription.plan).selectinload(PlatformSubscriptionPlan.entitlements)
        )
        .where(SocietySubscription.society_id == society_id)
    )
    sub = (await session.execute(stmt)).scalar_one_or_none()
    if not sub:
        raise SubscriptionNotFoundException(society_id=society_id)

    # Check for any pending scheduled downgrade in history
    hist_stmt = (
        select(PlatformSubscriptionHistory)
        .where(
            PlatformSubscriptionHistory.society_id == society_id,
            PlatformSubscriptionHistory.transition_reason.like("SCHEDULED_DOWNGRADE%"),
            PlatformSubscriptionHistory.effective_at >= _utc_now(),
        )
        .order_by(PlatformSubscriptionHistory.effective_at.desc())
    )
    pending_hist = (await session.execute(hist_stmt)).scalars().first()

    admin_svc = PlatformBillingAdminService(session)
    plan_resp = admin_svc._plan_to_response(sub.plan)

    return TenantSubscriptionOverview(
        id=sub.id,
        society_id=sub.society_id,
        plan_id=sub.plan_id,
        plan=plan_resp,
        status=sub.status,
        billing_cycle=sub.billing_cycle,
        auto_renew=sub.auto_renew,
        starts_at=sub.starts_at,
        trial_ends_at=sub.trial_ends_at,
        current_period_start=sub.current_period_start,
        current_period_end=sub.current_period_end,
        next_billing_at=sub.next_billing_at,
        past_due_since=sub.past_due_since,
        suspended_at=sub.suspended_at,
        cancelled_at=sub.cancelled_at,
        cancellation_reason=sub.cancellation_reason,
        pending_downgrade_plan_id=pending_hist.new_plan_id if pending_hist else None,
        pending_downgrade_effective_date=pending_hist.effective_at if pending_hist else None,
    )


@router.get(
    "/plans",
    response_model=list[PlatformSubscriptionPlanResponse],
    status_code=status.HTTP_200_OK,
    summary="List Available Subscription Plans",
)
async def list_available_plans(
    auth_ctx: tuple[UUID, User] = Depends(require_billing_read),
    session: AsyncSession = Depends(get_db_session),
) -> list[PlatformSubscriptionPlanResponse]:
    """List all active platform subscription plans with their entitlements and pricing."""
    admin_svc = PlatformBillingAdminService(session)
    return await admin_svc.list_plans(include_archived=False, is_active=True)


@router.get(
    "/subscription/usage",
    response_model=list[TenantUsageMetricItemResponse],
    status_code=status.HTTP_200_OK,
    summary="Get Society Resource Usage & Quotas",
)
async def get_subscription_usage(
    auth_ctx: tuple[UUID, User] = Depends(require_billing_read),
    session: AsyncSession = Depends(get_db_session),
) -> list[TenantUsageMetricItemResponse]:
    """Retrieve real-time usage metrics and quota allocations for this society."""
    society_id, _ = auth_ctx
    quota_svc = QuotaEnforcementService(session)

    stmt = select(SocietyUsageMetric).where(SocietyUsageMetric.society_id == society_id)
    metrics = (await session.execute(stmt)).scalars().all()

    result: list[TenantUsageMetricItemResponse] = []
    for m in metrics:
        diag = await quota_svc.get_usage_diagnostics(society_id=society_id, metric_key=m.metric_key)
        result.append(
            TenantUsageMetricItemResponse(
                metric_key=m.metric_key,
                current_value=m.current_value,
                quota_limit=diag.quota_limit,
                is_unlimited=diag.is_unlimited,
                utilization_percentage=diag.utilization_percentage,
                last_calculated_at=m.last_calculated_at,
            )
        )
    return result


@router.get(
    "/subscription/history",
    response_model=PaginatedResponse[SubscriptionHistoryItemResponse],
    status_code=status.HTTP_200_OK,
    summary="Get Subscription Transition History",
)
async def get_subscription_history(
    auth_ctx: tuple[UUID, User] = Depends(require_billing_read),
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    session: AsyncSession = Depends(get_db_session),
) -> PaginatedResponse[SubscriptionHistoryItemResponse]:
    """Retrieve immutable audit log history of subscription transitions and plan changes."""
    society_id, _ = auth_ctx

    count_stmt = (
        select(func.count())
        .select_from(PlatformSubscriptionHistory)
        .where(PlatformSubscriptionHistory.society_id == society_id)
    )
    total = (await session.execute(count_stmt)).scalar() or 0

    stmt = (
        select(PlatformSubscriptionHistory)
        .where(PlatformSubscriptionHistory.society_id == society_id)
        .order_by(desc(PlatformSubscriptionHistory.effective_at))
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = (await session.execute(stmt)).scalars().all()

    items = [
        SubscriptionHistoryItemResponse(
            id=r.id,
            society_id=r.society_id,
            subscription_id=r.subscription_id,
            previous_plan_id=r.previous_plan_id,
            new_plan_id=r.new_plan_id,
            previous_status=r.previous_status,
            new_status=r.new_status,
            previous_cycle=r.previous_cycle,
            new_cycle=r.new_cycle,
            transition_reason=r.transition_reason,
            changed_by=r.changed_by,
            effective_at=r.effective_at,
        )
        for r in rows
    ]

    pages = (total + page_size - 1) // page_size if total > 0 else 1
    return PaginatedResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
    )


# ==============================================================================
# 2. Plan Change & Lifecycle APIs
# ==============================================================================


@router.post(
    "/subscription/upgrade-preview",
    response_model=UpgradeCalculationResult,
    status_code=status.HTTP_200_OK,
    summary="Preview Subscription Upgrade",
)
async def preview_subscription_upgrade(
    payload: TenantUpgradePreviewRequest,
    auth_ctx: tuple[UUID, User] = Depends(require_billing_read),
    session: AsyncSession = Depends(get_db_session),
) -> UpgradeCalculationResult:
    """Simulate mid-cycle plan upgrade to preview prorated credit and net payable amount."""
    society_id, _ = auth_ctx
    upgrade_svc = SubscriptionUpgradeService(session)
    return await upgrade_svc.calculate_upgrade(
        society_id=society_id,
        target_plan_id=payload.target_plan_id,
    )


@router.post(
    "/subscription/upgrade",
    response_model=UpgradeCalculationResult,
    status_code=status.HTTP_200_OK,
    summary="Execute Subscription Upgrade",
)
async def execute_subscription_upgrade(
    payload: TenantUpgradeExecuteRequest,
    auth_ctx: tuple[UUID, User] = Depends(require_billing_write),
    session: AsyncSession = Depends(get_db_session),
) -> UpgradeCalculationResult:
    """Execute immediate mid-cycle plan upgrade with atomic proration calculation."""
    society_id, current_user = auth_ctx
    upgrade_svc = SubscriptionUpgradeService(session)
    calc = await upgrade_svc.apply_upgrade(
        society_id=society_id,
        target_plan_id=payload.target_plan_id,
        actor_id=str(current_user.id),
        reason="Tenant Self-Service Plan Upgrade",
    )
    await session.commit()
    return calc


@router.post(
    "/subscription/downgrade",
    response_model=ScheduledDowngradeResponse,
    status_code=status.HTTP_200_OK,
    summary="Schedule Plan Downgrade",
)
async def schedule_subscription_downgrade(
    payload: TenantDowngradeRequest,
    auth_ctx: tuple[UUID, User] = Depends(require_billing_write),
    session: AsyncSession = Depends(get_db_session),
) -> ScheduledDowngradeResponse:
    """Schedule a plan downgrade effective at the next billing cycle renewal boundary."""
    society_id, current_user = auth_ctx
    downgrade_svc = SubscriptionDowngradeService(session)
    res = await downgrade_svc.schedule_downgrade(
        society_id=society_id,
        target_plan_id=payload.target_plan_id,
        reason=payload.reason,
        actor_id=current_user.id,
    )
    await session.commit()
    return res


@router.post(
    "/subscription/cancel",
    response_model=TenantSubscriptionOverview,
    status_code=status.HTTP_200_OK,
    summary="Cancel Subscription",
)
async def cancel_subscription(
    payload: TenantSubscriptionCancelRequest,
    auth_ctx: tuple[UUID, User] = Depends(require_billing_write),
    session: AsyncSession = Depends(get_db_session),
) -> TenantSubscriptionOverview:
    """Schedule subscription cancellation at period end by disabling auto-renew."""
    society_id, current_user = auth_ctx

    stmt = (
        select(SocietySubscription)
        .options(
            selectinload(SocietySubscription.plan).selectinload(PlatformSubscriptionPlan.entitlements)
        )
        .where(SocietySubscription.society_id == society_id)
        .with_for_update()
    )
    sub = (await session.execute(stmt)).scalar_one_or_none()
    if not sub:
        raise SubscriptionNotFoundException(society_id=society_id)

    if sub.status == SubscriptionStatus.CANCELLED:
        raise SubscriptionAlreadyCancelledException(society_id=society_id)

    now = _utc_now()
    sub.auto_renew = False
    sub.cancellation_reason = payload.reason

    history = PlatformSubscriptionHistory(
        society_id=society_id,
        subscription_id=sub.id,
        previous_plan_id=sub.plan_id,
        new_plan_id=sub.plan_id,
        previous_status=sub.status,
        new_status=sub.status,
        previous_cycle=sub.billing_cycle,
        new_cycle=sub.billing_cycle,
        transition_reason=f"CANCELLATION_SCHEDULED: {payload.reason}",
        changed_by=current_user.id,
        effective_at=now,
    )
    session.add(history)

    audit = PlatformSubscriptionAuditLog(
        society_id=society_id,
        entity_type="SUBSCRIPTION",
        entity_id=sub.id,
        action="SCHEDULE_CANCELLATION",
        actor_type="USER",
        actor_id=current_user.id,
        before_state={"auto_renew": True},
        after_state={"auto_renew": False, "cancellation_reason": payload.reason},
        created_at=now,
    )
    session.add(audit)
    await session.commit()

    admin_svc = PlatformBillingAdminService(session)
    plan_resp = admin_svc._plan_to_response(sub.plan)

    return TenantSubscriptionOverview(
        id=sub.id,
        society_id=sub.society_id,
        plan_id=sub.plan_id,
        plan=plan_resp,
        status=sub.status,
        billing_cycle=sub.billing_cycle,
        auto_renew=sub.auto_renew,
        starts_at=sub.starts_at,
        trial_ends_at=sub.trial_ends_at,
        current_period_start=sub.current_period_start,
        current_period_end=sub.current_period_end,
        next_billing_at=sub.next_billing_at,
        past_due_since=sub.past_due_since,
        suspended_at=sub.suspended_at,
        cancelled_at=sub.cancelled_at,
        cancellation_reason=sub.cancellation_reason,
    )


@router.post(
    "/subscription/resume",
    response_model=TenantSubscriptionResumeResponse,
    status_code=status.HTTP_200_OK,
    summary="Resume Scheduled Cancellation",
)
async def resume_subscription(
    auth_ctx: tuple[UUID, User] = Depends(require_billing_write),
    session: AsyncSession = Depends(get_db_session),
) -> TenantSubscriptionResumeResponse:
    """Re-enable auto-renew for a subscription scheduled for cancellation."""
    society_id, current_user = auth_ctx

    stmt = (
        select(SocietySubscription)
        .where(SocietySubscription.society_id == society_id)
        .with_for_update()
    )
    sub = (await session.execute(stmt)).scalar_one_or_none()
    if not sub:
        raise SubscriptionNotFoundException(society_id=society_id)

    if sub.status == SubscriptionStatus.CANCELLED:
        raise SubscriptionAlreadyCancelledException(society_id=society_id)

    now = _utc_now()
    sub.auto_renew = True
    sub.cancellation_reason = None

    history = PlatformSubscriptionHistory(
        society_id=society_id,
        subscription_id=sub.id,
        previous_plan_id=sub.plan_id,
        new_plan_id=sub.plan_id,
        previous_status=sub.status,
        new_status=sub.status,
        previous_cycle=sub.billing_cycle,
        new_cycle=sub.billing_cycle,
        transition_reason="RESUME_SUBSCRIPTION: Auto-renew re-enabled by user",
        changed_by=current_user.id,
        effective_at=now,
    )
    session.add(history)

    audit = PlatformSubscriptionAuditLog(
        society_id=society_id,
        entity_type="SUBSCRIPTION",
        entity_id=sub.id,
        action="RESUME_SUBSCRIPTION",
        actor_type="USER",
        actor_id=current_user.id,
        before_state={"auto_renew": False},
        after_state={"auto_renew": True},
        created_at=now,
    )
    session.add(audit)
    await session.commit()

    return TenantSubscriptionResumeResponse(
        society_id=society_id,
        subscription_id=sub.id,
        status=sub.status,
        auto_renew=True,
        message="Subscription auto-renew successfully re-enabled.",
    )


# ==============================================================================
# 3. Platform Invoices APIs
# ==============================================================================


@router.get(
    "/invoices",
    response_model=PaginatedResponse[PlatformInvoiceResponse],
    status_code=status.HTTP_200_OK,
    summary="List Tenant Invoices",
)
async def list_tenant_invoices(
    auth_ctx: tuple[UUID, User] = Depends(require_billing_read),
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    session: AsyncSession = Depends(get_db_session),
) -> PaginatedResponse[PlatformInvoiceResponse]:
    """List invoices strictly scoped to the tenant society."""
    society_id, _ = auth_ctx

    count_stmt = select(func.count()).select_from(PlatformInvoice).where(
        PlatformInvoice.society_id == society_id
    )
    if status_filter:
        count_stmt = count_stmt.where(PlatformInvoice.status == status_filter.upper())
    total = (await session.execute(count_stmt)).scalar() or 0

    stmt = (
        select(PlatformInvoice)
        .options(selectinload(PlatformInvoice.items))
        .where(PlatformInvoice.society_id == society_id)
    )
    if status_filter:
        stmt = stmt.where(PlatformInvoice.status == status_filter.upper())

    stmt = stmt.order_by(desc(PlatformInvoice.issued_at)).offset((page - 1) * page_size).limit(page_size)
    invoices = (await session.execute(stmt)).scalars().all()

    pages = (total + page_size - 1) // page_size if total > 0 else 1
    return PaginatedResponse(
        items=[PlatformInvoiceResponse.model_validate(inv) for inv in invoices],
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
    )


@router.get(
    "/invoices/{invoice_id}",
    response_model=PlatformInvoiceResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Tenant Invoice Details",
)
async def get_tenant_invoice_details(
    invoice_id: UUID,
    auth_ctx: tuple[UUID, User] = Depends(require_billing_read),
    session: AsyncSession = Depends(get_db_session),
) -> PlatformInvoiceResponse:
    """Retrieve itemized details of an invoice belonging to this society."""
    society_id, _ = auth_ctx
    stmt = (
        select(PlatformInvoice)
        .options(selectinload(PlatformInvoice.items))
        .where(
            PlatformInvoice.id == invoice_id,
            PlatformInvoice.society_id == society_id,
        )
    )
    inv = (await session.execute(stmt)).scalar_one_or_none()
    if not inv:
        raise NotFoundException(f"Invoice '{invoice_id}' not found for society.")
    return PlatformInvoiceResponse.model_validate(inv)


@router.get(
    "/invoices/{invoice_id}/pdf",
    status_code=status.HTTP_200_OK,
    summary="Download Invoice PDF",
    response_class=Response,
)
async def download_tenant_invoice_pdf(
    invoice_id: UUID,
    auth_ctx: tuple[UUID, User] = Depends(require_billing_read),
    session: AsyncSession = Depends(get_db_session),
) -> Response:
    """Stream immutable binary PDF for a finalized invoice."""
    society_id, _ = auth_ctx
    doc_svc = PlatformBillingDocumentService()
    doc, pdf_bytes = await doc_svc.get_or_generate_invoice_document(
        session=session,
        invoice_id=invoice_id,
        caller_society_id=society_id,
    )
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="{doc.document_number}.pdf"',
            "X-Document-Checksum": doc.sha256_checksum,
        },
    )


@router.get(
    "/invoices/{invoice_id}/download-url",
    response_model=PlatformDocumentDownloadUrlResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Invoice Presigned Download URL",
)
async def get_tenant_invoice_download_url(
    invoice_id: UUID,
    auth_ctx: tuple[UUID, User] = Depends(require_billing_read),
    expires_in_seconds: Annotated[int, Query(ge=60, le=300)] = 300,
    session: AsyncSession = Depends(get_db_session),
) -> PlatformDocumentDownloadUrlResponse:
    """Generate a short-lived presigned download URL for an invoice PDF."""
    society_id, _ = auth_ctx
    doc_svc = PlatformBillingDocumentService()
    return await doc_svc.get_invoice_download_url(
        session=session,
        invoice_id=invoice_id,
        caller_society_id=society_id,
        expires_in_seconds=expires_in_seconds,
    )


@router.post(
    "/invoices/{invoice_id}/send-email",
    response_model=PlatformDocumentDeliveryResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Send Invoice Email",
)
async def send_tenant_invoice_email(
    invoice_id: UUID,
    payload: PlatformDocumentEmailRequest | None = None,
    auth_ctx: tuple[UUID, User] = Depends(require_billing_write),
    session: AsyncSession = Depends(get_db_session),
) -> PlatformDocumentDeliveryResponse:
    """Queue reliable email dispatch for an invoice to the billing contact."""
    society_id, _ = auth_ctx
    doc_svc = PlatformBillingDocumentService()
    delivery = await doc_svc.send_invoice_email(
        session=session,
        invoice_id=invoice_id,
        caller_society_id=society_id,
        payload=payload,
    )
    await session.commit()
    return delivery


@router.post(
    "/invoices/{invoice_id}/checkout",
    response_model=TenantCheckoutResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Checkout Payment Order",
)
async def create_invoice_checkout_order(
    invoice_id: UUID,
    payload: TenantCheckoutRequest | None = None,
    auth_ctx: tuple[UUID, User] = Depends(require_billing_write),
    session: AsyncSession = Depends(get_db_session),
) -> TenantCheckoutResponse:
    """Initialize an authoritative server-side checkout payment order."""
    society_id, _ = auth_ctx
    order_svc = PaymentOrderService(session)
    provider = payload.provider if payload else "RAZORPAY"
    idempotency_key = payload.idempotency_key if payload else None

    order_resp = await order_svc.create_payment_order(
        society_id=society_id,
        invoice_id=invoice_id,
        idempotency_key=idempotency_key,
        provider_name=provider,
    )
    await session.commit()

    return TenantCheckoutResponse(
        order_id=order_resp.order_id,
        invoice_id=order_resp.invoice_id,
        amount=order_resp.amount,
        currency=order_resp.currency_code,
        gateway_provider=order_resp.gateway_provider,
        key_id=order_resp.key_id,
    )


# ==============================================================================
# 4. Platform Credit Notes APIs
# ==============================================================================


@router.get(
    "/credit-notes",
    response_model=PaginatedResponse[PlatformCreditNoteResponse],
    status_code=status.HTTP_200_OK,
    summary="List Tenant Credit Notes",
)
async def list_tenant_credit_notes(
    auth_ctx: tuple[UUID, User] = Depends(require_billing_read),
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    session: AsyncSession = Depends(get_db_session),
) -> PaginatedResponse[PlatformCreditNoteResponse]:
    """List credit notes strictly scoped to this tenant society."""
    society_id, _ = auth_ctx

    count_stmt = select(func.count()).select_from(PlatformCreditNote).where(
        PlatformCreditNote.society_id == society_id
    )
    if status_filter:
        count_stmt = count_stmt.where(PlatformCreditNote.status == status_filter.upper())
    total = (await session.execute(count_stmt)).scalar() or 0

    stmt = (
        select(PlatformCreditNote)
        .options(selectinload(PlatformCreditNote.items))
        .where(PlatformCreditNote.society_id == society_id)
    )
    if status_filter:
        stmt = stmt.where(PlatformCreditNote.status == status_filter.upper())

    stmt = stmt.order_by(desc(PlatformCreditNote.created_at)).offset((page - 1) * page_size).limit(page_size)
    cns = (await session.execute(stmt)).scalars().all()

    pages = (total + page_size - 1) // page_size if total > 0 else 1
    return PaginatedResponse(
        items=[PlatformCreditNoteResponse.model_validate(cn) for cn in cns],
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
    )


@router.get(
    "/credit-notes/{credit_note_id}",
    response_model=PlatformCreditNoteResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Credit Note Details",
)
async def get_tenant_credit_note_details(
    credit_note_id: UUID,
    auth_ctx: tuple[UUID, User] = Depends(require_billing_read),
    session: AsyncSession = Depends(get_db_session),
) -> PlatformCreditNoteResponse:
    """Retrieve itemized details of a credit note belonging to this society."""
    society_id, _ = auth_ctx
    stmt = (
        select(PlatformCreditNote)
        .options(selectinload(PlatformCreditNote.items))
        .where(
            PlatformCreditNote.id == credit_note_id,
            PlatformCreditNote.society_id == society_id,
        )
    )
    cn = (await session.execute(stmt)).scalar_one_or_none()
    if not cn:
        raise NotFoundException(f"Credit note '{credit_note_id}' not found for society.")
    return PlatformCreditNoteResponse.model_validate(cn)


@router.get(
    "/credit-notes/{credit_note_id}/pdf",
    status_code=status.HTTP_200_OK,
    summary="Download Credit Note PDF",
    response_class=Response,
)
async def download_tenant_credit_note_pdf(
    credit_note_id: UUID,
    auth_ctx: tuple[UUID, User] = Depends(require_billing_read),
    session: AsyncSession = Depends(get_db_session),
) -> Response:
    """Stream immutable binary PDF for a finalized credit note."""
    society_id, _ = auth_ctx
    doc_svc = PlatformBillingDocumentService()
    doc, pdf_bytes = await doc_svc.get_or_generate_credit_note_document(
        session=session,
        credit_note_id=credit_note_id,
        caller_society_id=society_id,
    )
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="{doc.document_number}.pdf"',
            "X-Document-Checksum": doc.sha256_checksum,
        },
    )


@router.get(
    "/credit-notes/{credit_note_id}/download-url",
    response_model=PlatformDocumentDownloadUrlResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Credit Note Presigned Download URL",
)
async def get_tenant_credit_note_download_url(
    credit_note_id: UUID,
    auth_ctx: tuple[UUID, User] = Depends(require_billing_read),
    expires_in_seconds: Annotated[int, Query(ge=60, le=300)] = 300,
    session: AsyncSession = Depends(get_db_session),
) -> PlatformDocumentDownloadUrlResponse:
    """Generate a short-lived presigned download URL for a credit note PDF."""
    society_id, _ = auth_ctx
    doc_svc = PlatformBillingDocumentService()
    return await doc_svc.get_credit_note_download_url(
        session=session,
        credit_note_id=credit_note_id,
        caller_society_id=society_id,
        expires_in_seconds=expires_in_seconds,
    )


@router.post(
    "/credit-notes/{credit_note_id}/send-email",
    response_model=PlatformDocumentDeliveryResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Send Credit Note Email",
)
async def send_tenant_credit_note_email(
    credit_note_id: UUID,
    payload: PlatformDocumentEmailRequest | None = None,
    auth_ctx: tuple[UUID, User] = Depends(require_billing_write),
    session: AsyncSession = Depends(get_db_session),
) -> PlatformDocumentDeliveryResponse:
    """Queue reliable email dispatch for a credit note."""
    society_id, _ = auth_ctx
    doc_svc = PlatformBillingDocumentService()
    delivery = await doc_svc.send_credit_note_email(
        session=session,
        credit_note_id=credit_note_id,
        caller_society_id=society_id,
        payload=payload,
    )
    await session.commit()
    return delivery


# ==============================================================================
# 5. Gateway Payments APIs
# ==============================================================================


@router.post(
    "/payments/verify",
    response_model=PaymentVerificationResponse,
    status_code=status.HTTP_200_OK,
    summary="Verify Payment & Settle Invoice",
)
async def verify_tenant_payment(
    payload: TenantPaymentVerifyRequest,
    auth_ctx: tuple[UUID, User] = Depends(require_billing_write),
    session: AsyncSession = Depends(get_db_session),
) -> PaymentVerificationResponse:
    """Verify cryptographic checkout signature, check provider status, and settle payment."""
    society_id, _ = auth_ctx
    verif_svc = PaymentVerificationService(session)

    res = await verif_svc.verify_and_settle(
        society_id=society_id,
        invoice_id=payload.invoice_id,
        gateway_order_id=payload.gateway_order_id,
        gateway_payment_id=payload.gateway_payment_id,
        signature=payload.signature,
        provider_name=payload.provider,
    )
    await session.commit()
    return res


@router.get(
    "/payments",
    response_model=PaginatedResponse[PlatformPaymentListItemResponse],
    status_code=status.HTTP_200_OK,
    summary="List Tenant Payments",
)
async def list_tenant_payments(
    auth_ctx: tuple[UUID, User] = Depends(require_billing_read),
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    session: AsyncSession = Depends(get_db_session),
) -> PaginatedResponse[PlatformPaymentListItemResponse]:
    """List captured payment transactions for this tenant society."""
    society_id, _ = auth_ctx

    count_stmt = select(func.count()).select_from(PlatformPayment).where(
        PlatformPayment.society_id == society_id
    )
    if status_filter:
        count_stmt = count_stmt.where(PlatformPayment.status == status_filter.upper())
    total = (await session.execute(count_stmt)).scalar() or 0

    stmt = select(PlatformPayment).where(PlatformPayment.society_id == society_id)
    if status_filter:
        stmt = stmt.where(PlatformPayment.status == status_filter.upper())

    stmt = stmt.order_by(desc(PlatformPayment.captured_at)).offset((page - 1) * page_size).limit(page_size)
    payments = (await session.execute(stmt)).scalars().all()

    pages = (total + page_size - 1) // page_size if total > 0 else 1
    return PaginatedResponse(
        items=[PlatformPaymentListItemResponse.model_validate(p) for p in payments],
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
    )


# ==============================================================================
# 6. Advance Balance & Delivery Tracking APIs
# ==============================================================================


@router.get(
    "/balance",
    response_model=SocietyAdvanceBalanceResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Tenant Advance Balance",
)
async def get_tenant_advance_balance(
    auth_ctx: tuple[UUID, User] = Depends(require_billing_read),
    session: AsyncSession = Depends(get_db_session),
) -> SocietyAdvanceBalanceResponse:
    """Retrieve current credit balance, total granted, and total utilized for this society."""
    society_id, _ = auth_ctx
    admin_svc = PlatformBillingAdminService(session)
    return await admin_svc.get_society_advance_balance(society_id)


@router.get(
    "/balance/transactions",
    response_model=PaginatedResponse[PlatformBillingAdjustmentResponse],
    status_code=status.HTTP_200_OK,
    summary="Get Credit Balance Transactions",
)
async def list_tenant_balance_transactions(
    auth_ctx: tuple[UUID, User] = Depends(require_billing_read),
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    session: AsyncSession = Depends(get_db_session),
) -> PaginatedResponse[PlatformBillingAdjustmentResponse]:
    """Retrieve billing adjustments and credits ledger for this society."""
    society_id, _ = auth_ctx
    admin_svc = PlatformBillingAdminService(session)
    return await admin_svc.list_adjustments(society_id=society_id, page=page, page_size=page_size)


@router.get(
    "/documents/{document_id}/deliveries",
    response_model=list[PlatformDocumentDeliveryResponse],
    status_code=status.HTTP_200_OK,
    summary="Get Document Delivery History",
)
async def get_tenant_document_deliveries(
    document_id: UUID,
    auth_ctx: tuple[UUID, User] = Depends(require_billing_read),
    session: AsyncSession = Depends(get_db_session),
) -> list[PlatformDocumentDeliveryResponse]:
    """Retrieve delivery history and attempt logs for a document belonging to this society."""
    society_id, _ = auth_ctx
    doc_svc = PlatformBillingDocumentService()
    return await doc_svc.list_document_deliveries(
        session=session,
        document_id=document_id,
        caller_society_id=society_id,
    )
