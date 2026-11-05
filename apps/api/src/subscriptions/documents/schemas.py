"""Phase 21E.4D — Billing Document Schemas and DTOs."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class PlatformDocumentResponse(BaseModel):
    """Metadata response for a generated billing document."""

    id: UUID
    society_id: UUID
    document_type: str
    document_id: UUID
    document_number: str
    file_size_bytes: int
    content_type: str
    sha256_checksum: str
    generated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PlatformDocumentDownloadUrlResponse(BaseModel):
    """Response containing secure, short-lived presigned download URL."""

    document_id: UUID
    document_number: str
    download_url: str
    expires_in_seconds: int
    sha256_checksum: str


class PlatformDocumentEmailRequest(BaseModel):
    """Request to dispatch or resend document via email."""

    recipient_email: str | None = Field(default=None, description="Optional override; defaults to society billing admin")
    idempotency_key: str | None = Field(default=None, description="Client idempotency key")


class PlatformDeliveryAttemptResponse(BaseModel):
    """Detailed provider attempt log."""

    id: UUID
    attempt_number: int
    status: str
    provider_name: str
    provider_response_code: str | None
    provider_request_id: str | None
    error_message: str | None
    latency_ms: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PlatformDocumentDeliveryResponse(BaseModel):
    """Delivery status response."""

    id: UUID
    society_id: UUID
    document_id: UUID
    channel: str
    recipient_email: str
    status: str
    attempt_count: int
    max_attempts: int
    next_retry_at: datetime | None
    sent_at: datetime | None
    error_message: str | None
    idempotency_key: str
    attempts: list[PlatformDeliveryAttemptResponse] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)
