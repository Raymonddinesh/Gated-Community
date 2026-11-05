"""Accounting Provider Interface and Data Transfer Objects."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from apps.api.src.finance.domain.models import quantize_amount


@dataclass
class JournalLineDTO:
    account_code: str
    debit_amount: Decimal = Decimal("0.0000")
    credit_amount: Decimal = Decimal("0.0000")
    description: str | None = None

    def __post_init__(self) -> None:
        self.debit_amount = quantize_amount(self.debit_amount)
        self.credit_amount = quantize_amount(self.credit_amount)


@dataclass
class JournalEntryDTO:
    journal_number: str | None
    entry_date: date
    description: str
    lines: list[JournalLineDTO]
    source_type: str = "MANUAL"
    source_record_id: str | None = None
    reference_number: str | None = None
    currency: str = "INR"
    idempotency_key: str | None = None


@dataclass
class ProviderResult:
    success: bool
    message: str
    record_id: str | None = None
    journal_number: str | None = None
    details: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)


class AccountingProvider(ABC):
    """Abstract Strategy interface for financial accounting operations."""

    @abstractmethod
    async def create_entry(self, society_id: UUID, entry: JournalEntryDTO) -> ProviderResult:
        """Create a draft journal entry."""
        ...

    @abstractmethod
    async def post_entry(self, society_id: UUID, journal_id: UUID, posted_by: UUID | None) -> ProviderResult:
        """Commit/post an entry to the permanent ledger."""
        ...

    @abstractmethod
    async def reverse_entry(
        self, society_id: UUID, journal_id: UUID, reason: str, reversed_by: UUID | None
    ) -> ProviderResult:
        """Create and post a balanced reversal entry."""
        ...

    @abstractmethod
    async def get_balance(self, society_id: UUID, account_code: str) -> Decimal:
        """Retrieve closing balance for an account."""
        ...

    @abstractmethod
    async def export_entries(self, society_id: UUID, period_id: UUID | None = None) -> list[dict[str, Any]]:
        """Export ledger entries for data interchange."""
        ...

    @abstractmethod
    async def import_entries(
        self, society_id: UUID, entries: list[JournalEntryDTO], dry_run: bool = True
    ) -> ProviderResult:
        """Validate or import external entries."""
        ...

    @abstractmethod
    async def health_check(self, society_id: UUID) -> bool:
        """Verify provider availability."""
        ...
