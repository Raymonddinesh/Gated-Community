"""Phase 20 Provider-Neutral Communication Provider Abstraction."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID


@dataclass
class ProviderMessage:
    """Provider-agnostic message payload."""

    notification_id: UUID
    delivery_id: UUID
    recipient_user_id: UUID
    channel: str
    recipient_address: str  # email, phone number, device token, or user ID
    subject: str | None
    content: str
    payload: dict | None = field(default_factory=dict)


@dataclass
class ProviderResponse:
    """Provider response details."""

    success: bool
    provider_name: str
    provider_request_id: str | None = None
    response_code: str | None = None
    error_message: str | None = None
    is_retryable: bool = False
    sent_at: datetime = field(default_factory=datetime.now)
    latency_ms: int = 0


class CommunicationProvider(ABC):
    """Abstract Base Class for Communication Channel Adapters."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Name of the communication provider adapter."""
        pass

    @property
    @abstractmethod
    def channel(self) -> str:
        """Target communication channel (IN_APP, EMAIL, SMS, WHATSAPP, PUSH)."""
        pass

    @abstractmethod
    async def send(self, message: ProviderMessage) -> ProviderResponse:
        """Send message through the channel provider."""
        pass
