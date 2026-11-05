"""Vehicle Access Hardware & Protocol Provider Abstraction.

Prepares SocietySphere for future RFID, ANPR, and barrier gate integrations
without redesigning or coupling to the core vehicle domain.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal
from typing import Any


@dataclass(frozen=True)
class VehicleDetectionResult:
    """Result returned by a detection provider."""

    raw_plate: str
    normalized_plate: str
    detection_method: str  # MANUAL, RFID, ANPR
    source_provider: str
    confidence_score: Decimal | None = None
    captured_image_ref: str | None = None
    metadata: dict[str, Any] | None = None


class VehicleAccessProvider(ABC):
    """Abstract provider interface for gate detection hardware / services."""

    @property
    @abstractmethod
    def provider_code(self) -> str:
        """Unique code identifying this provider."""
        ...

    @abstractmethod
    async def process_detection(self, payload: dict[str, Any]) -> VehicleDetectionResult:
        """Process incoming detection event into a normalized detection result."""
        ...


class ManualVehicleAccessProvider(VehicleAccessProvider):
    """
    Default access provider representing manual security guard / operator entry.
    """

    @property
    def provider_code(self) -> str:
        return "MANUAL"

    async def process_detection(self, payload: dict[str, Any]) -> VehicleDetectionResult:
        raw_plate = payload.get("registration_number", "").strip()
        from apps.api.src.vehicles.domain.normalization import normalize_registration_number

        normalized = normalize_registration_number(raw_plate)
        return VehicleDetectionResult(
            raw_plate=raw_plate,
            normalized_plate=normalized,
            detection_method="MANUAL",
            source_provider=self.provider_code,
            confidence_score=Decimal("1.000"),
            captured_image_ref=payload.get("captured_image_ref"),
            metadata=payload.get("metadata"),
        )


class RFIDVehicleAccessProvider(VehicleAccessProvider):
    """
    Stub provider for future FastTag / RFID gate reader integrations.
    """

    @property
    def provider_code(self) -> str:
        return "RFID_STUB"

    async def process_detection(self, payload: dict[str, Any]) -> VehicleDetectionResult:
        raw_plate = payload.get("registration_number", "").strip()
        from apps.api.src.vehicles.domain.normalization import normalize_registration_number

        normalized = normalize_registration_number(raw_plate)
        tag_id = payload.get("rfid_tag_id", "SIMULATED_TAG")
        return VehicleDetectionResult(
            raw_plate=raw_plate,
            normalized_plate=normalized,
            detection_method="RFID",
            source_provider=self.provider_code,
            confidence_score=Decimal("1.000"),
            metadata={"rfid_tag_id": tag_id, **payload.get("metadata", {})},
        )


class ANPRVehicleAccessProvider(VehicleAccessProvider):
    """
    Stub provider for future Automatic Number Plate Recognition (ANPR) camera integrations.
    """

    @property
    def provider_code(self) -> str:
        return "ANPR_STUB"

    async def process_detection(self, payload: dict[str, Any]) -> VehicleDetectionResult:
        raw_plate = payload.get("registration_number", "").strip()
        from apps.api.src.vehicles.domain.normalization import normalize_registration_number

        normalized = normalize_registration_number(raw_plate)
        raw_confidence = payload.get("confidence_score", "0.950")
        confidence = Decimal(str(raw_confidence))
        image_ref = payload.get("captured_image_ref") or "anpr/snapshots/simulated_frame.jpg"

        return VehicleDetectionResult(
            raw_plate=raw_plate,
            normalized_plate=normalized,
            detection_method="ANPR",
            source_provider=self.provider_code,
            confidence_score=confidence,
            captured_image_ref=image_ref,
            metadata=payload.get("metadata"),
        )


_PROVIDERS: dict[str, type[VehicleAccessProvider]] = {
    "MANUAL": ManualVehicleAccessProvider,
    "RFID": RFIDVehicleAccessProvider,
    "RFID_STUB": RFIDVehicleAccessProvider,
    "ANPR": ANPRVehicleAccessProvider,
    "ANPR_STUB": ANPRVehicleAccessProvider,
}


def get_vehicle_access_provider(provider_type: str = "MANUAL") -> VehicleAccessProvider:
    """Factory function to instantiate access provider by type code."""
    provider_cls = _PROVIDERS.get(provider_type.upper(), ManualVehicleAccessProvider)
    return provider_cls()
