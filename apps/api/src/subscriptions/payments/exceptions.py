"""Phase 21E.3 — Payment Gateway and Webhook Processing Domain Exceptions."""

from typing import Any
from uuid import UUID

from fastapi import status

from apps.api.src.subscriptions.exceptions import SubscriptionDomainException


class PaymentDomainException(SubscriptionDomainException):
    """Base exception for all SaaS billing payment gateway domain errors."""

    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = status.HTTP_400_BAD_REQUEST,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(code=code, message=message, status_code=status_code, details=details)


class GatewayConfigurationNotFoundException(PaymentDomainException):
    """Raised when payment gateway credentials are not configured for a provider."""

    def __init__(self, provider: str, details: dict[str, Any] | None = None) -> None:
        msg = f"Payment gateway configuration for provider '{provider}' was not found or is inactive."
        merged = details or {}
        merged["provider"] = provider
        super().__init__(
            code="GATEWAY_CONFIG_NOT_FOUND",
            message=msg,
            status_code=status.HTTP_404_NOT_FOUND,
            details=merged,
        )


class PaymentGatewayException(PaymentDomainException):
    """Raised when an external payment gateway returns an error or fails to respond."""

    def __init__(
        self,
        provider: str,
        message: str,
        gateway_code: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        merged = details or {}
        merged["provider"] = provider
        if gateway_code:
            merged["gateway_code"] = gateway_code
        super().__init__(
            code="GATEWAY_COMMUNICATION_ERROR",
            message=f"Gateway provider '{provider}' error: {message}",
            status_code=status.HTTP_502_BAD_GATEWAY,
            details=merged,
        )


class InvalidPaymentSignatureException(PaymentDomainException):
    """Raised when a client-submitted payment checkout signature does not match."""

    def __init__(
        self,
        order_id: str,
        payment_id: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        merged = details or {}
        merged["order_id"] = order_id
        merged["payment_id"] = payment_id
        super().__init__(
            code="INVALID_PAYMENT_SIGNATURE",
            message="Payment signature verification failed. Untrusted payment payload rejected.",
            status_code=status.HTTP_400_BAD_REQUEST,
            details=merged,
        )


class WebhookSignatureVerificationException(PaymentDomainException):
    """Raised when a gateway webhook HMAC-SHA256 signature fails validation."""

    def __init__(
        self,
        provider: str,
        event_id: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        merged = details or {}
        merged["provider"] = provider
        if event_id:
            merged["event_id"] = event_id
        super().__init__(
            code="INVALID_WEBHOOK_SIGNATURE",
            message=f"Webhook HMAC signature verification failed for provider '{provider}'.",
            status_code=status.HTTP_401_UNAUTHORIZED,
            details=merged,
        )


class DuplicateWebhookException(PaymentDomainException):
    """Raised when a webhook event has already been received or processed."""

    def __init__(
        self,
        provider: str,
        event_id: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        merged = details or {}
        merged["provider"] = provider
        merged["event_id"] = event_id
        super().__init__(
            code="DUPLICATE_WEBHOOK_EVENT",
            message=f"Webhook event '{event_id}' for '{provider}' has already been received.",
            status_code=status.HTTP_409_CONFLICT,
            details=merged,
        )


class LockAcquisitionException(PaymentDomainException):
    """Raised when a 64-bit advisory lock cannot be acquired due to concurrent worker execution."""

    def __init__(
        self,
        lock_key: int,
        resource_id: str,
        retry_after: int = 5,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.retry_after = retry_after
        merged = details or {}
        merged["lock_key"] = lock_key
        merged["resource_id"] = resource_id
        merged["retry_after"] = retry_after
        super().__init__(
            code="LOCK_ACQUISITION_FAILED",
            message=f"Concurrent worker lock active for resource '{resource_id}'. Safe retry scheduled.",
            status_code=status.HTTP_409_CONFLICT,
            details=merged,
        )


class PaymentOrderCreationException(PaymentDomainException):
    """Raised when an order creation request fails pre-flight validation."""

    def __init__(
        self,
        invoice_id: UUID,
        reason: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        merged = details or {}
        merged["invoice_id"] = str(invoice_id)
        merged["reason"] = reason
        super().__init__(
            code="PAYMENT_ORDER_CREATION_FAILED",
            message=f"Failed to create payment order for invoice '{invoice_id}': {reason}",
            status_code=status.HTTP_400_BAD_REQUEST,
            details=merged,
        )


class InvoiceNotFoundException(PaymentDomainException):
    """Raised when a target platform invoice cannot be found."""

    def __init__(self, invoice_id: UUID, details: dict[str, Any] | None = None) -> None:
        merged = details or {}
        merged["invoice_id"] = str(invoice_id)
        super().__init__(
            code="INVOICE_NOT_FOUND",
            message=f"Platform invoice '{invoice_id}' was not found.",
            status_code=status.HTTP_404_NOT_FOUND,
            details=merged,
        )


class InvoiceAlreadyPaidException(PaymentDomainException):
    """Raised when attempting to create a payment order or settle an already paid invoice."""

    def __init__(self, invoice_id: UUID, details: dict[str, Any] | None = None) -> None:
        merged = details or {}
        merged["invoice_id"] = str(invoice_id)
        super().__init__(
            code="INVOICE_ALREADY_PAID",
            message=f"Platform invoice '{invoice_id}' is already fully paid.",
            status_code=status.HTTP_409_CONFLICT,
            details=merged,
        )


class InvalidInvoiceStateException(PaymentDomainException):
    """Raised when an invoice is in a non-payable state (e.g., VOID, UNCOLLECTIBLE)."""

    def __init__(
        self,
        invoice_id: UUID,
        current_status: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        merged = details or {}
        merged["invoice_id"] = str(invoice_id)
        merged["current_status"] = current_status
        super().__init__(
            code="INVALID_INVOICE_STATE",
            message=f"Platform invoice '{invoice_id}' is in state '{current_status}' and cannot receive payments.",
            status_code=status.HTTP_400_BAD_REQUEST,
            details=merged,
        )


class PaymentAlreadySettledException(PaymentDomainException):
    """Raised when attempting to settle a payment that has already been captured and processed."""

    def __init__(
        self,
        payment_id: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        merged = details or {}
        merged["payment_id"] = payment_id
        super().__init__(
            code="PAYMENT_ALREADY_SETTLED",
            message=f"Payment transaction '{payment_id}' has already been settled.",
            status_code=status.HTTP_409_CONFLICT,
            details=merged,
        )


class PaymentNotFoundException(PaymentDomainException):
    """Raised when a platform payment record cannot be found."""

    def __init__(self, payment_id: UUID | str, details: dict[str, Any] | None = None) -> None:
        merged = details or {}
        merged["payment_id"] = str(payment_id)
        super().__init__(
            code="PAYMENT_NOT_FOUND",
            message=f"Platform payment '{payment_id}' was not found.",
            status_code=status.HTTP_404_NOT_FOUND,
            details=merged,
        )


class PaymentAttemptNotFoundException(PaymentDomainException):
    """Raised when a payment attempt cannot be found for order verification."""

    def __init__(self, order_id: str, details: dict[str, Any] | None = None) -> None:
        merged = details or {}
        merged["gateway_order_id"] = order_id
        super().__init__(
            code="PAYMENT_ATTEMPT_NOT_FOUND",
            message=f"Payment attempt for gateway order '{order_id}' was not found.",
            status_code=status.HTTP_404_NOT_FOUND,
            details=merged,
        )


class InvalidRefundAmountException(PaymentDomainException):
    """Raised when requested refund exceeds available captured payment amount."""

    def __init__(
        self,
        payment_id: UUID,
        requested_amount: str,
        available_amount: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        merged = details or {}
        merged["payment_id"] = str(payment_id)
        merged["requested_amount"] = requested_amount
        merged["available_amount"] = available_amount
        super().__init__(
            code="INVALID_REFUND_AMOUNT",
            message=(
                f"Requested refund amount ({requested_amount}) exceeds remaining refundable "
                f"balance ({available_amount}) on payment '{payment_id}'."
            ),
            status_code=status.HTTP_400_BAD_REQUEST,
            details=merged,
        )


class RefundFailedException(PaymentDomainException):
    """Raised when the gateway rejects a refund initiation request."""

    def __init__(
        self,
        payment_id: UUID,
        reason: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        merged = details or {}
        merged["payment_id"] = str(payment_id)
        merged["reason"] = reason
        super().__init__(
            code="REFUND_FAILED",
            message=f"Refund request for payment '{payment_id}' failed: {reason}",
            status_code=status.HTTP_502_BAD_GATEWAY,
            details=merged,
        )


class ReconciliationDiscrepancyException(PaymentDomainException):
    """Raised when financial reconciliation uncovers an unresolvable record mismatch."""

    def __init__(
        self,
        discrepancy_type: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        merged = details or {}
        merged["discrepancy_type"] = discrepancy_type
        super().__init__(
            code="RECONCILIATION_DISCREPANCY",
            message=f"Financial reconciliation discrepancy detected: {discrepancy_type}",
            status_code=status.HTTP_409_CONFLICT,
            details=merged,
        )
