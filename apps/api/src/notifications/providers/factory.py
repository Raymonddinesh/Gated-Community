"""Provider Factory & Registry for Communication Channels."""

from apps.api.src.notifications.providers.base import CommunicationProvider
from apps.api.src.notifications.providers.email_provider import MockEmailProvider
from apps.api.src.notifications.providers.in_app_provider import InAppProvider
from apps.api.src.notifications.providers.push_provider import MockPushProvider
from apps.api.src.notifications.providers.sms_provider import MockSmsProvider
from apps.api.src.notifications.providers.whatsapp_provider import MockWhatsAppProvider


class ProviderFactory:
    """Registry and Factory for Communication Providers."""

    def __init__(self):
        self._providers: dict[str, CommunicationProvider] = {
            "IN_APP": InAppProvider(),
            "EMAIL": MockEmailProvider(),
            "SMS": MockSmsProvider(),
            "WHATSAPP": MockWhatsAppProvider(),
            "PUSH": MockPushProvider(),
        }

    def register_provider(self, channel: str, provider: CommunicationProvider) -> None:
        self._providers[channel.upper()] = provider

    def get_provider(self, channel: str) -> CommunicationProvider | None:
        return self._providers.get(channel.upper())


# Global singleton factory instance
provider_factory = ProviderFactory()
