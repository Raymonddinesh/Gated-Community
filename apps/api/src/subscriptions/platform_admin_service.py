"""Phase 21D — SaaS Platform Administration Domain Service.

Centralized domain service for platform-level management of tenant societies:
- Directory search, filtering, and pagination.
- Detailed society inspection with subscription & primary admin metadata.
- Independent lifecycle state transitions (suspend, reactivate) with FOR UPDATE row locks.
- Consolidated subscription, entitlement, and quota overview integrating Phase 21B services.
- Step-by-step provisioning diagnostics enforcing tenant RLS context.
- Safe, concurrency-guarded provisioning retry delegating to SocietyProvisioningEngine.
"""

import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from apps.api.src.core.exceptions import NotFoundException
from apps.api.src.core.tenant_context import tenant_context
from apps.api.src.database.models.audit import AuditLog
from apps.api.src.database.models.authorization import Role, RoleAssignment
from apps.api.src.database.models.identity import User
from apps.api.src.database.models.society import Society
from apps.api.src.database.models.subscription import (
    SocietyProvisioningLog,
    SocietySubscription,
)
from apps.api.src.database.session import set_db_tenant_context
from apps.api.src.subscriptions.entitlement_service import EntitlementService
from apps.api.src.subscriptions.enums import FeatureKey, QuotaKey
from apps.api.src.subscriptions.exceptions import (
    ProvisioningConflictException,
    ProvisioningRetryIneligibleException,
    SocietyAlreadyActiveException,
    SocietyAlreadySuspendedException,
    SocietyLifecycleValidationException,
    SubscriptionNotFoundException,
)
from apps.api.src.subscriptions.provisioning_engine import (
    SocietyProvisioningEngine,
    _lock_key_to_int,
)
from apps.api.src.subscriptions.quota_enforcement_service import QuotaEnforcementService
from apps.api.src.subscriptions.schemas import (
    EffectiveEntitlement,
    EffectiveQuota,
    ProvisioningStepLogResponse,
    ProvisionSocietyRequest,
    ProvisionSocietyResponse,
    SocietyAdminDetailResponse,
    SocietyDirectoryItemResponse,
    SocietyDirectoryResponse,
    SocietyLifecycleActionResponse,
    SocietyPrimaryAdminResponse,
    SocietyProvisioningDiagnosticsResponse,
    SocietySubscriptionBriefResponse,
    SocietySubscriptionOverviewResponse,
)

logger = logging.getLogger("societysphere.subscriptions.platform_admin")


def _utc_now() -> datetime:
    """Normalize timestamp to naive UTC for consistent PostgreSQL comparison."""
    return datetime.now(UTC).replace(tzinfo=None)


def _mask_email(email: str | None) -> str | None:
    """Mask email address for privacy (e.g. j***e@example.com)."""
    if not email or "@" not in email:
        return email
    local_part, domain = email.split("@", 1)
    if len(local_part) <= 2:
        masked_local = local_part[0] + "*"
    else:
        masked_local = local_part[0] + "*" * (len(local_part) - 2) + local_part[-1]
    return f"{masked_local}@{domain}"


def _mask_phone(phone: str | None) -> str | None:
    """Mask telephone number for privacy (e.g. +91 ******7890)."""
    if not phone or len(phone) < 6:
        return phone
    prefix = phone[:3]
    suffix = phone[-4:]
    masked_count = max(len(phone) - 7, 2)
    return f"{prefix}{'*' * masked_count}{suffix}"


class PlatformAdminService:
    """Domain service orchestrating administrative management of societies."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ==========================================================================
    # 1. Society Directory & Inspection
    # ==========================================================================

    async def list_societies(
        self,
        search: str | None = None,
        status: str | None = None,
        onboarding_status: str | None = None,
        state: str | None = None,
        city: str | None = None,
        page: int = 1,
        page_size: int = 20,
        sort_by: str = "created_at",
        sort_order: str = "desc",
    ) -> SocietyDirectoryResponse:
        """Query and paginate societies from global database records with filtering."""
        base_query = select(Society).where(Society.archived_at.is_(None))

        # Filtering
        if search:
            search_term = f"%{search.strip().lower()}%"
            base_query = base_query.where(
                or_(
                    func.lower(Society.legal_name).like(search_term),
                    func.lower(Society.display_name).like(search_term),
                    func.lower(Society.registration_number).like(search_term),
                )
            )

        if status:
            base_query = base_query.where(Society.status == status.upper())

        if onboarding_status:
            base_query = base_query.where(Society.onboarding_status == onboarding_status.upper())

        if state:
            base_query = base_query.where(func.lower(Society.state) == state.strip().lower())

        if city:
            base_query = base_query.where(func.lower(Society.city) == city.strip().lower())

        # Total count query
        count_stmt = select(func.count()).select_from(base_query.subquery())
        total_res = await self.session.execute(count_stmt)
        total = total_res.scalar_one() or 0

        # Sorting
        sort_col = getattr(Society, sort_by, Society.created_at)
        if sort_order.lower() == "asc":
            base_query = base_query.order_by(sort_col.asc())
        else:
            base_query = base_query.order_by(sort_col.desc())

        # Pagination
        offset = (page - 1) * page_size
        paged_query = base_query.offset(offset).limit(page_size)
        result = await self.session.execute(paged_query)
        societies = list(result.scalars().all())

        pages = (total + page_size - 1) // page_size if total > 0 else 0

        items = [
            SocietyDirectoryItemResponse(
                id=s.id,
                legal_name=s.legal_name,
                display_name=s.display_name,
                registration_number=s.registration_number,
                city=s.city,
                state=s.state,
                country=s.country,
                postal_code=s.postal_code,
                status=s.status,
                onboarding_status=s.onboarding_status,
                plan_code=None,
                subscription_status=None,
                created_at=s.created_at,
                updated_at=s.updated_at,
            )
            for s in societies
        ]

        return SocietyDirectoryResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            pages=pages,
        )

    async def get_society_detail(
        self,
        society_id: UUID,
    ) -> SocietyAdminDetailResponse:
        """Retrieve comprehensive society metadata, subscription details, and primary admin info."""
        society = await self.session.get(Society, society_id)
        if not society or society.archived_at is not None:
            raise NotFoundException(f"Society with ID '{society_id}' does not exist.")

        subscription_brief: SocietySubscriptionBriefResponse | None = None
        primary_admin: SocietyPrimaryAdminResponse | None = None

        # Enter tenant context to safely access tenant-scoped tables
        async with tenant_context(society_id):
            await set_db_tenant_context(self.session, society_id)

            # Query subscription
            sub_stmt = (
                select(SocietySubscription)
                .options(selectinload(SocietySubscription.plan))
                .where(SocietySubscription.society_id == society_id)
            )
            sub_res = await self.session.execute(sub_stmt)
            sub = sub_res.scalar_one_or_none()

            if sub and sub.plan:
                subscription_brief = SocietySubscriptionBriefResponse(
                    plan_code=sub.plan.plan_code,
                    plan_name=sub.plan.display_name,
                    status=sub.status,
                    starts_at=sub.starts_at,
                    trial_ends_at=sub.trial_ends_at,
                    current_period_end=sub.current_period_end,
                    past_due_since=sub.past_due_since,
                    suspended_at=sub.suspended_at,
                    cancelled_at=sub.cancelled_at,
                )

            # Query primary admin
            admin_stmt = (
                select(User)
                .join(RoleAssignment, User.id == RoleAssignment.user_id)
                .join(Role, RoleAssignment.role_id == Role.id)
                .where(
                    RoleAssignment.society_id == society_id,
                    Role.code == "SOCIETY_ADMIN",
                    RoleAssignment.status == "ACTIVE",
                )
                .limit(1)
            )
            admin_res = await self.session.execute(admin_stmt)
            admin_user = admin_res.scalar_one_or_none()

            if admin_user:
                primary_admin = SocietyPrimaryAdminResponse(
                    user_id=admin_user.id,
                    name=f"{admin_user.first_name} {admin_user.last_name}".strip(),
                    email_masked=_mask_email(admin_user.email),
                    phone_masked=_mask_phone(admin_user.phone),
                    status=admin_user.status,
                )

        return SocietyAdminDetailResponse(
            id=society.id,
            legal_name=society.legal_name,
            display_name=society.display_name,
            registration_number=society.registration_number,
            address_line1=society.address_line1,
            address_line2=society.address_line2,
            city=society.city,
            state=society.state,
            country=society.country,
            postal_code=society.postal_code,
            timezone=society.timezone,
            default_language=society.default_language,
            status=society.status,
            onboarding_status=society.onboarding_status,
            created_at=society.created_at,
            updated_at=society.updated_at,
            archived_at=society.archived_at,
            subscription=subscription_brief,
            primary_admin=primary_admin,
        )

    # ==========================================================================
    # 2. Independent Lifecycle State Transitions (Mandatory Condition 2)
    # ==========================================================================

    async def suspend_society(
        self,
        society_id: UUID,
        actor_user_id: UUID,
        reason: str,
        notes: str | None = None,
        correlation_id: str | None = None,
    ) -> SocietyLifecycleActionResponse:
        """Administratively suspend a society using pessimistic row locking.

        Invariants:
        - Validates reason >= 10 non-whitespace characters.
        - Acquires SELECT FOR UPDATE row lock on societies.
        - Rejects duplicate suspension (409 Conflict).
        - Rejects archived society (400 Bad Request).
        - Transitions Society.status = 'SUSPENDED'.
        - STRICT DECOUPLING: Does NOT alter SocietySubscription.status.
        - Records suspended_at on subscription if present without corrupting commercial state.
        - Emits immutable AuditLog record.
        """
        clean_reason = reason.strip()
        if len(clean_reason) < 10:
            raise SocietyLifecycleValidationException(
                "Administrative suspension reason must be at least 10 non-whitespace characters."
            )

        # 1. Acquire pessimistic row lock on Society
        stmt = select(Society).where(Society.id == society_id).with_for_update()
        res = await self.session.execute(stmt)
        society = res.scalar_one_or_none()

        if not society:
            raise NotFoundException(f"Society with ID '{society_id}' does not exist.")

        if society.archived_at is not None:
            raise SocietyLifecycleValidationException("Cannot suspend an archived society.")

        if society.status == "SUSPENDED":
            raise SocietyAlreadySuspendedException(society_id=society_id)

        previous_status = society.status
        society.status = "SUSPENDED"
        society.updated_at = _utc_now()

        # 2. Update subscription suspended_at timestamp under tenant context
        sub_status_val: str | None = None
        async with tenant_context(society_id):
            await set_db_tenant_context(self.session, society_id)

            sub_stmt = (
                select(SocietySubscription)
                .where(SocietySubscription.society_id == society_id)
                .with_for_update()
            )
            sub_res = await self.session.execute(sub_stmt)
            subscription = sub_res.scalar_one_or_none()

            if subscription:
                subscription.suspended_at = _utc_now()
                subscription.updated_at = _utc_now()
                sub_status_val = subscription.status

            # 3. Write immutable audit log entry
            audit = AuditLog(
                society_id=society_id,
                actor_user_id=actor_user_id,
                action="SOCIETY_SUSPENDED",
                entity_type="society",
                entity_id=str(society_id),
                correlation_id=correlation_id,
                before_state={"status": previous_status},
                after_state={
                    "status": "SUSPENDED",
                    "reason": clean_reason,
                    "notes": notes,
                    "subscription_status": sub_status_val,
                },
                diff={"status": {"before": previous_status, "after": "SUSPENDED"}},
            )
            self.session.add(audit)

        await self.session.commit()

        return SocietyLifecycleActionResponse(
            society_id=society_id,
            previous_status=previous_status,
            current_status="SUSPENDED",
            reason=clean_reason,
            actor_user_id=actor_user_id,
            executed_at=_utc_now(),
            subscription_status=sub_status_val,
        )

    async def reactivate_society(
        self,
        society_id: UUID,
        actor_user_id: UUID,
        reason: str,
        notes: str | None = None,
        correlation_id: str | None = None,
    ) -> SocietyLifecycleActionResponse:
        """Administratively reactivate a suspended society using pessimistic row locking.

        Invariants:
        - Validates reason >= 10 non-whitespace characters.
        - Acquires SELECT FOR UPDATE row lock on societies.
        - Rejects duplicate reactivation (409 Conflict).
        - Rejects archived society (400 Bad Request).
        - Requires society to be in SUSPENDED status (400 Bad Request if not).
        - Transitions Society.status = 'ACTIVE'.
        - STRICT DECOUPLING: Does NOT alter commercial subscription status!
          Reactivating a society NEVER automatically reactivates a CANCELLED subscription
          or clears PAST_DUE restrictions.
        - Clears suspended_at on subscription if present.
        - Emits immutable AuditLog record.
        """
        clean_reason = reason.strip()
        if len(clean_reason) < 10:
            raise SocietyLifecycleValidationException(
                "Administrative reactivation reason must be at least 10 non-whitespace characters."
            )

        # 1. Acquire pessimistic row lock on Society
        stmt = select(Society).where(Society.id == society_id).with_for_update()
        res = await self.session.execute(stmt)
        society = res.scalar_one_or_none()

        if not society:
            raise NotFoundException(f"Society with ID '{society_id}' does not exist.")

        if society.archived_at is not None:
            raise SocietyLifecycleValidationException("Cannot reactivate an archived society.")

        if society.status == "ACTIVE":
            raise SocietyAlreadyActiveException(society_id=society_id)

        if society.status != "SUSPENDED":
            raise SocietyLifecycleValidationException(
                f"Cannot reactivate society with current status '{society.status}'. Must be in SUSPENDED status."
            )

        previous_status = society.status
        society.status = "ACTIVE"
        society.updated_at = _utc_now()

        # 2. Update subscription under tenant context without changing commercial state
        sub_status_val: str | None = None
        async with tenant_context(society_id):
            await set_db_tenant_context(self.session, society_id)

            sub_stmt = (
                select(SocietySubscription)
                .where(SocietySubscription.society_id == society_id)
                .with_for_update()
            )
            sub_res = await self.session.execute(sub_stmt)
            subscription = sub_res.scalar_one_or_none()

            if subscription:
                subscription.suspended_at = None
                subscription.updated_at = _utc_now()
                sub_status_val = subscription.status
                # CRITICAL: We preserve the exact commercial subscription status!
                # CANCELLED remains CANCELLED; PAST_DUE remains PAST_DUE!

            # 3. Write immutable audit log entry
            audit = AuditLog(
                society_id=society_id,
                actor_user_id=actor_user_id,
                action="SOCIETY_REACTIVATED",
                entity_type="society",
                entity_id=str(society_id),
                correlation_id=correlation_id,
                before_state={"status": previous_status},
                after_state={
                    "status": "ACTIVE",
                    "reason": clean_reason,
                    "notes": notes,
                    "subscription_status": sub_status_val,
                },
                diff={"status": {"before": previous_status, "after": "ACTIVE"}},
            )
            self.session.add(audit)

        await self.session.commit()

        return SocietyLifecycleActionResponse(
            society_id=society_id,
            previous_status=previous_status,
            current_status="ACTIVE",
            reason=clean_reason,
            actor_user_id=actor_user_id,
            executed_at=_utc_now(),
            subscription_status=sub_status_val,
        )

    # ==========================================================================
    # 3. Subscription & Quota Overview (Phase 21B Integration)
    # ==========================================================================

    async def get_subscription_overview(
        self,
        society_id: UUID,
    ) -> SocietySubscriptionOverviewResponse:
        """Consolidated subscription, feature entitlement, and quota usage overview.

        Directly delegates to Phase 21B EntitlementService and QuotaEnforcementService
        within a properly scoped tenant context.
        """
        society = await self.session.get(Society, society_id)
        if not society or society.archived_at is not None:
            raise NotFoundException(f"Society with ID '{society_id}' does not exist.")

        async with tenant_context(society_id):
            await set_db_tenant_context(self.session, society_id)

            sub_stmt = (
                select(SocietySubscription)
                .options(selectinload(SocietySubscription.plan))
                .where(SocietySubscription.society_id == society_id)
            )
            sub_res = await self.session.execute(sub_stmt)
            subscription = sub_res.scalar_one_or_none()

            if not subscription or not subscription.plan:
                raise SubscriptionNotFoundException(society_id=society_id)

            # Delegate feature evaluation to Phase 21B EntitlementService
            entitlement_svc = EntitlementService(self.session)
            feature_keys = [
                FeatureKey.GOVERNANCE,
                FeatureKey.FACILITY_BOOKING,
                FeatureKey.MAINTENANCE_BILLING,
                FeatureKey.VISITOR_MANAGEMENT,
                FeatureKey.VEHICLE_TRACKING,
                FeatureKey.ACCOUNTING_ADVANCED,
                FeatureKey.EMERGENCY_MANAGEMENT,
                FeatureKey.VENDOR_MANAGEMENT,
            ]
            features: list[EffectiveEntitlement] = []
            for f_key in feature_keys:
                ent = await entitlement_svc.get_effective_entitlement(society_id, f_key)
                features.append(ent)

            # Delegate quota evaluation to Phase 21B QuotaEnforcementService
            quota_svc = QuotaEnforcementService(self.session)
            quota_keys = [
                QuotaKey.UNITS_MAX,
                QuotaKey.RESIDENTS_MAX,
                QuotaKey.STAFF_MAX,
                QuotaKey.STORAGE_BYTES_MAX,
            ]
            quotas: list[EffectiveQuota] = []
            for q_key in quota_keys:
                q = await quota_svc.get_effective_quota(society_id, q_key)
                quotas.append(q)

            return SocietySubscriptionOverviewResponse(
                society_id=society.id,
                plan_code=subscription.plan.plan_code,
                plan_name=subscription.plan.display_name,
                subscription_status=subscription.status,
                starts_at=subscription.starts_at,
                trial_ends_at=subscription.trial_ends_at,
                current_period_end=subscription.current_period_end,
                features=features,
                quotas=quotas,
            )

    # ==========================================================================
    # 4. Provisioning Diagnostics (Mandatory Condition 1: FORCE RLS Compliance)
    # ==========================================================================

    async def get_provisioning_diagnostics(
        self,
        society_id: UUID,
    ) -> SocietyProvisioningDiagnosticsResponse:
        """Retrieve step-by-step provisioning logs and failure diagnostics under FORCE RLS.

        Enforces tenant context using transaction-scoped set_config, guaranteeing
        compliance with FORCE ROW LEVEL SECURITY on society_provisioning_logs.
        """
        society = await self.session.get(Society, society_id)
        if not society:
            raise NotFoundException(f"Society with ID '{society_id}' does not exist.")

        # Establish tenant context for FORCE ROW LEVEL SECURITY on society_provisioning_logs
        async with tenant_context(society_id):
            await set_db_tenant_context(self.session, society_id)

            stmt = (
                select(SocietyProvisioningLog)
                .where(SocietyProvisioningLog.society_id == society_id)
                .order_by(SocietyProvisioningLog.started_at.asc())
            )
            result = await self.session.execute(stmt)
            logs = list(result.scalars().all())

        # If no tenant-scoped logs exist (e.g. failure before BIND_TENANT_RLS or rolled back),
        # query platform-level audit logs for the failure details
        last_failure: dict[str, Any] | None = None
        if not logs:
            audit_stmt = (
                select(AuditLog)
                .where(
                    AuditLog.entity_id == str(society_id),
                    AuditLog.action.in_(["PROVISIONING_FAILED", "SOCIETY_PROVISIONED"]),
                )
                .order_by(AuditLog.created_at.desc())
                .limit(1)
            )
            audit_res = await self.session.execute(audit_stmt)
            prior_audit = audit_res.scalar_one_or_none()
            if prior_audit and prior_audit.after_state:
                last_failure = prior_audit.after_state

        is_retryable = society.onboarding_status in ("FAILED", "IN_PROGRESS")

        return SocietyProvisioningDiagnosticsResponse(
            society_id=society.id,
            onboarding_status=society.onboarding_status,
            is_retryable=is_retryable,
            steps=[
                ProvisioningStepLogResponse(
                    step_key=log.step_key,
                    status=log.status,
                    started_at=log.started_at,
                    completed_at=log.completed_at,
                    message=log.message,
                )
                for log in logs
            ],
            last_failure=last_failure,
        )

    # ==========================================================================
    # 5. Concurrency-Safe Provisioning Retry (Mandatory Condition 3)
    # ==========================================================================

    async def _try_acquire_advisory_lock(self, lock_key_str: str, resource_name: str) -> None:
        """Acquire non-blocking transaction-scoped advisory lock if running on PostgreSQL."""
        bind = self.session.bind
        if bind and getattr(bind, "dialect", None) and bind.dialect.name == "postgresql":
            lock_id = _lock_key_to_int(lock_key_str)
            result = await self.session.execute(
                text("SELECT pg_try_advisory_xact_lock(:lock_id)"),
                {"lock_id": lock_id},
            )
            acquired = result.scalar()
            if not acquired:
                await self.session.rollback()
                raise ProvisioningConflictException(
                    message=f"A provisioning request for {resource_name} is currently in progress. Please retry after several seconds.",
                    details={
                        "code": "PROVISIONING_IN_PROGRESS",
                        "resource": resource_name,
                        "retry_after_seconds": 5,
                    },
                    headers={"Retry-After": "5"},
                )

    async def retry_provisioning(
        self,
        society_id: UUID,
        current_user_id: UUID,
        correlation_id: str | None = None,
        override_request: ProvisionSocietyRequest | None = None,
    ) -> ProvisionSocietyResponse:
        """Retry a failed or incomplete provisioning request safely.

        Reuses SocietyProvisioningEngine and advisory lock concurrency controls.
        Guarantees:
        - Rejects retry if onboarding is already COMPLETED (409 Conflict).
        - Prevents concurrent in-progress execution via pg_try_advisory_xact_lock (409 Conflict, Retry-After: 5).
        - Executes all steps in a single atomic transaction with complete rollback on error.
        - Prevents duplicate societies, subscriptions, or role assignments.
        """
        # Mandatory Condition 3: Concurrency-safe advisory lock serialization
        await self._try_acquire_advisory_lock(
            f"provisioning_retry:{society_id}",
            f"provisioning retry for society '{society_id}'",
        )

        society = await self.session.get(Society, society_id)

        if society is not None:
            if society.onboarding_status == "COMPLETED":
                raise ProvisioningRetryIneligibleException(
                    message="Society provisioning has already completed and cannot be retried.",
                    code="PROVISIONING_ALREADY_COMPLETED",
                    details={"society_id": str(society_id), "status": society.onboarding_status},
                )
        else:
            # Check if there is an out-of-band audit log of a failed attempt
            audit_stmt = (
                select(AuditLog)
                .where(
                    AuditLog.action == "PROVISIONING_FAILED",
                    or_(
                        AuditLog.request_id == str(society_id),
                        AuditLog.entity_id == str(society_id),
                    ),
                )
                .limit(1)
            )
            audit_res = await self.session.execute(audit_stmt)
            if not audit_res.scalar_one_or_none() and override_request is None:
                raise NotFoundException(f"Society or provisioning record with ID '{society_id}' does not exist.")

        engine = SocietyProvisioningEngine(self.session)

        if override_request is not None:
            retry_payload = override_request
        else:
            # If society exists with FAILED or IN_PROGRESS, load subscription plan to reconstruct
            plan_code = "FREE"
            async with tenant_context(society_id):
                await set_db_tenant_context(self.session, society_id)
                sub_stmt = (
                    select(SocietySubscription)
                    .options(selectinload(SocietySubscription.plan))
                    .where(SocietySubscription.society_id == society_id)
                )
                sub_res = await self.session.execute(sub_stmt)
                sub = sub_res.scalar_one_or_none()
                if sub and sub.plan:
                    plan_code = sub.plan.plan_code

            # Lookup admin user
            admin_stmt = (
                select(User)
                .join(RoleAssignment, User.id == RoleAssignment.user_id)
                .join(Role, RoleAssignment.role_id == Role.id)
                .where(
                    RoleAssignment.society_id == society_id,
                    Role.code == "SOCIETY_ADMIN",
                )
                .limit(1)
            )
            admin_res = await self.session.execute(admin_stmt)
            admin_user = admin_res.scalar_one_or_none()

            from apps.api.src.subscriptions.schemas import InitialAdminPayload, InitialSpatialPayload

            retry_payload = ProvisionSocietyRequest(
                provisioning_request_id=society_id,
                legal_name=society.legal_name if society else f"Society-{society_id}",
                display_name=society.display_name if society else f"Society-{society_id}",
                registration_number=society.registration_number if society else None,
                address_line1=society.address_line1 if society else "Main St",
                address_line2=society.address_line2 if society else None,
                city=society.city if society else "City",
                state=society.state if society else "State",
                country=society.country if society else "IN",
                postal_code=society.postal_code if society else "123456",
                timezone=society.timezone if society else "Asia/Kolkata",
                default_language=society.default_language if society else "en",
                plan_code=plan_code,
                admin_user=InitialAdminPayload(
                    email=admin_user.email if admin_user and admin_user.email else f"admin.{society_id}@example.com",
                    first_name=admin_user.first_name if admin_user else "Admin",
                    last_name=admin_user.last_name if admin_user else "User",
                    phone=admin_user.phone if admin_user else None,
                ),
                spatial=InitialSpatialPayload(create_default_block=True, default_block_name="Tower A"),
            )

        # Delegate execution to engine
        result = await engine.provision_society(
            request=retry_payload,
            current_user_id=current_user_id,
            correlation_id=correlation_id,
        )

        return result
