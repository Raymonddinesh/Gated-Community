"""Phase 21E.4D — Billing Document Generation, Secure Storage & Email Delivery Package."""

from apps.api.src.subscriptions.documents.document_orchestrator import (
    PlatformBillingDocumentService,
)
from apps.api.src.subscriptions.documents.email_service import (
    BillingEmailDeliveryService,
    BillingEmailProvider,
    EmailAttachment,
    EmailDeliveryResult,
    EmailPayload,
    MockBillingEmailProvider,
)
from apps.api.src.subscriptions.documents.exceptions import (
    BillingDocumentException,
    DocumentAlreadyGeneratedException,
    DocumentDeliveryException,
    DocumentNotFoundException,
    DocumentPermissionDeniedException,
    DocumentStorageException,
    DocumentTamperException,
    DraftDocumentAccessDeniedException,
)
from apps.api.src.subscriptions.documents.issuer import (
    BillingIssuerConfig,
    get_issuer_config,
)
from apps.api.src.subscriptions.documents.pdf_service import BillingPDFService
from apps.api.src.subscriptions.documents.schemas import (
    PlatformDeliveryAttemptResponse,
    PlatformDocumentDeliveryResponse,
    PlatformDocumentDownloadUrlResponse,
    PlatformDocumentEmailRequest,
    PlatformDocumentResponse,
)
from apps.api.src.subscriptions.documents.storage_service import (
    BillingDocumentStorageService,
)

__all__ = [
    "BillingDocumentException",
    "BillingDocumentStorageService",
    "BillingEmailDeliveryService",
    "BillingEmailProvider",
    "BillingIssuerConfig",
    "BillingPDFService",
    "DocumentAlreadyGeneratedException",
    "DocumentDeliveryException",
    "DocumentNotFoundException",
    "DocumentPermissionDeniedException",
    "DocumentStorageException",
    "DocumentTamperException",
    "DraftDocumentAccessDeniedException",
    "EmailAttachment",
    "EmailDeliveryResult",
    "EmailPayload",
    "MockBillingEmailProvider",
    "PlatformBillingDocumentService",
    "PlatformDeliveryAttemptResponse",
    "PlatformDocumentDeliveryResponse",
    "PlatformDocumentDownloadUrlResponse",
    "PlatformDocumentEmailRequest",
    "PlatformDocumentResponse",
    "get_issuer_config",
]
