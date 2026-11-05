"""Phase 21E.4A — Indian GST Place of Supply Determination Service.

Implements statutory place of supply (POS) resolution under Section 12 and 13
of the Integrated Goods and Services Tax (IGST) Act, 2017:
- B2B Supply (Section 12(2)(a)): Location of the registered person (derived from verified GSTIN state).
- B2C Supply (Section 12(2)(b)): Location of the recipient on record (customer billing address state).
- Intra-State vs Inter-State:
    - Intra-State (Supplier State == Place of Supply): CGST + SGST apply.
    - Inter-State (Supplier State != Place of Supply): IGST applies.
- Safe-fail guarantee: Unresolved, missing, or contradictory state data fails safely
  with InvalidPlaceOfSupplyException rather than applying incorrect taxation.
"""

import logging
from typing import Final

from apps.api.src.subscriptions.tax.exceptions import (
    InvalidGSTINException,
    InvalidPlaceOfSupplyException,
)
from apps.api.src.subscriptions.tax.gstin_validator import GSTINValidator
from apps.api.src.subscriptions.tax.models import (
    PlaceOfSupplyInput,
    PlaceOfSupplyResult,
    SupplyCategory,
    SupplyType,
    TaxComponentType,
)
from apps.api.src.subscriptions.tax.state_codes import (
    GST_STATE_CODES,
    normalize_state,
)

logger = logging.getLogger("societysphere.tax.place_of_supply")

POLICY_B2B_SEC_12_2_A: Final[str] = "IGST_ACT_SECTION_12_2_A_B2B"
POLICY_B2C_SEC_12_2_B: Final[str] = "IGST_ACT_SECTION_12_2_B_B2C"


class PlaceOfSupplyService:
    """Statutory Place of Supply resolution engine for SaaS subscriptions."""

    def __init__(self, strict_b2b_state_match: bool = False) -> None:
        """Initialize PlaceOfSupplyService.

        Args:
            strict_b2b_state_match: If True, raises an exception if customer billing state
                conflicts with customer GSTIN state. If False, GSTIN state takes legal precedence
                under Sec 12(2)(a).
        """
        self.strict_b2b_state_match = strict_b2b_state_match

    def determine_place_of_supply(self, pos_input: PlaceOfSupplyInput) -> PlaceOfSupplyResult:
        """Determine legal place of supply and applicable tax components.

        Raises:
            InvalidPlaceOfSupplyException: When supplier or customer location is unresolved.
            InvalidGSTINException: When customer GSTIN is provided but structurally invalid.
        """
        # 1. Resolve Supplier State
        supplier_norm = normalize_state(pos_input.supplier_state)
        if not supplier_norm:
            raise InvalidPlaceOfSupplyException(
                reason="SUPPLIER_STATE_UNRESOLVED",
                supplier_state=pos_input.supplier_state,
                details={"provided_supplier_state": pos_input.supplier_state},
            )
        supplier_state_name, supplier_state_code = supplier_norm

        # 2. Resolve Customer State (if provided)
        customer_state_name: str | None = None
        customer_state_code: str | None = None
        if pos_input.customer_state:
            customer_norm = normalize_state(pos_input.customer_state)
            if customer_norm:
                customer_state_name, customer_state_code = customer_norm
            elif not pos_input.customer_gstin:
                # If no GSTIN, unresolvable customer state is a fatal error
                raise InvalidPlaceOfSupplyException(
                    reason="CUSTOMER_STATE_UNRESOLVED",
                    customer_state=pos_input.customer_state,
                    details={"provided_customer_state": pos_input.customer_state},
                )

        # 3. Determine Supply Category (B2B vs B2C)
        cleaned_gstin = pos_input.customer_gstin.strip().upper() if pos_input.customer_gstin else None

        if cleaned_gstin:
            # --- B2B FLOW ---
            gstin_res = GSTINValidator.validate(cleaned_gstin, verify_checksum=True)
            if not gstin_res.is_valid:
                raise InvalidGSTINException(
                    gstin=cleaned_gstin,
                    reason=gstin_res.error_message or "Structural or checksum validation failed.",
                    details={
                        "syntactic_valid": gstin_res.syntactic_valid,
                        "checksum_valid": gstin_res.checksum_valid,
                    },
                )

            assert gstin_res.state_code is not None
            gstin_state_code = gstin_res.state_code
            gstin_state_name = GST_STATE_CODES[gstin_state_code]

            # Check for conflict between customer billing state and GSTIN state
            if customer_state_code and customer_state_code != gstin_state_code:
                if self.strict_b2b_state_match:
                    raise InvalidPlaceOfSupplyException(
                        reason="B2B_STATE_GSTIN_MISMATCH",
                        customer_state=customer_state_name,
                        customer_gstin=cleaned_gstin,
                        details={
                            "billing_state_code": customer_state_code,
                            "gstin_state_code": gstin_state_code,
                        },
                    )
                logger.warning(
                    "Customer billing state (%s) differs from GSTIN registered state (%s). "
                    "Under Section 12(2)(a) of IGST Act, GSTIN registered location governs Place of Supply.",
                    customer_state_name,
                    gstin_state_name,
                )

            # In B2B, GSTIN state governs place of supply
            pos_state_name = gstin_state_name
            pos_state_code = gstin_state_code
            category = SupplyCategory.B2B
            policy = POLICY_B2B_SEC_12_2_A

        else:
            # --- B2C FLOW ---
            if not customer_state_code or not customer_state_name:
                raise InvalidPlaceOfSupplyException(
                    reason="CUSTOMER_BILLING_STATE_REQUIRED_FOR_B2C",
                    details={"message": "Unregistered customers must have a valid billing state on record."},
                )

            pos_state_name = customer_state_name
            pos_state_code = customer_state_code
            category = SupplyCategory.B2C
            policy = POLICY_B2C_SEC_12_2_B

        # 4. Intra-State vs Inter-State Evaluation
        components: tuple[TaxComponentType, ...]
        if pos_state_code == supplier_state_code:
            supply_type = SupplyType.INTRA_STATE
            components = (TaxComponentType.CGST, TaxComponentType.SGST)
            reason = (
                f"Intra-state supply: Supplier location ({supplier_state_name} [{supplier_state_code}]) "
                f"matches Place of Supply ({pos_state_name} [{pos_state_code}]). "
                f"Applicable components: CGST + SGST."
            )
        else:
            supply_type = SupplyType.INTER_STATE
            components = (TaxComponentType.IGST,)
            reason = (
                f"Inter-state supply: Supplier location ({supplier_state_name} [{supplier_state_code}]) "
                f"differs from Place of Supply ({pos_state_name} [{pos_state_code}]). "
                f"Applicable component: IGST."
            )

        return PlaceOfSupplyResult(
            place_of_supply_state=pos_state_name,
            place_of_supply_code=pos_state_code,
            supplier_state=supplier_state_name,
            supplier_state_code=supplier_state_code,
            customer_state=customer_state_name,
            customer_state_code=customer_state_code,
            customer_gstin=cleaned_gstin,
            supply_type=supply_type,
            supply_category=category,
            applicable_components=components,
            policy_applied=policy,
            reason=reason,
        )
