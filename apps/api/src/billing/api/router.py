"""Billing Module Master API Router."""

from fastapi import APIRouter

from apps.api.src.billing.api import (
    config,
    invoices,
    payments,
    periods,
    receipts,
    reconciliation,
    reports,
    resident,
    rules,
)

router = APIRouter()

router.include_router(config.router)
router.include_router(rules.router)
router.include_router(periods.router)
router.include_router(invoices.router)
router.include_router(payments.router)
router.include_router(receipts.router)
router.include_router(reconciliation.router)
router.include_router(reports.router)
router.include_router(resident.router)
