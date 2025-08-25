from typing import Any

from django.conf import settings

from ffc.clients.base import BaseAsyncAPIClient


class ExchangeRatesAsyncClient(BaseAsyncAPIClient):
    def __init__(self):
        self.exchage_rates_cache = {}

    @property
    def base_url(self):
        return settings.EXTENSION_CONFIG["EXCHANGE_RATES_BASE_URL"]

    @property
    def auth(self):
        return None

    async def fetch_exchange_rates(self, currency) -> dict[str, Any]:
        if currency in self.exchage_rates_cache:
            return self.exchage_rates_cache[currency]
        response = await self.httpx_client.get(
            f"{settings.EXTENSION_CONFIG["EXCHANGE_RATES_BASE_URL"]}/latest/{currency}"
        )
        response.raise_for_status()
        exchange_rates = response.json()
        self.exchage_rates_cache[currency] = exchange_rates
        return exchange_rates
