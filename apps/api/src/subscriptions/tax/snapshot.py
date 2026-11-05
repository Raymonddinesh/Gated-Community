"""Phase 21E.4A — Immutable Tax Snapshot Generator and Integrity Verifier.

Creates cryptographically signed, immutable snapshots of tax calculations for historical
invoices, credit notes, and statutory audits. Ensures that changes to current tax rules
never cause historical invoice records or credit calculations to drift.
"""

import hashlib
import json
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from apps.api.src.subscriptions.tax.exceptions import TaxSnapshotTamperedException
from apps.api.src.subscriptions.tax.models import (
    PlaceOfSupplyResult,
    TaxRateConfig,
    TaxSnapshot,
)


class TaxSnapshotService:
    """Service generating, serializing, and cryptographically verifying TaxSnapshots."""

    @staticmethod
    def compute_integrity_hash(
        sac_code: str,
        tax_rate: Decimal,
        taxable_value: Decimal,
        cgst_amount: Decimal,
        sgst_amount: Decimal,
        igst_amount: Decimal,
        total_tax: Decimal,
        grand_total: Decimal,
        supplier_state_code: str,
        place_of_supply_code: str,
        supply_type: str,
        tax_config_version: str,
        calculation_timestamp: datetime,
        currency_code: str,
        invoice_id: UUID | None = None,
        commercial_discount: Decimal = Decimal("0.00"),
        prorated_credit: Decimal = Decimal("0.00"),
    ) -> str:
        """Compute a deterministic SHA-256 hash over canonical tax calculation attributes."""
        canonical_payload = {
            "sac_code": sac_code,
            "tax_rate": str(tax_rate),
            "taxable_value": str(taxable_value),
            "cgst_amount": str(cgst_amount),
            "sgst_amount": str(sgst_amount),
            "igst_amount": str(igst_amount),
            "total_tax": str(total_tax),
            "grand_total": str(grand_total),
            "supplier_state_code": supplier_state_code,
            "place_of_supply_code": place_of_supply_code,
            "supply_type": supply_type,
            "tax_config_version": tax_config_version,
            "calculation_timestamp": calculation_timestamp.isoformat(),
            "currency_code": currency_code,
        }
        if invoice_id is not None:
            canonical_payload["invoice_id"] = str(invoice_id)
        if commercial_discount > Decimal("0.00"):
            canonical_payload["commercial_discount"] = str(commercial_discount)
        if prorated_credit > Decimal("0.00"):
            canonical_payload["prorated_credit"] = str(prorated_credit)
        encoded = json.dumps(canonical_payload, sort_keys=True).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    @classmethod
    def create_snapshot(
        cls,
        sac_code: str,
        tax_rule: TaxRateConfig,
        pos_result: PlaceOfSupplyResult,
        taxable_value: Decimal,
        cgst_amount: Decimal,
        sgst_amount: Decimal,
        igst_amount: Decimal,
        total_tax: Decimal,
        grand_total: Decimal,
        calculation_timestamp: datetime,
        currency_code: str = "INR",
        snapshot_id: UUID | None = None,
        invoice_id: UUID | None = None,
        commercial_discount: Decimal = Decimal("0.00"),
        prorated_credit: Decimal = Decimal("0.00"),
    ) -> TaxSnapshot:
        """Create an immutable, hashed TaxSnapshot."""
        snap_id = snapshot_id or uuid4()
        integrity_hash = cls.compute_integrity_hash(
            sac_code=sac_code,
            tax_rate=tax_rule.total_rate,
            taxable_value=taxable_value,
            cgst_amount=cgst_amount,
            sgst_amount=sgst_amount,
            igst_amount=igst_amount,
            total_tax=total_tax,
            grand_total=grand_total,
            supplier_state_code=pos_result.supplier_state_code,
            place_of_supply_code=pos_result.place_of_supply_code,
            supply_type=pos_result.supply_type.value,
            tax_config_version=tax_rule.version,
            calculation_timestamp=calculation_timestamp,
            currency_code=currency_code,
            invoice_id=invoice_id,
            commercial_discount=commercial_discount,
            prorated_credit=prorated_credit,
        )

        return TaxSnapshot(
            snapshot_id=snap_id,
            invoice_id=invoice_id,
            sac_code=sac_code,
            tax_rate=tax_rule.total_rate,
            taxable_value=taxable_value,
            commercial_discount=commercial_discount,
            prorated_credit=prorated_credit,
            cgst_rate=tax_rule.cgst_rate if pos_result.supply_type.value == "INTRA_STATE" else Decimal("0.00"),
            cgst_amount=cgst_amount,
            sgst_rate=tax_rule.sgst_rate if pos_result.supply_type.value == "INTRA_STATE" else Decimal("0.00"),
            sgst_amount=sgst_amount,
            igst_rate=tax_rule.igst_rate if pos_result.supply_type.value == "INTER_STATE" else Decimal("0.00"),
            igst_amount=igst_amount,
            total_tax=total_tax,
            grand_total=grand_total,
            supplier_state=pos_result.supplier_state,
            supplier_state_code=pos_result.supplier_state_code,
            customer_state=pos_result.customer_state or pos_result.place_of_supply_state,
            customer_state_code=pos_result.customer_state_code or pos_result.place_of_supply_code,
            customer_gstin=pos_result.customer_gstin,
            place_of_supply=pos_result.place_of_supply_state,
            place_of_supply_code=pos_result.place_of_supply_code,
            supply_type=pos_result.supply_type,
            supply_category=pos_result.supply_category,
            tax_config_version=tax_rule.version,
            calculation_timestamp=calculation_timestamp,
            currency_code=currency_code,
            integrity_hash=integrity_hash,
        )

    @classmethod
    def verify_snapshot_integrity(cls, snapshot: TaxSnapshot) -> bool:
        """Verify that the TaxSnapshot's stored hash matches its recalculated digest."""
        expected_hash = cls.compute_integrity_hash(
            sac_code=snapshot.sac_code,
            tax_rate=snapshot.tax_rate,
            taxable_value=snapshot.taxable_value,
            cgst_amount=snapshot.cgst_amount,
            sgst_amount=snapshot.sgst_amount,
            igst_amount=snapshot.igst_amount,
            total_tax=snapshot.total_tax,
            grand_total=snapshot.grand_total,
            supplier_state_code=snapshot.supplier_state_code,
            place_of_supply_code=snapshot.place_of_supply_code,
            supply_type=snapshot.supply_type.value,
            tax_config_version=snapshot.tax_config_version,
            calculation_timestamp=snapshot.calculation_timestamp,
            currency_code=snapshot.currency_code,
            invoice_id=snapshot.invoice_id,
            commercial_discount=snapshot.commercial_discount,
            prorated_credit=snapshot.prorated_credit,
        )
        return expected_hash == snapshot.integrity_hash

    @classmethod
    def assert_valid_snapshot(cls, snapshot: TaxSnapshot) -> None:
        """Raise TaxSnapshotTamperedException if snapshot digest does not verify."""
        if not cls.verify_snapshot_integrity(snapshot):
            raise TaxSnapshotTamperedException(snapshot_id=snapshot.snapshot_id)

    @staticmethod
    def to_dict(snapshot: TaxSnapshot) -> dict[str, Any]:
        """Convert snapshot to JSON-serializable dictionary for DB JSONB storage."""
        data = snapshot.model_dump()
        data["snapshot_id"] = str(data["snapshot_id"])
        data["invoice_id"] = str(data["invoice_id"]) if data.get("invoice_id") else None
        data["tax_rate"] = str(data["tax_rate"])
        data["taxable_value"] = str(data["taxable_value"])
        data["commercial_discount"] = str(data.get("commercial_discount", "0.00"))
        data["prorated_credit"] = str(data.get("prorated_credit", "0.00"))
        data["cgst_rate"] = str(data["cgst_rate"])
        data["cgst_amount"] = str(data["cgst_amount"])
        data["sgst_rate"] = str(data["sgst_rate"])
        data["sgst_amount"] = str(data["sgst_amount"])
        data["igst_rate"] = str(data["igst_rate"])
        data["igst_amount"] = str(data["igst_amount"])
        data["total_tax"] = str(data["total_tax"])
        data["grand_total"] = str(data["grand_total"])
        data["calculation_timestamp"] = data["calculation_timestamp"].isoformat()
        data["supply_type"] = data["supply_type"].value if hasattr(data["supply_type"], "value") else str(data["supply_type"])
        data["supply_category"] = data["supply_category"].value if hasattr(data["supply_category"], "value") else str(data["supply_category"])
        return data
