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
    # assert result == ["/tmp/FCHG-1035-3738-7350.zip"]


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
