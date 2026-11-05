"""Email Provider Adapter Foundation (Provider Neutral)."""

import time
import uuid

from apps.api.src.notifications.providers.base import (
    CommunicationProvider,
    ProviderMessage,
    ProviderResponse,
)


class MockEmailProvider(CommunicationProvider):
    """Provider-neutral Email Channel Foundation Adapter."""

    @property
    def provider_name(self) -> str:
        return "MockEmailProvider"

    @property
    def channel(self) -> str:
        return "EMAIL"

    async def send(self, message: ProviderMessage) -> ProviderResponse:
        start_time = time.time()
        # Provider-neutral foundation - simulates successful email dispatch
        request_id = f"email-{uuid.uuid4().hex[:12]}"
        latency = int((time.time() - start_time) * 1000)

        return ProviderResponse(
            success=True,
            provider_name=self.provider_name,
            provider_request_id=request_id,
            response_code="202",
            latency_ms=latency,
        )
