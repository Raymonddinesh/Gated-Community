"""Phase 21E.4D — Statutory Billing Issuer Configuration.

Loads configurable corporate, tax, and GST credentials:
- Never hardcodes corporate credentials into PDF templates.
- Enforces consistency with statutory GST guidelines and place of supply rules.
- Explicit Disclaimer: Corporate CIN, GSTIN, and Registered Address must be verified
  and signed off by a certified Chartered Accountant prior to live production invoice issuance.
"""

from dataclasses import dataclass

from apps.api.src.core.config import get_settings


@dataclass(frozen=True)
class BillingIssuerConfig:
    """Configurable statutory billing issuer metadata."""

    legal_name: str
    trade_name: str
    cin: str
    pan: str
    gstin: str
    registered_address: str
    billing_email: str
    support_phone: str
    state_code: str
    state_name: str


def get_issuer_config() -> BillingIssuerConfig:
    """Load validated billing issuer configuration from environment settings."""
    settings = get_settings()
    return BillingIssuerConfig(
        legal_name=settings.ISSUER_LEGAL_NAME,
        trade_name=settings.ISSUER_TRADE_NAME,
        cin=settings.ISSUER_CIN,
        pan=settings.ISSUER_PAN,
        gstin=settings.ISSUER_GSTIN,
        registered_address=settings.ISSUER_REGISTERED_ADDRESS,
        billing_email=settings.ISSUER_BILLING_EMAIL,
        support_phone=settings.ISSUER_SUPPORT_PHONE,
        state_code=settings.ISSUER_STATE_CODE,
        state_name=settings.ISSUER_STATE_NAME,
    )
