"""Phase 21E.6 — SaaS Billing Period Scheduler Service.

Autonomous background engine for subscription billing cycle advancement and renewal invoicing:
- Detects subscriptions where next_billing_at <= current UTC cutoff.
- Supports MONTHLY and ANNUAL cycles with Asia/Kolkata boundaries.
- Preserves anchor-day semantics and handles leap-year edge cases via BillingPeriodService.
- Excludes cancelled subscriptions and administratively suspended societies (Society.status == 'SUSPENDED').
- High-concurrency safe: uses SELECT ... FOR UPDATE SKIP LOCKED and PostgreSQL advisory locks.
- Recovers safely from partial worker failures without duplicate invoices or skipped cycles.
- Persists detailed audit records in platform_billing_job_runs and subscription history/audit logs.
"""

import hashlib
import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import and_, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from apps.api.src.database.models.platform_billing import (
    PlatformBillingJobRun,
    PlatformSubscriptionAuditLog,
    PlatformSubscriptionHistory,
)
from apps.api.src.database.models.society import Society
from apps.api.src.database.models.subscription import SocietySubscription
from apps.api.src.subscriptions.automation.renewal_service import (
    AutomatedRenewalInvoicingService,
)
from apps.api.src.subscriptions.automation.schemas import (
    BillingBatchExecutionResult,
    BillingJobRunStatus,
    BillingJobType,
    SubscriptionRollResult,
)
from apps.api.src.subscriptions.billing_period_service import BillingPeriodService
from apps.api.src.subscriptions.enums import SubscriptionStatus
from apps.api.src.subscriptions.grace_period_service import GracePeriodService
from apps.api.src.subscriptions.subscription_lifecycle_service import SubscriptionLifecycleService

logger = logging.getLogger("societysphere.subscriptions.automation.scheduler")


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def compute_advisory_lock_key(resource_id: str) -> int:
    """Derive deterministic signed 64-bit integer hash for pg_try_advisory_xact_lock(bigint).

    Uses SHA-256 digest to map string identity to PostgreSQL bigint range [-2^63, 2^63 - 1].
    """
    digest = hashlib.sha256(resource_id.encode("utf-8")).digest()[:8]
    return int.from_bytes(digest, byteorder="big", signed=True)


# Backwards compatibility alias
_calc_advisory_lock_key = compute_advisory_lock_key


class BillingPeriodSchedulerService:
    """Service managing periodic subscription renewal rolling and statutory invoicing."""

    def __init__(
        self,
        session: AsyncSession,
        renewal_service: AutomatedRenewalInvoicingService | None = None,
    ) -> None:
        self.session = session
        self.renewal_service = renewal_service or AutomatedRenewalInvoicingService()

    async def _is_postgresql(self) -> bool:
        """Detect whether the current database session is PostgreSQL."""
        try:
            bind = self.session.get_bind()
            if bind and "postgresql" in str(bind.dialect.name).lower():
                return True
        except Exception:
            pass
        return False

    async def detect_due_subscriptions(
        self,
        cutoff_utc: datetime,
        batch_size: int = 50,
    ) -> list[SocietySubscription]:
        """Query subscriptions due for renewal up to cutoff_utc under concurrency locks."""
        stmt = (
            select(SocietySubscription)
            .join(Society, Society.id == SocietySubscription.society_id)
            .options(
                selectinload(SocietySubscription.plan),
                selectinload(SocietySubscription.society),
            )
            .where(
                or_(
                    and_(
                        SocietySubscription.status == "ACTIVE",
                        SocietySubscription.auto_renew.is_(True),
                    ),
                    SocietySubscription.status == "TRIAL",
                ),
                SocietySubscription.next_billing_at <= cutoff_utc,
                Society.status != "SUSPENDED",
                Society.archived_at.is_(None),
            )
            .order_by(SocietySubscription.next_billing_at.asc())
            .limit(batch_size)
        )

        is_pg = await self._is_postgresql()
        if is_pg:
            stmt = stmt.with_for_update(skip_locked=True)
        else:
            stmt = stmt.with_for_update()

        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def roll_single_subscription(
        self,
        subscription_id: UUID,
        cutoff_utc: datetime,
        execution_id: str,
    ) -> SubscriptionRollResult:
        """Process billing roll and renewal invoicing for an individual subscription.

        Must be executed within an active database transaction.
        """
        now = _utc_now()

        # 1. Fetch Subscription under row lock
        stmt = (
            select(SocietySubscription)
            .options(
                selectinload(SocietySubscription.plan),
                selectinload(SocietySubscription.society),
            )
            .where(SocietySubscription.id == subscription_id)
            .with_for_update()
        )
        res = await self.session.execute(stmt)
        sub = res.scalar_one_or_none()

        if not sub:
            return SubscriptionRollResult(
                subscription_id=subscription_id,
                society_id=UUID(int=0),
                status="SKIPPED",
                skip_reason="SUBSCRIPTION_NOT_FOUND",
            )

        society: Society | None = sub.society
        if not society:
            society = await self.session.get(Society, sub.society_id)
        if not society:
            return SubscriptionRollResult(
                subscription_id=sub.id,
                society_id=sub.society_id,
                status="SKIPPED",
                skip_reason="SOCIETY_NOT_FOUND",
            )

        # 2. Administrative Suspensions & Terminal Cancellation Checks
        if society.status == "SUSPENDED":
            logger.warning(
                "Subscription %s skipped: Society %s is administratively suspended.",
                sub.id,
                sub.society_id,
            )
            return SubscriptionRollResult(
                subscription_id=sub.id,
                society_id=sub.society_id,
                status="SKIPPED",
                skip_reason="SOCIETY_ADMINISTRATIVELY_SUSPENDED",
            )

        if sub.status == "CANCELLED":
            logger.info("Subscription %s skipped: subscription is CANCELLED.", sub.id)
            return SubscriptionRollResult(
                subscription_id=sub.id,
                society_id=sub.society_id,
                status="SKIPPED",
                skip_reason="SUBSCRIPTION_CANCELLED",
            )

        # Skip non-trial subscriptions if auto_renew is False
        if not sub.auto_renew and sub.status != SubscriptionStatus.TRIAL.value:
            logger.info("Subscription %s skipped: auto_renew is False.", sub.id)
            return SubscriptionRollResult(
                subscription_id=sub.id,
                society_id=sub.society_id,
                status="SKIPPED",
                skip_reason="AUTO_RENEW_DISABLED",
            )

        # 3. Currency / Next Billing Check (prevent race if already rolled)
        norm_cutoff = cutoff_utc.replace(tzinfo=None) if cutoff_utc.tzinfo is not None else cutoff_utc
        sub_next = sub.next_billing_at.replace(tzinfo=None) if (sub.next_billing_at and sub.next_billing_at.tzinfo is not None) else sub.next_billing_at
        if sub_next and sub_next > norm_cutoff:
            logger.info("Subscription %s skipped: next_billing_at is in future.", sub.id)
            return SubscriptionRollResult(
                subscription_id=sub.id,
                society_id=sub.society_id,
                status="SKIPPED",
                skip_reason="ALREADY_ADVANCED",
            )

        # 4. Supplementary PostgreSQL Advisory Lock
        is_pg = await self._is_postgresql()
        if is_pg:
            lock_key = _calc_advisory_lock_key(f"billing_sub:{sub.society_id}")
            lock_res = await self.session.execute(
                text("SELECT pg_try_advisory_xact_lock(:lock_key)"),
                {"lock_key": lock_key},
            )
            if not lock_res.scalar():
                logger.warning(
                    "Advisory lock contention for society %s. Skipping this worker cycle.",
                    sub.society_id,
                )
                return SubscriptionRollResult(
                    subscription_id=sub.id,
                    society_id=sub.society_id,
                    status="SKIPPED",
                    skip_reason="ADVISORY_LOCK_CONTENTION",
                )

        # 5. Handle Expiring TRIAL with auto_renew=False
        # Business rule: Expired TRIAL with auto_renew=False must NOT generate renewal invoice,
        # must NOT transition to PAST_DUE, must NOT initiate grace period, and must NOT activate.
        # It transitions cleanly to terminal state CANCELLED via the existing lifecycle state machine.
        if sub.status == SubscriptionStatus.TRIAL.value and not sub.auto_renew:
            previous_status = sub.status
            target_status = SubscriptionStatus.CANCELLED.value
            transition_reason = "Trial expired with auto_renew=False; subscription cancelled without renewal."

            lifecycle_service = SubscriptionLifecycleService(self.session)
            lifecycle_service.validate_transition(
                current_status=previous_status,
                target_status=target_status,
                society_id=sub.society_id,
            )

            trial_before_state: dict[str, Any] = {
                "status": sub.status,
                "current_period_start": sub.current_period_start.isoformat(),
                "current_period_end": sub.current_period_end.isoformat(),
                "next_billing_at": sub.next_billing_at.isoformat() if sub.next_billing_at else None,
                "past_due_since": sub.past_due_since.isoformat() if sub.past_due_since else None,
                "auto_renew": sub.auto_renew,
            }

            sub.status = target_status
            sub.cancelled_at = now
            sub.cancellation_reason = transition_reason
            # Note: past_due_since remains None (grace period NOT initiated)
            # Note: zero renewal invoices generated

            trial_after_state: dict[str, Any] = {
                "status": sub.status,
                "current_period_start": sub.current_period_start.isoformat(),
                "current_period_end": sub.current_period_end.isoformat(),
                "next_billing_at": sub.next_billing_at.isoformat() if sub.next_billing_at else None,
                "past_due_since": None,
                "auto_renew": sub.auto_renew,
                "cancelled_at": sub.cancelled_at.isoformat(),
                "cancellation_reason": sub.cancellation_reason,
            }

            history = PlatformSubscriptionHistory(
                id=uuid4(),
                society_id=sub.society_id,
                subscription_id=sub.id,
                previous_plan_id=sub.plan_id,
                new_plan_id=sub.plan_id,
                previous_status=previous_status,
                new_status=target_status,
                previous_cycle=sub.billing_cycle,
                new_cycle=sub.billing_cycle,
                transition_reason=transition_reason,
                changed_by=None,
                effective_at=now,
            )
            self.session.add(history)

            audit = PlatformSubscriptionAuditLog(
                id=uuid4(),
                society_id=sub.society_id,
                entity_type="SUBSCRIPTION",
                entity_id=sub.id,
                action="TRIAL_EXPIRED_CANCELLED",
                actor_type="SYSTEM",
                correlation_id=execution_id,
                before_state=trial_before_state,
                after_state=trial_after_state,
                created_at=now,
            )
            self.session.add(audit)
            await self.session.flush()

            logger.info(
                "Subscription %s (Society %s) trial expired with auto_renew=False; transitioned to CANCELLED.",
                sub.id,
                sub.society_id,
            )

            return SubscriptionRollResult(
                subscription_id=sub.id,
                society_id=sub.society_id,
                status="CANCELLED",
                skip_reason="TRIAL_EXPIRED_WITHOUT_RENEWAL",
                old_period_start=sub.current_period_start,
                old_period_end=sub.current_period_end,
                new_period_start=sub.current_period_start,
                new_period_end=sub.current_period_end,
                new_next_billing_at=sub.next_billing_at,
            )

        # 6. Calculate New Billing Period
        old_period_start = sub.current_period_start
        old_period_end = sub.current_period_end

        # Preserve original anchor day from subscription starts_at in IST
        ist_starts = BillingPeriodService.to_ist(sub.starts_at)
        anchor_day = ist_starts.day

        new_period_start, new_period_end = BillingPeriodService.calculate_next_billing_period(
            current_period_end_utc=old_period_end,
            billing_cycle=sub.billing_cycle,
            original_anchor_day=anchor_day,
        )
        if new_period_start.tzinfo is not None:
            new_period_start = new_period_start.replace(tzinfo=None)
        if new_period_end.tzinfo is not None:
            new_period_end = new_period_end.replace(tzinfo=None)

        # 6. Idempotency Key Generation
        idempotency_key = f"renewal:{sub.id}:{new_period_start.isoformat()}:{new_period_end.isoformat()}"

        # 7. Generate & Finalize Renewal Invoice
        invoice_resp = await self.renewal_service.generate_renewal_invoice(
            session=self.session,
            subscription=sub,
            society=society,
            period_start=new_period_start,
            period_end=new_period_end,
            idempotency_key=idempotency_key,
        )

        # 8. Advance Subscription Period & State
        previous_status = sub.status

        # Mandatory Rule: Expiring TRIAL transitions to PAST_DUE (7-day grace period);
        # ACTIVE subscriptions remain ACTIVE upon periodic renewal.
        if previous_status == SubscriptionStatus.TRIAL.value:
            new_status = SubscriptionStatus.PAST_DUE.value
            # Initialize 7-day grace period if not already set (ensures scheduler retries never extend grace)
            if sub.past_due_since is None:
                sub.past_due_since = now
            grace_expiry = GracePeriodService.calculate_grace_expiry(sub.past_due_since)
            transition_reason = (
                f"Trial ended; renewal invoice {invoice_resp.invoice_number} issued "
                f"awaiting payment settlement (7-day grace period expires {grace_expiry.date()})"
            )
        else:
            new_status = previous_status
            transition_reason = f"Automated renewal roll to period {new_period_start.date()} - {new_period_end.date()}"

        # Validate transition using canonical state machine
        if previous_status != new_status:
            lifecycle_service = SubscriptionLifecycleService(self.session)
            lifecycle_service.validate_transition(
                current_status=previous_status,
                target_status=new_status,
                society_id=sub.society_id,
            )

        before_state: dict[str, Any] = {
            "status": sub.status,
            "current_period_start": sub.current_period_start.isoformat(),
            "current_period_end": sub.current_period_end.isoformat(),
            "next_billing_at": sub.next_billing_at.isoformat() if sub.next_billing_at else None,
            "past_due_since": sub.past_due_since.isoformat() if sub.past_due_since else None,
        }

        sub.status = new_status
        sub.current_period_start = new_period_start
        sub.current_period_end = new_period_end
        sub.next_billing_at = new_period_end

        after_state: dict[str, Any] = {
            "status": sub.status,
            "current_period_start": sub.current_period_start.isoformat(),
            "current_period_end": sub.current_period_end.isoformat(),
            "next_billing_at": sub.next_billing_at.isoformat(),
            "invoice_number": invoice_resp.invoice_number,
            "past_due_since": sub.past_due_since.isoformat() if sub.past_due_since else None,
        }
        if sub.past_due_since:
            grace_eval = GracePeriodService().evaluate_grace_period(
                due_date=sub.past_due_since,
                as_of_time=now,
            )
            after_state["grace_period_expiry"] = GracePeriodService.calculate_grace_expiry(sub.past_due_since).isoformat()
            after_state["grace_period_expired"] = grace_eval.is_expired
            after_state["grace_seconds_remaining"] = grace_eval.seconds_remaining

        # 9. Record Subscription History & Audit Log
        history = PlatformSubscriptionHistory(
            id=uuid4(),
            society_id=sub.society_id,
            subscription_id=sub.id,
            previous_plan_id=sub.plan_id,
            new_plan_id=sub.plan_id,
            previous_status=previous_status,
            new_status=new_status,
            previous_cycle=sub.billing_cycle,
            new_cycle=sub.billing_cycle,
            transition_reason=transition_reason,
            changed_by=None,
            effective_at=now,
        )
        self.session.add(history)

        audit = PlatformSubscriptionAuditLog(
            id=uuid4(),
            society_id=sub.society_id,
            entity_type="SUBSCRIPTION",
            entity_id=sub.id,
            action="BILLING_PERIOD_ROLLED",
            actor_type="SYSTEM",
            correlation_id=execution_id,
            before_state=before_state,
            after_state=after_state,
            created_at=now,
        )
        self.session.add(audit)

        await self.session.flush()

        logger.info(
            "Subscription %s rolled: period [%s, %s] -> [%s, %s], invoice %s (%s)",
            sub.id,
            old_period_start,
            old_period_end,
            new_period_start,
            new_period_end,
            invoice_resp.invoice_number,
            invoice_resp.id,
        )

        return SubscriptionRollResult(
            subscription_id=sub.id,
            society_id=sub.society_id,
            status="ROLLED",
            invoice_id=invoice_resp.id,
            invoice_number=invoice_resp.invoice_number,
            old_period_start=old_period_start,
            old_period_end=old_period_end,
            new_period_start=new_period_start,
            new_period_end=new_period_end,
            new_next_billing_at=new_period_end,
        )

    async def process_due_subscriptions(
        self,
        cutoff_utc: datetime | None = None,
        batch_size: int = 50,
        execution_id: str | None = None,
    ) -> BillingBatchExecutionResult:
        """Execute a batch billing roll and renewal invoicing run across due subscriptions.

        Provides complete error isolation per subscription via savepoints.
        """
        started_at = _utc_now()
        effective_cutoff = cutoff_utc or started_at
        if effective_cutoff.tzinfo is not None:
            effective_cutoff = effective_cutoff.replace(tzinfo=None)
        exec_id = execution_id or f"sched-roll-{uuid4().hex[:12]}"

        # 1. Initialize PlatformBillingJobRun or return cached result if already COMPLETED
        existing_stmt = select(PlatformBillingJobRun).where(PlatformBillingJobRun.execution_id == exec_id)
        existing_job = (await self.session.execute(existing_stmt)).scalar_one_or_none()
        if existing_job:
            if existing_job.status == BillingJobRunStatus.COMPLETED.value:
                logger.info("Job run '%s' already COMPLETED. Returning idempotent result.", exec_id)
                return BillingBatchExecutionResult(
                    job_run_id=existing_job.id,
                    execution_id=exec_id,
                    job_type=existing_job.job_type,
                    status=existing_job.status,
                    started_at=existing_job.started_at,
                    completed_at=existing_job.completed_at,
                    processed_count=existing_job.processed_count,
                    succeeded_count=existing_job.succeeded_count,
                    failed_count=existing_job.failed_count,
                    skipped_count=existing_job.skipped_count,
                    results=[],
                    errors=[],
                )
            job_run = existing_job
        else:
            job_run = PlatformBillingJobRun(
                id=uuid4(),
                job_type=BillingJobType.PERIOD_ROLL.value,
                execution_id=exec_id,
                status=BillingJobRunStatus.RUNNING.value,
                started_at=started_at,
                processed_count=0,
                succeeded_count=0,
                failed_count=0,
                skipped_count=0,
            )
            self.session.add(job_run)
            await self.session.flush()

        # 2. Detect Due Subscriptions
        due_subscriptions = await self.detect_due_subscriptions(
            cutoff_utc=effective_cutoff,
            batch_size=batch_size,
        )

        processed_count = len(due_subscriptions)
        succeeded_count = 0
        failed_count = 0
        skipped_count = 0
        results: list[SubscriptionRollResult] = []
        errors: list[str] = []

        # 3. Process each subscription with savepoint isolation
        for sub in due_subscriptions:
            try:
                async with self.session.begin_nested():
                    roll_result = await self.roll_single_subscription(
                        subscription_id=sub.id,
                        cutoff_utc=effective_cutoff,
                        execution_id=exec_id,
                    )

                results.append(roll_result)
                if roll_result.status in ("ROLLED", "CANCELLED"):
                    succeeded_count += 1
                elif roll_result.status == "SKIPPED":
                    skipped_count += 1
                else:
                    failed_count += 1

            except Exception as exc:
                failed_count += 1
                err_msg = f"Subscription {sub.id} roll failed: {str(exc)[:250]}"
                logger.error(err_msg, exc_info=True)
                errors.append(err_msg)
                results.append(
                    SubscriptionRollResult(
                        subscription_id=sub.id,
                        society_id=sub.society_id,
                        status="FAILED",
                        error_message=str(exc)[:500],
                    )
                )

        completed_at = _utc_now()

        # 4. Finalize Job Status
        final_status = BillingJobRunStatus.COMPLETED
        if failed_count > 0:
            final_status = BillingJobRunStatus.PARTIAL if succeeded_count > 0 else BillingJobRunStatus.FAILED

        job_run.status = final_status.value
        job_run.completed_at = completed_at
        job_run.processed_count = processed_count
        job_run.succeeded_count = succeeded_count
        job_run.failed_count = failed_count
        job_run.skipped_count = skipped_count
        job_run.error_summary = "\n".join(errors) if errors else None
        job_run.diagnostics = {
            "batch_size": batch_size,
            "cutoff_utc": effective_cutoff.isoformat(),
            "duration_seconds": (completed_at - started_at).total_seconds(),
        }

        await self.session.commit()

        logger.info(
            "Billing batch %s finished: status=%s, processed=%d, succeeded=%d, skipped=%d, failed=%d",
            exec_id,
            final_status.value,
            processed_count,
            succeeded_count,
            skipped_count,
            failed_count,
        )

        return BillingBatchExecutionResult(
            execution_id=exec_id,
            job_type=BillingJobType.PERIOD_ROLL.value,
            job_run_id=job_run.id,
            status=final_status,
            started_at=started_at,
            completed_at=completed_at,
            processed_count=processed_count,
            succeeded_count=succeeded_count,
            failed_count=failed_count,
            skipped_count=skipped_count,
            results=results,
            error_summary=job_run.error_summary,
            diagnostics=job_run.diagnostics,
        )
