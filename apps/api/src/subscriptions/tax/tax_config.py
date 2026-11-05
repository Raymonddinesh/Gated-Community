"""Phase 21E.4A — Configurable GST Tax Rules and SAC Classification Registry.

Manages dynamic, versioned tax rules across Service Accounting Codes (SAC):
- Supports SAC classification, CGST/SGST/IGST breakdown, effective date ranges, and status.
- Decouples tax configuration from calculation logic (zero hardcoded rates or SACs).
- Initial proposed defaults:
    - SAC 998313: Information technology design and development services (18% GST).
    - SAC 998314: Internet telecommunication / IT infrastructure / SaaS hosting (18% GST).
- Explicit Disclaimer: Initial defaults are configurable proposals, NOT legally confirmed classifications.
"""

import threading
from datetime import date
from decimal import Decimal
from typing import Final

from apps.api.src.subscriptions.tax.exceptions import TaxConfigurationNotFoundException
from apps.api.src.subscriptions.tax.models import TaxRateConfig, TaxRuleStatus

# Initial Proposed Defaults (Configurable Proposals, Not Legally Confirmed)
DEFAULT_RULES: Final[list[TaxRateConfig]] = [
    TaxRateConfig(
        sac_code="998313",
        description="Information technology (IT) design, development, and maintenance services",
        total_rate=Decimal("18.00"),
        cgst_rate=Decimal("9.00"),
        sgst_rate=Decimal("9.00"),
        igst_rate=Decimal("18.00"),
        effective_from=date(2017, 7, 1),
        effective_to=None,
        status=TaxRuleStatus.ACTIVE,
        version="1.0",
        is_reverse_charge=False,
        is_exempt=False,
    ),
    TaxRateConfig(
        sac_code="998314",
        description="Internet telecommunication, IT infrastructure provision, and SaaS web hosting",
        total_rate=Decimal("18.00"),
        cgst_rate=Decimal("9.00"),
        sgst_rate=Decimal("9.00"),
        igst_rate=Decimal("18.00"),
        effective_from=date(2017, 7, 1),
        effective_to=None,
        status=TaxRuleStatus.ACTIVE,
        version="1.0",
        is_reverse_charge=False,
        is_exempt=False,
    ),
]


class TaxConfigurationService:
    """Thread-safe, versioned tax configuration service managing SAC rules and rates."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._rules: list[TaxRateConfig] = list(DEFAULT_RULES)

    def register_rule(self, rule: TaxRateConfig) -> None:
        """Register or supersede a tax rate rule."""
        with self._lock:
            # If replacing an existing rule with same SAC and version, remove old one
            self._rules = [
                r for r in self._rules
                if not (r.sac_code == rule.sac_code and r.version == rule.version)
            ]
            self._rules.append(rule)

    def get_rule(
        self,
        sac_code: str,
        effective_date: date | None = None,
    ) -> TaxRateConfig:
        """Lookup applicable active tax rule for an SAC code on a specific date.

        If effective_date is None, defaults to current date.
        """
        target_date = effective_date or date.today()
        cleaned_sac = sac_code.strip()

        with self._lock:
            candidates: list[TaxRateConfig] = []
            for r in self._rules:
                if r.sac_code != cleaned_sac:
                    continue
                if r.status != TaxRuleStatus.ACTIVE:
                    continue
                if r.effective_from > target_date:
                    continue
                if r.effective_to is not None and r.effective_to < target_date:
                    continue
                candidates.append(r)

            if not candidates:
                raise TaxConfigurationNotFoundException(
                    sac_code=cleaned_sac,
                    transaction_date=target_date.isoformat(),
                )

            # Sort by version descending to pick the latest version
            candidates.sort(key=lambda x: x.version, reverse=True)
            return candidates[0]

    def list_rules(self, sac_code: str | None = None) -> list[TaxRateConfig]:
        """List all registered tax rules, optionally filtered by SAC code."""
        with self._lock:
            if sac_code:
                cleaned = sac_code.strip()
                return [r for r in self._rules if r.sac_code == cleaned]
            return list(self._rules)

    def deactivate_rule(self, sac_code: str, version: str) -> None:
        """Mark a specific tax rule version as INACTIVE."""
        with self._lock:
            for idx, r in enumerate(self._rules):
                if r.sac_code == sac_code and r.version == version:
                    # Replace with inactive copy
                    updated = TaxRateConfig(
                        sac_code=r.sac_code,
                        description=r.description,
                        total_rate=r.total_rate,
                        cgst_rate=r.cgst_rate,
                        sgst_rate=r.sgst_rate,
                        igst_rate=r.igst_rate,
                        effective_from=r.effective_from,
                        effective_to=r.effective_to,
                        status=TaxRuleStatus.INACTIVE,
                        version=r.version,
                        is_reverse_charge=r.is_reverse_charge,
                        is_exempt=r.is_exempt,
                    )
                    self._rules[idx] = updated
                    return
            raise TaxConfigurationNotFoundException(
                sac_code=sac_code,
                details={"version": version, "message": "Rule not found to deactivate."},
            )

    def reset_to_defaults(self) -> None:
        """Reset registry to initial default rules (used for test isolation)."""
        with self._lock:
            self._rules = list(DEFAULT_RULES)


# Global singleton instance for application usage
tax_config_service = TaxConfigurationService()
