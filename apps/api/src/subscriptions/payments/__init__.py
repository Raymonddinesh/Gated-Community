"""Phase 21E.3 — Commercial SaaS Payment Gateway and Webhook Processing Package."""

from apps.api.src.subscriptions.payments.encryption import (
    decrypt_secret,
    encrypt_secret,
    mask_secret,
    redact_sensitive_dict,
)
from apps.api.src.subscriptions.payments.exceptions import (
    DuplicateWebhookException,
    GatewayConfigurationNotFoundException,
    InvalidInvoiceStateException,
    InvalidPaymentSignatureException,
    InvalidRefundAmountException,
    InvoiceAlreadyPaidException,
    InvoiceNotFoundException,
    LockAcquisitionException,
    PaymentAlreadySettledException,
    PaymentAttemptNotFoundException,
    PaymentDomainException,
    PaymentGatewayException,
    PaymentNotFoundException,
    PaymentOrderCreationException,
    ReconciliationDiscrepancyException,
    RefundFailedException,
    WebhookSignatureVerificationException,
)
from apps.api.src.subscriptions.payments.order_service import PaymentOrderService
from apps.api.src.subscriptions.payments.provider import PaymentGatewayProvider
from apps.api.src.subscriptions.payments.provider_factory import PaymentGatewayFactory
from apps.api.src.subscriptions.payments.razorpay_adapter import RazorpayGatewayProvider
from apps.api.src.subscriptions.payments.reconciliation_service import PaymentReconciliationService
from apps.api.src.subscriptions.payments.refund_service import RefundService
from apps.api.src.subscriptions.payments.schemas import (
    GatewayOrderResponse,
    GatewayPaymentDetails,
    GatewayRefundResponse,
    PaymentOrderCreateRequest,
    PaymentOrderResponse,
    PaymentVerificationRequest,
    PaymentVerificationResponse,
    ReconciliationDiscrepancy,
    ReconciliationReportResponse,
    RefundInitiationRequest,
    RefundResponse,
    WebhookIngestResponse,
)
from apps.api.src.subscriptions.payments.settlement_service import PaymentSettlementService
from apps.api.src.subscriptions.payments.verification_service import (
    PaymentVerificationService,
)
from apps.api.src.subscriptions.payments.webhook_ingestion_service import (
    WebhookIngestionService,
    compute_advisory_lock_key,
)
from apps.api.src.subscriptions.payments.webhook_worker import WebhookProcessingWorker

__all__ = [
    # Abstraction & Adapters
    "PaymentGatewayProvider",
    "RazorpayGatewayProvider",
    "PaymentGatewayFactory",
    # Domain Services
    "PaymentOrderService",
    "PaymentVerificationService",
    "WebhookIngestionService",
    "WebhookProcessingWorker",
    "PaymentSettlementService",
    "RefundService",
    "PaymentReconciliationService",
    # Cryptography & Redaction
    "encrypt_secret",
    "decrypt_secret",
    "mask_secret",
    "redact_sensitive_dict",
    "compute_advisory_lock_key",
    # Schemas
    "GatewayOrderResponse",
    "GatewayPaymentDetails",
    "GatewayRefundResponse",
    "PaymentOrderCreateRequest",
    "PaymentOrderResponse",
    "PaymentVerificationRequest",
    "PaymentVerificationResponse",
    "RefundInitiationRequest",
    "RefundResponse",
    "WebhookIngestResponse",
    "ReconciliationDiscrepancy",
    "ReconciliationReportResponse",
    # Exceptions
    "PaymentDomainException",
    "PaymentGatewayException",
    "GatewayConfigurationNotFoundException",
    "InvalidPaymentSignatureException",
    "WebhookSignatureVerificationException",
    "DuplicateWebhookException",
    "LockAcquisitionException",
    "PaymentOrderCreationException",
    "InvoiceNotFoundException",
    "InvoiceAlreadyPaidException",
    "InvalidInvoiceStateException",
    "PaymentAlreadySettledException",
    "PaymentNotFoundException",
    "PaymentAttemptNotFoundException",
    "InvalidRefundAmountException",
    "RefundFailedException",
    "ReconciliationDiscrepancyException",
]
