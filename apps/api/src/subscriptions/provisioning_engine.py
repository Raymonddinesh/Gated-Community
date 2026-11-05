"""Phase 21C — Society Provisioning Engine Domain Service.

Atomic, idempotent, race-safe, and zero-RLS-bypass compliant tenant onboarding
orchestrator for SocietySphere.
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from apps.api.src.core.tenant_context import tenant_context
from apps.api.src.database.models.audit import AuditLog
from apps.api.src.database.models.authorization import Role, RoleAssignment
from apps.api.src.database.models.identity import User
from apps.api.src.database.models.membership import UserSocietyMembership
from apps.api.src.database.models.society import Block, Society
from apps.api.src.database.models.subscription import (
    PlatformSubscriptionPlan,
    SocietyProvisioningLog,
    SocietySubscription,
    SocietyUsageMetric,
)
from apps.api.src.database.session import get_session_factory, set_db_tenant_context
from apps.api.src.subscriptions.entitlement_service import EntitlementService
from apps.api.src.subscriptions.enums import (
    FeatureKey,
    ProvisioningStatus,
    ProvisioningStepKey,
    QuotaKey,
    SubscriptionStatus,
)
from apps.api.src.subscriptions.exceptions import (
    IdempotencyPayloadMismatchException,
    InvalidProvisioningPayloadException,
    PlanInactiveException,
    PlanNotFoundException,
    ProvisioningConflictException,
    ProvisioningEngineException,
)
from apps.api.src.subscriptions.schemas import (
    ProvisioningStepLogResponse,
    ProvisionSocietyRequest,
    ProvisionSocietyResponse,
)

logger = logging.getLogger("societysphere.subscriptions.provisioning")


def compute_payload_fingerprint(request: ProvisionSocietyRequest) -> str:
    """Compute a deterministic SHA-256 fingerprint of canonical JSON for the provisioning request.

    Excludes volatile fields (provisioning_request_id, timestamps).
    Normalizes string casing and whitespace.
    """
    canonical: dict[str, Any] = {
        "legal_name": request.legal_name.strip(),
        "display_name": request.display_name.strip(),
        "registration_number": (request.registration_number or "").strip() or None,
        "address_line1": request.address_line1.strip(),
        "address_line2": (request.address_line2 or "").strip() or None,
        "city": request.city.strip(),
        "state": request.state.strip(),
        "country": request.country.strip(),
        "postal_code": request.postal_code.strip(),
        "timezone": request.timezone.strip(),
        "default_language": request.default_language.strip(),
        "plan_code": request.plan_code.strip().upper(),
        "skip_trial": request.skip_trial,
        "admin_user": {
            "email": (request.admin_user.email or "").strip().lower() or None,
            "phone": (request.admin_user.phone or "").strip() or None,
            "first_name": request.admin_user.first_name.strip(),
            "last_name": request.admin_user.last_name.strip(),
        },
        "spatial": {
            "create_default_block": request.spatial.create_default_block,
            "default_block_name": request.spatial.default_block_name.strip(),
        },
    }
    serialized = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _lock_key_to_int(key_str: str) -> int:
    """Derive a stable 64-bit signed integer hash from a string key for pg_try_advisory_xact_lock(bigint)."""
    digest = hashlib.sha256(key_str.encode("utf-8")).digest()[:8]
    return int.from_bytes(digest, byteorder="big", signed=True)


def _mask_email(email: str | None) -> str | None:
    """Mask email for privacy in audit logs."""
    if not email:
        return None
    parts = email.split("@")
    if len(parts) != 2:
        return "***"
    username, domain = parts
    if len(username) <= 2:
        masked_user = username[0] + "*"
    else:
        masked_user = username[0] + "*" * (len(username) - 2) + username[-1]
    return f"{masked_user}@{domain}"


def _utc_now() -> datetime:
    """Return naive UTC datetime matching SQLAlchemy TimestampMixin and PostgreSQL TIMESTAMP."""
    return datetime.now(UTC).replace(tzinfo=None)


class SocietyProvisioningEngine:
    """Enterprise domain service executing idempotent, atomic society tenant provisioning."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

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

    async def _log_out_of_band_failure(
        self,
        request: ProvisionSocietyRequest,
        exc: Exception,
        step_key: str,
        current_user_id: uuid.UUID | None,
        correlation_id: str | None,
    ) -> None:
        """Record diagnostic failure telemetry in global audit log using an independent session."""
        try:
            bind = self.session.bind
            if bind:
                failure_session_maker = async_sessionmaker(
                    bind=bind, class_=AsyncSession, expire_on_commit=False, autoflush=False
                )
                async with failure_session_maker() as failure_session:
                    audit = AuditLog(
                        society_id=None,
                        actor_user_id=current_user_id,
                        action="SOCIETY_PROVISIONING_FAILED",
                        entity_type="society",
                        entity_id=str(request.provisioning_request_id),
                        request_id=str(request.provisioning_request_id),
                        correlation_id=correlation_id,
                        after_state={
                            "error_type": exc.__class__.__name__,
                            "error_message": str(exc),
                            "failed_step": step_key,
                            "legal_name": request.legal_name,
                            "plan_code": request.plan_code,
                        },
                    )
                    failure_session.add(audit)
                    await failure_session.commit()
            else:
                factory = get_session_factory()
                async with factory() as failure_session:
                    audit = AuditLog(
                        society_id=None,
                        actor_user_id=current_user_id,
                        action="SOCIETY_PROVISIONING_FAILED",
                        entity_type="society",
                        entity_id=str(request.provisioning_request_id),
                        request_id=str(request.provisioning_request_id),
                        correlation_id=correlation_id,
                        after_state={
                            "error_type": exc.__class__.__name__,
                            "error_message": str(exc),
                            "failed_step": step_key,
                            "legal_name": request.legal_name,
                            "plan_code": request.plan_code,
                        },
                    )
                    failure_session.add(audit)
                    await failure_session.commit()
        except Exception as audit_err:
            logger.warning(f"Failed to record out-of-band provisioning failure audit: {audit_err}")

    async def provision_society(
        self,
        request: ProvisionSocietyRequest,
        current_user_id: uuid.UUID | None = None,
        correlation_id: str | None = None,
    ) -> ProvisionSocietyResponse:
        """Execute the complete 9-step atomic society provisioning lifecycle."""
        current_step: str = ProvisioningStepKey.VALIDATE_INPUT
        step_logs: list[ProvisioningStepLogResponse] = []
        now_utc = _utc_now()

        # ----------------------------------------------------------------------
        # 1. Idempotency Key & Advisory Lock Serialization
        # ----------------------------------------------------------------------
        idempotency_key_str = str(request.provisioning_request_id)
        payload_fingerprint = compute_payload_fingerprint(request)

        # Attempt non-blocking transaction-scoped locks
        await self._try_acquire_advisory_lock(
            f"idempotency:{idempotency_key_str}",
            f"idempotency key '{idempotency_key_str}'",
        )
        normalized_legal_name = request.legal_name.strip().lower()
        await self._try_acquire_advisory_lock(
            f"society_legal_name:{normalized_legal_name}",
            f"society '{request.legal_name}'",
        )

        # ----------------------------------------------------------------------
        # 2. Durable Idempotency & Conflict Check
        # ----------------------------------------------------------------------
        # Check if this provisioning_request_id was already successfully provisioned
        prior_audit_stmt = select(AuditLog).where(
            AuditLog.request_id == idempotency_key_str,
            AuditLog.action == "SOCIETY_PROVISIONED",
        )
        prior_audit_res = await self.session.execute(prior_audit_stmt)
        prior_audit = prior_audit_res.scalar_one_or_none()

        if prior_audit is not None:
            # Check payload fingerprint
            stored_hash = (prior_audit.after_state or {}).get("payload_hash")
            if stored_hash and stored_hash != payload_fingerprint:
                await self.session.rollback()
                raise IdempotencyPayloadMismatchException(
                    idempotency_key=idempotency_key_str,
                    details={
                        "expected_hash": stored_hash,
                        "actual_hash": payload_fingerprint,
                    },
                )

            # Replay existing completed society
            existing_society_id = uuid.UUID(prior_audit.entity_id)
            existing_soc = await self.session.get(Society, existing_society_id)
            if existing_soc:
                # Load subscription within tenant context
                async with tenant_context(existing_society_id):
                    await set_db_tenant_context(self.session, existing_society_id)
                    sub_stmt = select(SocietySubscription).where(
                        SocietySubscription.society_id == existing_society_id
                    )
                    sub_res = await self.session.execute(sub_stmt)
                    sub = sub_res.scalar_one_or_none()
                    plan_code = (prior_audit.after_state or {}).get("plan_code", request.plan_code)

                    return ProvisionSocietyResponse(
                        provisioning_request_id=request.provisioning_request_id,
                        society_id=existing_soc.id,
                        legal_name=existing_soc.legal_name,
                        display_name=existing_soc.display_name,
                        status=existing_soc.status,
                        onboarding_status=existing_soc.onboarding_status,
                        plan_code=plan_code,
                        subscription_status=sub.status if sub else "ACTIVE",
                        trial_ends_at=sub.trial_ends_at if sub else None,
                        current_period_end=sub.current_period_end if sub else now_utc + timedelta(days=30),
                        admin_user_id=current_user_id or uuid.uuid4(),
                        admin_email=request.admin_user.email,
                        created_at=existing_soc.created_at,
                        completed_at=existing_soc.updated_at,
                        is_idempotent_replay=True,
                        steps=[],
                    )

        # Check if active society with identical legal name already exists
        name_check_stmt = select(Society).where(
            func.lower(func.trim(Society.legal_name)) == normalized_legal_name,
            Society.archived_at.is_(None),
        )
        name_check_res = await self.session.execute(name_check_stmt)
        if name_check_res.scalar_one_or_none() is not None:
            await self.session.rollback()
            raise ProvisioningConflictException(
                message=f"A society with legal name '{request.legal_name}' already exists.",
                details={"code": "SOCIETY_ALREADY_EXISTS"},
            )

        # Check if active society with identical registration number already exists
        if request.registration_number:
            reg_norm = request.registration_number.strip().upper()
            reg_check_stmt = select(Society).where(
                func.upper(func.trim(Society.registration_number)) == reg_norm,
                Society.archived_at.is_(None),
            )
            reg_check_res = await self.session.execute(reg_check_stmt)
            if reg_check_res.scalar_one_or_none() is not None:
                await self.session.rollback()
                raise ProvisioningConflictException(
                    message=f"A society with registration number '{request.registration_number}' already exists.",
                    details={"code": "SOCIETY_REGISTRATION_EXISTS"},
                )

        try:
            # ------------------------------------------------------------------
            # STEP 01: VALIDATE_INPUT & Plan Resolution
            # ------------------------------------------------------------------
            current_step = ProvisioningStepKey.VALIDATE_INPUT
            step_start = _utc_now()

            if not request.admin_user.email and not request.admin_user.phone:
                raise InvalidProvisioningPayloadException(
                    "Either admin_user.email or admin_user.phone must be provided."
                )

            plan_stmt = select(PlatformSubscriptionPlan).where(
                func.upper(PlatformSubscriptionPlan.plan_code) == request.plan_code.strip().upper(),
                PlatformSubscriptionPlan.archived_at.is_(None),
            )
            plan_res = await self.session.execute(plan_stmt)
            plan = plan_res.scalar_one_or_none()

            if plan is None:
                raise PlanNotFoundException(request.plan_code)
            if not plan.is_active:
                raise PlanInactiveException(request.plan_code)

            step_logs.append(
                ProvisioningStepLogResponse(
                    step_key=ProvisioningStepKey.VALIDATE_INPUT,
                    status=ProvisioningStatus.COMPLETED,
                    started_at=step_start,
                    completed_at=_utc_now(),
                    message=f"Plan '{plan.plan_code}' validated successfully.",
                )
            )

            # ------------------------------------------------------------------
            # STEP 02: CREATE_SOCIETY_ROOT
            # ------------------------------------------------------------------
            current_step = ProvisioningStepKey.CREATE_SOCIETY_ROOT
            step_start = _utc_now()

            new_society_id = uuid.uuid4()
            society = Society(
                id=new_society_id,
                legal_name=request.legal_name.strip(),
                display_name=request.display_name.strip(),
                registration_number=(request.registration_number or "").strip() or None,
                address_line1=request.address_line1.strip(),
                address_line2=(request.address_line2 or "").strip() or None,
                city=request.city.strip(),
                state=request.state.strip(),
                country=request.country.strip(),
                postal_code=request.postal_code.strip(),
                timezone=request.timezone.strip(),
                default_language=request.default_language.strip(),
                status="ACTIVE",
                onboarding_status="IN_PROGRESS",
            )
            self.session.add(society)
            await self.session.flush()

            step_logs.append(
                ProvisioningStepLogResponse(
                    step_key=ProvisioningStepKey.CREATE_SOCIETY_ROOT,
                    status=ProvisioningStatus.COMPLETED,
                    started_at=step_start,
                    completed_at=_utc_now(),
                    message=f"Created society root with ID '{society.id}'.",
                )
            )

            # ------------------------------------------------------------------
            # STEP 03: BIND_TENANT_RLS
            # ------------------------------------------------------------------
            current_step = ProvisioningStepKey.BIND_TENANT_RLS
            step_start = _utc_now()

            # Configure transaction-local RLS GUC setting
            await set_db_tenant_context(self.session, society.id)

            # Enter tenant context manager for the remainder of provisioning
            async with tenant_context(society.id):
                # Write initial step logs in society_provisioning_logs
                init_log = SocietyProvisioningLog(
                    provisioning_request_id=request.provisioning_request_id,
                    society_id=society.id,
                    step_key=ProvisioningStepKey.VALIDATE_INPUT,
                    status=ProvisioningStatus.COMPLETED,
                    message="Validated request payload and subscription plan.",
                    correlation_id=correlation_id,
                    started_at=step_start,
                    completed_at=_utc_now(),
                )
                self.session.add(init_log)

                root_log = SocietyProvisioningLog(
                    provisioning_request_id=request.provisioning_request_id,
                    society_id=society.id,
                    step_key=ProvisioningStepKey.CREATE_SOCIETY_ROOT,
                    status=ProvisioningStatus.COMPLETED,
                    message=f"Created society record {society.id}",
                    correlation_id=correlation_id,
                    started_at=step_start,
                    completed_at=_utc_now(),
                )
                self.session.add(root_log)

                step_logs.append(
                    ProvisioningStepLogResponse(
                        step_key=ProvisioningStepKey.BIND_TENANT_RLS,
                        status=ProvisioningStatus.COMPLETED,
                        started_at=step_start,
                        completed_at=_utc_now(),
                        message=f"Bound tenant RLS context to '{society.id}'.",
                    )
                )

                # --------------------------------------------------------------
                # STEP 04: ASSIGN_SUBSCRIPTION
                # --------------------------------------------------------------
                current_step = ProvisioningStepKey.ASSIGN_SUBSCRIPTION
                step_start = _utc_now()

                if plan.trial_days > 0 and not request.skip_trial:
                    sub_status = SubscriptionStatus.TRIAL
                    trial_ends_at = now_utc + timedelta(days=plan.trial_days)
                    period_start = now_utc
                    period_end = trial_ends_at
                else:
                    sub_status = SubscriptionStatus.ACTIVE
                    trial_ends_at = None
                    period_start = now_utc
                    period_end = now_utc + timedelta(days=30)

                subscription = SocietySubscription(
                    society_id=society.id,
                    plan_id=plan.id,
                    status=sub_status,
                    starts_at=now_utc,
                    trial_ends_at=trial_ends_at,
                    current_period_start=period_start,
                    current_period_end=period_end,
                )
                self.session.add(subscription)

                sub_log = SocietyProvisioningLog(
                    provisioning_request_id=request.provisioning_request_id,
                    society_id=society.id,
                    step_key=ProvisioningStepKey.ASSIGN_SUBSCRIPTION,
                    status=ProvisioningStatus.COMPLETED,
                    message=f"Assigned plan '{plan.plan_code}' with status '{sub_status}'.",
                    correlation_id=correlation_id,
                    started_at=step_start,
                    completed_at=_utc_now(),
                )
                self.session.add(sub_log)

                step_logs.append(
                    ProvisioningStepLogResponse(
                        step_key=ProvisioningStepKey.ASSIGN_SUBSCRIPTION,
                        status=ProvisioningStatus.COMPLETED,
                        started_at=step_start,
                        completed_at=_utc_now(),
                        message=f"Assigned plan '{plan.plan_code}'.",
                    )
                )

                # --------------------------------------------------------------
                # STEP 05: INIT_USAGE_METRICS
                # --------------------------------------------------------------
                current_step = ProvisioningStepKey.INIT_USAGE_METRICS
                step_start = _utc_now()

                metrics_to_seed = [
                    QuotaKey.UNITS_MAX,
                    QuotaKey.RESIDENTS_MAX,
                    QuotaKey.STAFF_MAX,
                    QuotaKey.STORAGE_BYTES_MAX,
                ]
                for metric_key in metrics_to_seed:
                    metric = SocietyUsageMetric(
                        society_id=society.id,
                        metric_key=metric_key,
                        current_value=0,
                        last_calculated_at=now_utc,
                    )
                    self.session.add(metric)

                metric_log = SocietyProvisioningLog(
                    provisioning_request_id=request.provisioning_request_id,
                    society_id=society.id,
                    step_key=ProvisioningStepKey.INIT_USAGE_METRICS,
                    status=ProvisioningStatus.COMPLETED,
                    message=f"Seeded {len(metrics_to_seed)} baseline usage metrics.",
                    correlation_id=correlation_id,
                    started_at=step_start,
                    completed_at=_utc_now(),
                )
                self.session.add(metric_log)

                step_logs.append(
                    ProvisioningStepLogResponse(
                        step_key=ProvisioningStepKey.INIT_USAGE_METRICS,
                        status=ProvisioningStatus.COMPLETED,
                        started_at=step_start,
                        completed_at=_utc_now(),
                        message="Initialized baseline usage counters.",
                    )
                )

                # --------------------------------------------------------------
                # STEP 06: PROVISION_ADMIN_USER
                # --------------------------------------------------------------
                current_step = ProvisioningStepKey.PROVISION_ADMIN_USER
                step_start = _utc_now()

                admin_email = (request.admin_user.email or "").strip().lower() or None
                admin_phone = (request.admin_user.phone or "").strip() or None

                admin_user: User | None = None
                if admin_email:
                    u_stmt = select(User).where(func.lower(User.email) == admin_email)
                    u_res = await self.session.execute(u_stmt)
                    admin_user = u_res.scalar_one_or_none()

                if admin_user is None and admin_phone:
                    u_stmt = select(User).where(User.phone == admin_phone)
                    u_res = await self.session.execute(u_stmt)
                    admin_user = u_res.scalar_one_or_none()

                if admin_user is None:
                    admin_user = User(
                        email=admin_email,
                        phone=admin_phone,
                        first_name=request.admin_user.first_name.strip(),
                        last_name=request.admin_user.last_name.strip(),
                        display_name=f"{request.admin_user.first_name.strip()} {request.admin_user.last_name.strip()}",
                        preferred_language=request.default_language,
                        status="ACTIVE",
                    )
                    self.session.add(admin_user)
                    await self.session.flush()

                membership = UserSocietyMembership(
                    user_id=admin_user.id,
                    society_id=society.id,
                    membership_status="ACTIVE",
                    joined_at=now_utc,
                    activated_at=now_utc,
                )
                self.session.add(membership)

                user_log = SocietyProvisioningLog(
                    provisioning_request_id=request.provisioning_request_id,
                    society_id=society.id,
                    step_key=ProvisioningStepKey.PROVISION_ADMIN_USER,
                    status=ProvisioningStatus.COMPLETED,
                    message=f"Bound primary admin user '{admin_user.id}' to society.",
                    correlation_id=correlation_id,
                    started_at=step_start,
                    completed_at=_utc_now(),
                )
                self.session.add(user_log)

                step_logs.append(
                    ProvisioningStepLogResponse(
                        step_key=ProvisioningStepKey.PROVISION_ADMIN_USER,
                        status=ProvisioningStatus.COMPLETED,
                        started_at=step_start,
                        completed_at=_utc_now(),
                        message=f"Provisioned administrator identity '{admin_user.id}'.",
                    )
                )

                # --------------------------------------------------------------
                # STEP 07: ASSIGN_ADMIN_ROLE
                # --------------------------------------------------------------
                current_step = ProvisioningStepKey.ASSIGN_ADMIN_ROLE
                step_start = _utc_now()

                role_stmt = select(Role).where(
                    Role.code == "SOCIETY_ADMIN",
                    Role.scope_type == "SOCIETY",
                )
                role_res = await self.session.execute(role_stmt)
                admin_role = role_res.scalar_one_or_none()

                if admin_role is None:
                    raise ProvisioningEngineException("System role 'SOCIETY_ADMIN' not found.")

                role_assignment = RoleAssignment(
                    user_id=admin_user.id,
                    role_id=admin_role.id,
                    society_id=society.id,
                    scope_type="SOCIETY",
                    status="ACTIVE",
                    assigned_at=now_utc,
                )
                self.session.add(role_assignment)

                role_log = SocietyProvisioningLog(
                    provisioning_request_id=request.provisioning_request_id,
                    society_id=society.id,
                    step_key=ProvisioningStepKey.ASSIGN_ADMIN_ROLE,
                    status=ProvisioningStatus.COMPLETED,
                    message=f"Assigned 'SOCIETY_ADMIN' role to user '{admin_user.id}'.",
                    correlation_id=correlation_id,
                    started_at=step_start,
                    completed_at=_utc_now(),
                )
                self.session.add(role_log)

                step_logs.append(
                    ProvisioningStepLogResponse(
                        step_key=ProvisioningStepKey.ASSIGN_ADMIN_ROLE,
                        status=ProvisioningStatus.COMPLETED,
                        started_at=step_start,
                        completed_at=_utc_now(),
                        message="Assigned 'SOCIETY_ADMIN' role to administrator.",
                    )
                )

                # --------------------------------------------------------------
                # STEP 08: INIT_SPATIAL_BASELINE
                # --------------------------------------------------------------
                current_step = ProvisioningStepKey.INIT_SPATIAL_BASELINE
                step_start = _utc_now()

                if request.spatial.create_default_block:
                    block = Block(
                        society_id=society.id,
                        code="A",
                        display_name=request.spatial.default_block_name or "Tower A",
                        sequence_order=1,
                        status="ACTIVE",
                    )
                    self.session.add(block)

                spatial_log = SocietyProvisioningLog(
                    provisioning_request_id=request.provisioning_request_id,
                    society_id=society.id,
                    step_key=ProvisioningStepKey.INIT_SPATIAL_BASELINE,
                    status=ProvisioningStatus.COMPLETED,
                    message="Initialized baseline physical spatial hierarchy.",
                    correlation_id=correlation_id,
                    started_at=step_start,
                    completed_at=_utc_now(),
                )
                self.session.add(spatial_log)

                step_logs.append(
                    ProvisioningStepLogResponse(
                        step_key=ProvisioningStepKey.INIT_SPATIAL_BASELINE,
                        status=ProvisioningStatus.COMPLETED,
                        started_at=step_start,
                        completed_at=_utc_now(),
                        message="Configured initial spatial hierarchy.",
                    )
                )

                # --------------------------------------------------------------
                # STEP 09: FINALIZE_ONBOARDING
                # --------------------------------------------------------------
                current_step = ProvisioningStepKey.FINALIZE_ONBOARDING
                step_start = _utc_now()

                # Update society status
                society.onboarding_status = "COMPLETED"
                society.status = "ACTIVE"

                # Entitlement validation probe (verifies resolution under active context)
                entitlement_svc = EntitlementService(self.session)
                effective_ent = await entitlement_svc.get_effective_entitlement(
                    society_id=society.id,
                    entitlement_key=FeatureKey.GOVERNANCE,
                )
                if effective_ent is None:
                    raise ProvisioningEngineException("Entitlement validation probe failed for GOVERNANCE.")

                # Finalize provisioning log step
                final_log = SocietyProvisioningLog(
                    provisioning_request_id=request.provisioning_request_id,
                    society_id=society.id,
                    step_key=ProvisioningStepKey.FINALIZE_ONBOARDING,
                    status=ProvisioningStatus.COMPLETED,
                    message=f"fingerprint:{payload_fingerprint} | Provisioning completed successfully.",
                    correlation_id=correlation_id,
                    started_at=step_start,
                    completed_at=_utc_now(),
                )
                self.session.add(final_log)

                # Write platform audit log entry (unscoped society_id = None)
                audit_entry = AuditLog(
                    society_id=None,
                    actor_user_id=current_user_id,
                    action="SOCIETY_PROVISIONED",
                    entity_type="society",
                    entity_id=str(society.id),
                    request_id=idempotency_key_str,
                    correlation_id=correlation_id,
                    after_state={
                        "payload_hash": payload_fingerprint,
                        "society_id": str(society.id),
                        "legal_name": society.legal_name,
                        "plan_code": plan.plan_code,
                        "admin_email_masked": _mask_email(request.admin_user.email),
                        "completed_at": _utc_now().isoformat(),
                    },
                )
                self.session.add(audit_entry)

                step_logs.append(
                    ProvisioningStepLogResponse(
                        step_key=ProvisioningStepKey.FINALIZE_ONBOARDING,
                        status=ProvisioningStatus.COMPLETED,
                        started_at=step_start,
                        completed_at=_utc_now(),
                        message="Finalized society onboarding and verified entitlements.",
                    )
                )

                # Commit the entire atomic transaction
                await self.session.commit()

                return ProvisionSocietyResponse(
                    provisioning_request_id=request.provisioning_request_id,
                    society_id=society.id,
                    legal_name=society.legal_name,
                    display_name=society.display_name,
                    status=society.status,
                    onboarding_status=society.onboarding_status,
                    plan_code=plan.plan_code,
                    subscription_status=subscription.status,
                    trial_ends_at=subscription.trial_ends_at,
                    current_period_end=subscription.current_period_end,
                    admin_user_id=admin_user.id,
                    admin_email=admin_user.email,
                    created_at=society.created_at,
                    completed_at=_utc_now(),
                    is_idempotent_replay=False,
                    steps=step_logs,
                )

        except Exception as exc:
            await self.session.rollback()
            await self._log_out_of_band_failure(
                request=request,
                exc=exc,
                step_key=current_step,
                current_user_id=current_user_id,
                correlation_id=correlation_id,
            )
            raise
