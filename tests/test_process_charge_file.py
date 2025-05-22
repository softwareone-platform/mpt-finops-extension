import asyncio
import logging
import os
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

import aiofiles
import httpx
import pytest

from ffc.client import (
    HttpxFFCAPIClient,
)
from ffc.process_charge_file import ChargeFileSplitProcessor


@pytest.fixture
def mock_httpx_ffc_client(monkeypatch):
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    monkeypatch.setattr(
        "ffc.client.httpx.AsyncClient", lambda *args, **kwargs: mock_client
    )
    return mock_client


@pytest.fixture
def mock_proc_ffc_client(monkeypatch):
    mock_client = AsyncMock()
    mock_client.get_charges_file_download_url = AsyncMock()
    mock_client.get_generated_charge_files = AsyncMock()

    monkeypatch.setattr(
        "ffc.process_charge_file.get_httpx_ffc_api_client",
        lambda *args, **kwargs: mock_client,
    )
    return mock_client


@pytest.fixture
def mock_proc_mtp_client(monkeypatch):
    mock_client = AsyncMock()
    mock_client.fetch_subscription_and_agreement_details = AsyncMock()

    monkeypatch.setattr(
        "ffc.process_charge_file.get_httpx_mtp_api_client",
        lambda *args, **kwargs: mock_client,
    )
    return mock_client


@pytest.fixture
def charge_files():
    return {
        "items": [
            {
                "amount": 100.4,
                "currency": "USD",
                "document_date": "2017-05-19T00:00:00",
                "events": {
                    "created": {"at": "2025-04-28T10:32:16.100842Z"},
                    "updated": {"at": "2025-04-28T10:32:16.100848Z"},
                },
                "id": "FCHG-5825-2145-4566",
                "owner": {"id": "FACC-4174-5917", "name": "Test", "type": "operations"},
                "status": "generated",
            }
        ],
        "limit": 50,
        "offset": 0,
        "total": 1,
    }

@pytest.fixture
def xlsx_headers():
    return ["ID", "Subscription Search Criteria", "Subscription Search Value",
                   "Item Search Criteria","Item Search Value","Usage Start Time",
                   "Usage End Time","Time", "Quantity", "Purchase Price", "Total Purchase Price",
                   "External Reference","Vendor Description 1", "Vendor Description 2",
                   "Vendor Reference"]

@pytest.fixture
def xlsx_row():
    return (1, "subscription.externalIds.vendor", "FORG-4801-6958-2949", "item.externalIds.vendor",
      "FIN-0001-P1M", "29-Apr-2025", 0.00, "3d0fe384-b1cf", "AWS SSO",
      "6b1d3f21")

@pytest.fixture
def xlsx_row_no_forg():
    return (1, "subscription.externalIds.vendor", "", "item.externalIds.vendor",
      "FIN-0001-P1M", "29-Apr-2025", 0.00, "3d0fe384-b1cf", "AWS SSO",
      "6b1d3f21")

@pytest.fixture
def agreement_details():
    return [
            {
              "id": "SUB-0017-7335-0548",
              "status": "Active",
              "commitmentDate": "2025-05-17T13:53:23.556Z",
              "price": {
                "PPxY": 0.00000,
                "PPxM": 0.00000,
                "currency": "USD"
              },
              "agreement": {
                "id": "AGR-4480-3352-1794",
                "status": "Active",
                "listing": {
                  "id": "LST-9168-7963"
                },
                "authorization": {
                  "id": "AUT-3727-1184",
                  "name": "SoftwareOne FinOps for Cloud (USD)",
                  "currency": "USD"
                },
              }
            }
        ]


@pytest.mark.asyncio()
async def test_get_generated_charge_files_success(mock_httpx_ffc_client, charge_files):
    mock_response = MagicMock()
    mock_response.json.return_value = charge_files
    mock_response.raise_for_status.return_value = None
    mock_httpx_ffc_client.get.return_value = mock_response
    client = HttpxFFCAPIClient("https://fake.api", "sub", "secret")
    response = await client.get_generated_charge_files()
    assert response is not None
    assert isinstance(response, list)
    mock_httpx_ffc_client.get.assert_called_once()


@pytest.mark.asyncio
async def test_get_generated_charge_files_failure(mock_httpx_ffc_client):
    mock_httpx_ffc_client.get.side_effect = httpx.HTTPStatusError(
        "error",
        request=httpx.Request("GET", "https://fake.api"),
        response=httpx.Response(
            status_code=500, request=httpx.Request("GET", "https://fake.api")
        ),
    )

    client = HttpxFFCAPIClient("https://fake.api", "sub", "secret")
    result = await client.get_generated_charge_files()

    assert result is None
    mock_httpx_ffc_client.get.assert_called_once()


@pytest.mark.asyncio()
async def test_download_charge_file_success(mock_httpx_ffc_client, charge_files):
    chunks = [b"chunk1", b"chunk2", b"chunk3"]

    async def chunk_generator():
        for chunk in chunks:
            await asyncio.sleep(0)
            yield chunk

    initial_response = AsyncMock()
    initial_response.status_code = 307
    initial_response.headers = {"Location": "https://redirect.url"}
    mock_httpx_ffc_client.get.return_value = initial_response

    final_response = AsyncMock()
    final_response.status_code = 200
    final_response.aread = AsyncMock(return_value=b"just a test")
    final_response.aiter_bytes = MagicMock(return_value=chunk_generator())
    mock_httpx_ffc_client.get = AsyncMock(
        side_effect=[initial_response, final_response]
    )
    client = HttpxFFCAPIClient("https://fake.api", "sub", "secret")

    with patch("aiofiles.open") as mock_open:
        mock_file = AsyncMock()
        mock_open.return_value.__aenter__.return_value = mock_file
        mock_file.__aexit__.return_value = None

        result = await client.download_charges_file(
            charge_files["items"][0]["id"], tempfile.gettempdir()
        )
        assert result.endswith("FCHG-5825-2145-4566.zip")


@pytest.mark.asyncio()
async def test_download_redirect_location_header_missing(
    mock_httpx_ffc_client, charge_files
):
    initial_response = AsyncMock()
    initial_response.status_code = 307
    initial_response.headers = {}
    mock_httpx_ffc_client.get.return_value = initial_response
    client = HttpxFFCAPIClient("https://fake.api", "sub", "secret")
    result = await client.download_charges_file(
        charge_files["items"][0]["id"], tempfile.gettempdir()
    )
    assert result is None


@pytest.mark.asyncio()
async def test_download_not_307_status_code(mock_httpx_ffc_client, charge_files):
    initial_response = AsyncMock()
    initial_response.status_code = 400
    initial_response.headers = {}
    mock_httpx_ffc_client.get.return_value = initial_response
    client = HttpxFFCAPIClient("https://fake.api", "sub", "secret")
    result = await client.download_charges_file(
        charge_files["items"][0]["id"], tempfile.gettempdir()
    )
    assert result is None


@pytest.mark.asyncio()
async def test_download_location_url_fail(mock_httpx_ffc_client, charge_files):
    initial_response = AsyncMock()
    initial_response.status_code = 307
    initial_response.headers = {"Location": "http://redirect.url"}

    final_response = AsyncMock()
    final_response.status_code = 500

    mock_httpx_ffc_client.get = AsyncMock(
        side_effect=[initial_response, final_response]
    )
    client = HttpxFFCAPIClient("https://fake.api", "sub", "secret")
    result = await client.download_charges_file(
        charge_files["items"][0]["id"], tempfile.gettempdir()
    )
    assert result is None


@pytest.mark.asyncio()
async def test_read_the_response_in_chunks_and_write_to_file(charge_files):
    chunks = [b"chunk1", b"chunk2", b"chunk3"]
    temp_file = os.path.join(tempfile.gettempdir(), "test_downloaded_file.zip")

    async def chunk_generator():
        for chunk in chunks:
            await asyncio.sleep(0)  # forces async context
            yield chunk

    response = AsyncMock()
    response.aiter_bytes = MagicMock(return_value=chunk_generator())
    client = HttpxFFCAPIClient("https://fake.api", "sub", "secret")
    with patch("aiofiles.open", aiofiles.open):
        result_path = await client._stream_response_to_file(response, temp_file)
        assert result_path == temp_file
        with open(temp_file, "rb") as f:
            content = f.read()
        assert content == b"".join(chunks)
        os.remove(temp_file)


@pytest.mark.asyncio()
async def test_process_generated_charge_files_success(
    mock_proc_ffc_client, charge_files
):
    mock_proc_ffc_client.download_charges_file.return_value = (
        "/tmp/FCHG-1035-3738-7350.zip"
    )
    mock_proc_ffc_client.get_generated_charge_files.return_value = charge_files["items"]

    proc = ChargeFileSplitProcessor()
    await proc.process_generated_charge_files()
    mock_proc_ffc_client.get_generated_charge_files.assert_called_once()


@pytest.mark.asyncio()
async def test_process_generated_charge_files_exception_with_logging(
    mock_proc_ffc_client, charge_files, caplog
):
    def force_error():
        raise RuntimeError("An error occurred")

    mock_proc_ffc_client.get_generated_charge_files = AsyncMock(side_effect=force_error)

    proc = ChargeFileSplitProcessor()
    with caplog.at_level(logging.ERROR):
        response = await proc.process_generated_charge_files()
        assert response is None
        assert any(
            "An Error occurred processing the charge files" in msg
            for msg in caplog.messages
        )
@pytest.mark.asyncio
async def test_process_charge_file_logs_error_on_none(mock_proc_ffc_client, caplog):
    charge_file_id = "CHARGE123"
    download_folder = "/tmp/downloads"

    proc = ChargeFileSplitProcessor()
    proc.semaphore = AsyncMock()
    proc.semaphore.__aenter__.return_value = None
    proc.semaphore.__aexit__.return_value = None

    mock_proc_ffc_client.finops_client.download_charges_file.return_value = None

    with caplog.at_level(logging.ERROR):
        response = await proc.process_charge_file(charge_file_id, download_folder)
        assert response is None
    assert any(
        f"No file was downloaded for the charge file: {charge_file_id}" in message
        for message in caplog.messages
    )


@pytest.mark.asyncio()
async def test_process_excel_file_and_get_agreement_details(xlsx_headers,
                                                            xlsx_row,
                                                            mock_proc_mtp_client,
                                                            agreement_details):
    response = AsyncMock()
    response.status_code = 200
    response.reason = agreement_details
    mock_proc_mtp_client.fetch_subscription_and_agreement_details.return_value = response
    proc = ChargeFileSplitProcessor()
    ret = await proc.process_excel_content_and_get_agreement_details(headers=xlsx_headers,
                                                                     rows=[xlsx_row])
    assert ret is None


@pytest.mark.asyncio()
async def test_process_excel_file_and_get_agreement_details_no_forg_id(xlsx_headers,
                                                            xlsx_row_no_forg,
                                                            mock_proc_mtp_client,
                                                            agreement_details,
                                                                         caplog):
    proc = ChargeFileSplitProcessor()
    with caplog.at_level(logging.INFO):
        await proc.process_excel_content_and_get_agreement_details(headers=xlsx_headers,
                                                                     rows=[xlsx_row_no_forg])

    assert "No agreement auth id was found for row:" in caplog.messages[0]

@pytest.mark.asyncio()
@patch("ffc.client.HttpxMTPAPIClient.fetch_subscription_and_agreement_details",new_callable=AsyncMock)
async def test_process_excel_file_no_get_agreement_details(mock_proc_mtp_client,
                                                           xlsx_headers,
                                                            xlsx_row,
                                                            caplog,
                                                           ):
    mock_proc_mtp_client.return_value = None
    proc = ChargeFileSplitProcessor()
    with caplog.at_level(logging.ERROR):

        await proc.process_excel_content_and_get_agreement_details(headers=xlsx_headers,
                                                                     rows=[xlsx_row])
    assert "No agreement details found for" in caplog.messages[0]

@pytest.mark.asyncio
async def test_split_and_save_charge_file(xlsx_headers,xlsx_row):
    proc = ChargeFileSplitProcessor()
    proc.authorization_id_mapping = {"AUTH-123-456-987": [xlsx_row]}

    response = await proc.split_and_save_charge_file(headers=xlsx_headers)
    assert "AUTH-123-456-987.xlsx" in response[0]
