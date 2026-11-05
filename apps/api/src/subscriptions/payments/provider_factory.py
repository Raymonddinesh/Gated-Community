"""Phase 21E.3 — Payment Gateway Provider Factory.

Loads gateway configuration from PlatformPaymentGatewayConfig, decrypts secrets,
and instantiates the appropriate PaymentGatewayProvider adapter.
"""

import os

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.database.models.platform_billing import PlatformPaymentGatewayConfig
from apps.api.src.subscriptions.payments.encryption import decrypt_secret
from apps.api.src.subscriptions.payments.exceptions import (
    GatewayConfigurationNotFoundException,
    PaymentGatewayException,
)
from apps.api.src.subscriptions.payments.provider import PaymentGatewayProvider
from apps.api.src.subscriptions.payments.razorpay_adapter import RazorpayGatewayProvider


class PaymentGatewayFactory:
    """Factory for resolving and instantiating configured payment gateway providers."""

    @staticmethod
    async def get_provider(
        session: AsyncSession,
        provider_name: str = "RAZORPAY",
        httpx_client: httpx.AsyncClient | None = None,
    ) -> PaymentGatewayProvider:
        """Resolve and instantiate a gateway provider using database configuration or env fallback.

        Args:
            session: AsyncSession connected to PostgreSQL.
            provider_name: Gateway provider identifier (e.g. 'RAZORPAY').
            httpx_client: Optional mock or shared HTTP client.

        Returns:
            Configured PaymentGatewayProvider.
        """
        norm_provider = provider_name.upper().strip()

        # 1. Query database for merchant configuration
        stmt = select(PlatformPaymentGatewayConfig).where(
            PlatformPaymentGatewayConfig.gateway_provider == norm_provider,
            PlatformPaymentGatewayConfig.is_active == True,  # noqa: E712
        )
        res = await session.execute(stmt)
        config = res.scalar_one_or_none()

        if config:
            key_secret = decrypt_secret(config.encrypted_secret)
            webhook_secret = (
                decrypt_secret(config.webhook_secret_primary)
                if config.webhook_secret_primary
                else None
            )
            webhook_secret_sec = (
                decrypt_secret(config.webhook_secret_secondary)
                if config.webhook_secret_secondary
                else None
            )

            if norm_provider == "RAZORPAY":
                return RazorpayGatewayProvider(
                    key_id=config.key_id,
                    key_secret=key_secret,
                    webhook_secret=webhook_secret,
                    webhook_secret_secondary=webhook_secret_sec,
                    httpx_client=httpx_client,
                )
            raise PaymentGatewayException(
                provider=norm_provider,
                message=f"Provider '{norm_provider}' is not yet supported.",
            )

        # 2. Fallback to environment variables for dev/test environments
        env_key_id = os.getenv(f"{norm_provider}_KEY_ID")
        env_key_secret = os.getenv(f"{norm_provider}_KEY_SECRET")
        env_webhook_secret = os.getenv(f"{norm_provider}_WEBHOOK_SECRET")

        if env_key_id and env_key_secret:
            if norm_provider == "RAZORPAY":
                return RazorpayGatewayProvider(
                    key_id=env_key_id,
                    key_secret=env_key_secret,
                    webhook_secret=env_webhook_secret,
                    httpx_client=httpx_client,
                )

        raise GatewayConfigurationNotFoundException(provider=norm_provider)
