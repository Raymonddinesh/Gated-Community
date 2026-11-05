"""Chart of Accounts (COA) Application Service."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.core.exceptions import ConflictException, NotFoundException
from apps.api.src.database.models.finance import Account
from apps.api.src.database.repositories.audit_repository import AuditRepository
from apps.api.src.finance.domain.models import AccountType, default_normal_balance
from apps.api.src.finance.infrastructure.repositories import AccountRepository


class AccountService:
    """Service managing the hierarchical Chart of Accounts (COA) within tenant boundaries."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.account_repo = AccountRepository(session)
        self.audit_repo = AuditRepository(session)

    async def create_account(
        self,
        society_id: UUID,
        account_code: str,
        account_name: str,
        account_type: str,
        sub_type: str | None = None,
        parent_account_id: UUID | None = None,
        normal_balance: str | None = None,
        currency: str = "INR",
        is_system_account: bool = False,
        created_by: UUID | None = None,
        correlation_id: str | None = None,
    ) -> Account:
        """Create a new ledger account, validating uniqueness within society."""
        code_clean = account_code.strip().upper()

        # Enforce uniqueness within society
        existing = await self.account_repo.get_by_code(society_id, code_clean)
        if existing:
            raise ConflictException(
                f"Account with code '{code_clean}' already exists in this society ('{existing.account_name}')."
            )

        # Validate parent account if provided (must belong to same society)
        if parent_account_id:
            parent = await self.account_repo.get_by_id(parent_account_id, society_id)
            if not parent:
                raise NotFoundException(
                    f"Parent account '{parent_account_id}' does not exist in this society."
                )

        # Default normal balance based on account type if not specified
        resolved_normal = (
            normal_balance if normal_balance else default_normal_balance(AccountType(account_type)).value
        )

        account = await self.account_repo.create_account(
            society_id=society_id,
            account_code=code_clean,
            account_name=account_name.strip(),
            account_type=account_type,
            sub_type=sub_type,
            parent_account_id=parent_account_id,
            normal_balance=resolved_normal,
            currency=currency,
            is_system_account=is_system_account,
        )

        await self.audit_repo.log_event(
            action="FINANCE_ACCOUNT_CREATED",
            entity_type="account",
            entity_id=str(account.id),
            society_id=society_id,
            actor_user_id=created_by,
            correlation_id=correlation_id,
            after_state={
                "code": account.account_code,
                "name": account.account_name,
                "type": account.account_type,
            },
        )

        return account

    async def deactivate_account(
        self,
        account_id: UUID,
        society_id: UUID,
        deactivated_by: UUID | None = None,
        correlation_id: str | None = None,
    ) -> Account:
        """Deactivate account preventing new postings while preserving historical integrity."""
        account = await self.account_repo.get_by_id(account_id, society_id)
        if not account:
            raise NotFoundException(f"Account '{account_id}' not found.")

        if not account.is_active:
            return account

        await self.account_repo.deactivate_account(account_id, society_id)

        await self.audit_repo.log_event(
            action="FINANCE_ACCOUNT_DEACTIVATED",
            entity_type="account",
            entity_id=str(account.id),
            society_id=society_id,
            actor_user_id=deactivated_by,
            correlation_id=correlation_id,
            before_state={"is_active": True},
            after_state={"is_active": False},
        )

        account.is_active = False
        return account
