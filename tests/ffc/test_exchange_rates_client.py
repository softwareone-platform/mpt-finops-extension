import pytest

from ffc.clients.exchage_rates import ExchangeRatesAsyncClient


@pytest.fixture()
def exchange_rates_client_settings(settings):
    settings.EXTENSION_CONFIG = {
        "EXCHANGE_RATES_BASE_URL": "https://local.local",
        "EXCHANGE_RATES_API_TOKEN": "api-token"
    }
    return settings


@pytest.fixture()
def mocked_exchange_rates_client():
    return ExchangeRatesAsyncClient()


@pytest.mark.asyncio()
async def test_fetch_exchange_rates_cached(mocked_exchange_rates_client, exchange_rates):
    mocked_exchange_rates_client.exchage_rates_cache["USD"] = exchange_rates
    result = await mocked_exchange_rates_client.fetch_exchange_rates(currency="USD")
    assert result == exchange_rates


@pytest.mark.asyncio()
async def test_fetch_exchange_rates_no_cached(
    httpx_mock, mocked_exchange_rates_client, exchange_rates, exchange_rates_client_settings
):
    httpx_mock.add_response(
        method="GET", url="https://local.local/api-token/latest/USD", json=exchange_rates,
    )
    response = await mocked_exchange_rates_client.fetch_exchange_rates(currency="USD")
    assert response == exchange_rates
    assert mocked_exchange_rates_client.exchage_rates_cache["USD"] == exchange_rates
