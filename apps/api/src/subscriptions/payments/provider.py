"""Phase 21E.3 — Abstract Payment Gateway Provider Interface.

Defines the provider-independent interface required for B2B SaaS payment processing.
All gateway adapters (Razorpay, Stripe, Cashfree) must adhere to this interface.
"""

from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Any

from apps.api.src.subscriptions.payments.schemas import (
    GatewayOrderResponse,
    GatewayPaymentDetails,
    GatewayRefundResponse,
)


class PaymentGatewayProvider(ABC):
    """Abstract interface for external payment gateway communication."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Provider identifier string, e.g. 'RAZORPAY', 'STRIPE', 'CASHFREE'."""
        pass

    @abstractmethod
    async def create_payment_order(
        self,
        amount: Decimal,
        currency: str,
        receipt: str,
        notes: dict[str, Any] | None = None,
    ) -> GatewayOrderResponse:
        """Create a server-side payment order with the gateway.

        Args:
            amount: Authoritative monetary amount in standard currency units (e.g. 2500.00 INR).
            currency: ISO 3-letter currency code (e.g. 'INR').
            receipt: Unique internal receipt or attempt identifier.
            notes: Key-value metadata attached to the order.

        Returns:
            GatewayOrderResponse with provider order ID and status.
        """
        pass

    @abstractmethod
    async def fetch_payment(self, payment_id: str) -> GatewayPaymentDetails:
        """Fetch authoritative payment state from the gateway.

        Args:
            payment_id: Gateway payment identifier (e.g. 'pay_ABC123').

        Returns:
            GatewayPaymentDetails containing status, captured amounts, and card/UPI metadata.
        """
        pass

    @abstractmethod
    def verify_payment_signature(
        self,
        order_id: str,
        payment_id: str,
        signature: str,
    ) -> bool:
        """Verify client-submitted payment checkout signature.

        Args:
            order_id: Gateway order ID.
            payment_id: Gateway payment ID.
            signature: Cryptographic signature returned by client checkout SDK.

        Returns:
            True if signature matches; False otherwise.
        """
        pass

    @abstractmethod
    async def verify_payment(
        self,
        order_id: str,
        payment_id: str,
        signature: str,
    ) -> bool:
        """Verify checkout signature and confirm payment status with provider.

        Args:
            order_id: Gateway order ID.
            payment_id: Gateway payment ID.
            signature: Client checkout signature.

        Returns:
            True if valid and confirmed; False otherwise.
        """
        pass

    @abstractmethod
    async def initiate_refund(
        self,
        payment_id: str,
        amount: Decimal,
        currency: str,
        reason: str | None = None,
        notes: dict[str, Any] | None = None,
    ) -> GatewayRefundResponse:
        """Initiate a full or partial refund against a captured payment.

        Args:
            payment_id: Gateway payment ID to refund.
            amount: Refund amount in standard currency units.
            currency: ISO 3-letter currency code.
            reason: Business justification for refund.
            notes: Additional metadata for gateway audit.

        Returns:
            GatewayRefundResponse containing gateway refund ID and status.
        """
        pass

    @abstractmethod
    async def fetch_refund(
        self,
        refund_id: str,
        payment_id: str | None = None,
    ) -> GatewayRefundResponse:
        """Fetch status and details of an existing refund from the gateway.

        Args:
            refund_id: Gateway refund identifier (e.g. 'rfnd_XYZ123').
            payment_id: Optional associated gateway payment ID.

        Returns:
            GatewayRefundResponse.
        """
        pass

    @abstractmethod
    def verify_webhook_signature(
        self,
        raw_body: bytes,
        signature: str,
        webhook_secret: str,
    ) -> bool:
        """Verify HMAC-SHA256 webhook signature over original raw payload bytes.

        Args:
            raw_body: Byte sequence of the HTTP request body.
            signature: Signature header value from gateway.
            webhook_secret: Gateway webhook signing secret.

        Returns:
            True if HMAC-SHA256 matches; False otherwise.
        """
        pass
