"""Finance Central Router."""

from fastapi import APIRouter

from apps.api.src.finance.api.accounts import router as accounts_router
from apps.api.src.finance.api.config import router as config_router
from apps.api.src.finance.api.expenses import router as expenses_router
from apps.api.src.finance.api.journals import router as journals_router
from apps.api.src.finance.api.periods import router as periods_router
from apps.api.src.finance.api.reports import router as reports_router

router = APIRouter()

router.include_router(periods_router)
router.include_router(accounts_router)
router.include_router(journals_router)
router.include_router(expenses_router)
router.include_router(reports_router)
router.include_router(config_router)
