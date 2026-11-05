"""Phase 21E.4A — Indian GST Tax Engine and Configuration Module.

Exported components:
- Domain Exceptions: TaxDomainException, InvalidPlaceOfSupplyException, InvalidGSTINException, etc.
- Models & Enums: TaxComponentType, SupplyType, SupplyCategory, TaxRateConfig, PlaceOfSupplyResult, etc.
- Core Services:
    - GSTINValidator: Indian GSTIN format and Luhn Mod-36 checksum validation.
    - PlaceOfSupplyService: Statutory place of supply resolution (Sec 12/13 IGST Act).
    - TaxConfigurationService / tax_config_service: Configurable SAC rules and rate versions.
    - GSTTaxEngine: High-precision Decimal GST computation (CGST+SGST / IGST).
    - TaxSnapshotService: Cryptographically verifiable immutable tax snapshots.
"""

from apps.api.src.subscriptions.tax.engine import GSTTaxEngine, quantize_money
from apps.api.src.subscriptions.tax.exceptions import (
    IncompatibleCreditNoteTaxException,
    InvalidGSTINException,
    InvalidPlaceOfSupplyException,
    TaxCalculationException,
    TaxConfigurationNotFoundException,
    TaxDomainException,
    TaxSnapshotTamperedException,
)
from apps.api.src.subscriptions.tax.gstin_validator import (
    GSTINValidationResult,
    GSTINValidator,
)
from apps.api.src.subscriptions.tax.models import (
    PlaceOfSupplyInput,
    PlaceOfSupplyResult,
    SupplyCategory,
    SupplyType,
    TaxCalculationInput,
    TaxCalculationResult,
    TaxComponentType,
    TaxRateConfig,
    TaxRuleStatus,
    TaxSnapshot,
)
from apps.api.src.subscriptions.tax.place_of_supply import PlaceOfSupplyService
from apps.api.src.subscriptions.tax.snapshot import TaxSnapshotService
from apps.api.src.subscriptions.tax.state_codes import (
    GST_STATE_CODES,
    get_canonical_state_name,
    get_state_code,
    normalize_state,
)
from apps.api.src.subscriptions.tax.tax_config import (
    TaxConfigurationService,
    tax_config_service,
)

__all__ = [
    # Engine & Math
    "GSTTaxEngine",
    "quantize_money",
    # Services
    "GSTINValidator",
    "PlaceOfSupplyService",
    "TaxConfigurationService",
    "tax_config_service",
    "TaxSnapshotService",
    # State Codes
    "GST_STATE_CODES",
    "normalize_state",
    "get_state_code",
    "get_canonical_state_name",
    # Enums
    "TaxComponentType",
    "SupplyType",
    "SupplyCategory",
    "TaxRuleStatus",
    # Models & Schemas
    "TaxRateConfig",
    "PlaceOfSupplyInput",
    "PlaceOfSupplyResult",
    "TaxCalculationInput",
    "TaxCalculationResult",
    "TaxSnapshot",
    "GSTINValidationResult",
    # Exceptions
    "TaxDomainException",
    "InvalidPlaceOfSupplyException",
    "InvalidGSTINException",
    "TaxConfigurationNotFoundException",
    "TaxCalculationException",
    "TaxSnapshotTamperedException",
    "IncompatibleCreditNoteTaxException",
]
