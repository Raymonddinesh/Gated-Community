"""Phase 21E.6 — SaaS Billing Automation Schemas & DTOs."""

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class BillingJobRunStatus(StrEnum):
    """Execution status for automated billing scheduler jobs."""

    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    PARTIAL = "PARTIAL"


class BillingJobType(StrEnum):
    """Types of automated batch billing operations."""

    PERIOD_ROLL = "PERIOD_ROLL"
    RENEWAL_INVOICING = "RENEWAL_INVOICING"
    DUNNING_EVAL = "DUNNING_EVAL"


class SubscriptionRollResult(BaseModel):
    """Per-subscription execution outcome within a billing scheduler run."""

    model_config = ConfigDict(frozen=True)

    subscription_id: UUID
    society_id: UUID
    status: str  # 'ROLLED', 'INVOICED', 'SKIPPED', 'FAILED'
    invoice_id: UUID | None = None
    invoice_number: str | None = None
    old_period_start: datetime | None = None
    old_period_end: datetime | None = None
    new_period_start: datetime | None = None
    new_period_end: datetime | None = None
    new_next_billing_at: datetime | None = None
    skip_reason: str | None = None
    error_message: str | None = None


class BillingBatchExecutionResult(BaseModel):
    """Aggregate result of a batch billing scheduler execution run."""

    model_config = ConfigDict(frozen=True)

    execution_id: str
    job_type: str
    job_run_id: UUID | None = None
    status: BillingJobRunStatus
    started_at: datetime
    completed_at: datetime | None = None
    processed_count: int = 0
    succeeded_count: int = 0
    failed_count: int = 0
    skipped_count: int = 0
    results: list[SubscriptionRollResult] = Field(default_factory=list)
    error_summary: str | None = None
    diagnostics: dict[str, Any] | None = None
