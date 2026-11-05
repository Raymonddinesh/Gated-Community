"""In-App Communication Provider Adapter."""

import time
import uuid

from apps.api.src.notifications.providers.base import (
    CommunicationProvider,
    ProviderMessage,
    ProviderResponse,
)


class InAppProvider(CommunicationProvider):
    """In-App Delivery Provider Adapter."""

    @property
    def provider_name(self) -> str:
        return "InAppProvider"

    @property
    def channel(self) -> str:
        return "IN_APP"

    async def send(self, message: ProviderMessage) -> ProviderResponse:
        start_time = time.time()
        # In-App notifications are delivered by inserting NotificationRecipient into DB inbox
        request_id = f"inapp-{uuid.uuid4().hex[:12]}"
        latency = int((time.time() - start_time) * 1000)

        return ProviderResponse(
            success=True,
            provider_name=self.provider_name,
            provider_request_id=request_id,
            response_code="200",
            latency_ms=latency,
        )
