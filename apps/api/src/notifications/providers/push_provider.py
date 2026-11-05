"""Push Provider Adapter Foundation (Provider Neutral)."""

import time
import uuid

from apps.api.src.notifications.providers.base import (
    CommunicationProvider,
    ProviderMessage,
    ProviderResponse,
)


class MockPushProvider(CommunicationProvider):
    """Provider-neutral Mobile Push Channel Foundation Adapter."""

    @property
    def provider_name(self) -> str:
        return "MockPushProvider"

    @property
    def channel(self) -> str:
        return "PUSH"

    async def send(self, message: ProviderMessage) -> ProviderResponse:
        start_time = time.time()
        request_id = f"push-{uuid.uuid4().hex[:12]}"
        latency = int((time.time() - start_time) * 1000)

        return ProviderResponse(
            success=True,
            provider_name=self.provider_name,
            provider_request_id=request_id,
            response_code="200",
            latency_ms=latency,
        )
