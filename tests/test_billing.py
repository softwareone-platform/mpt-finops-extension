import logging
import os
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

import aiofiles
import pytest

from ffc.process_charge_file import (
    ChargeFileSplitProcessor,
    read_the_response_in_chunks_and_write_to_file,
)


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
async def test_download_charge_file_success(monkeypatch, charge_files):
    client = AsyncMock()
    initial_response = MagicMock()
    initial_response.status_code = 307
    initial_response.headers = {"Location": "https://redirect.url"}

    final_response = MagicMock()
    final_response.status_code = 200
    final_response.aread = AsyncMock(return_value=b"just a test")
    client.get = AsyncMock(side_effect=[initial_response, final_response])

    with patch("aiofiles.open") as mock_open:
        mock_file = AsyncMock()
        mock_open.return_value.__aenter__.return_value = mock_file
        mock_file.__aexit__.return_value = None

        proc = ChargeFileSplitProcessor(mtp_base_api_url="https://localhost.url")
        result = await proc.download_zip_charge_file_from_azure_and_store(
            client, charge_files["items"][0], tempfile.gettempdir()
        )
        assert result.endswith("FCHG-5825-2145-4566.zip")


@pytest.mark.asyncio()
async def test_download_redirect_location_header_missing(charge_files):
    client = AsyncMock()
    response = MagicMock()
    response.status_code = 307
    response.headers = {}

    client.get = AsyncMock(return_value=response)
    proc = ChargeFileSplitProcessor(mtp_base_api_url="https://localhost.url")
    result = await proc.download_zip_charge_file_from_azure_and_store(
        client, charge_files["items"][0], tempfile.gettempdir()
    )
    assert result is None


@pytest.mark.asyncio()
async def test_download_not_307_status_code(charge_files):
    client = AsyncMock()
    response = MagicMock()
    response.status_code = 400
    response.headers = {}

    client.get = AsyncMock(return_value=response)
    proc = ChargeFileSplitProcessor(mtp_base_api_url="https://localhost.url")
    result = await proc.download_zip_charge_file_from_azure_and_store(
        client, charge_files["items"][0], tempfile.gettempdir()
    )
    assert result is None


@pytest.mark.asyncio()
async def test_download_location_url_fail(charge_files):
    client = AsyncMock()
    response1 = MagicMock()
    response1.status_code = 307
    response1.headers = {"Location": "http://redirect.url"}

    response2 = MagicMock()
    response2.status_code = 500

    client.get = AsyncMock(side_effect=[response1, response2])
    proc = ChargeFileSplitProcessor(mtp_base_api_url="https://localhost.url")
    result = await proc.download_zip_charge_file_from_azure_and_store(
        client, charge_files["items"][0], tempfile.gettempdir()
    )
    assert result is None


@pytest.mark.asyncio()
async def test_read_the_response_in_chunks_and_write_to_file(charge_files):
    chunks = [b"chunk1", b"chunk2", b"chunk3"]
    temp_file = os.path.join(tempfile.gettempdir(), "test_downloaded_file.zip")

    response = AsyncMock()

    def chunk_generator():
        yield from chunks

    response.aiter_bytes = MagicMock(return_value=chunk_generator())

    with patch("aiofiles.open", aiofiles.open):
        result_path = await read_the_response_in_chunks_and_write_to_file(
            response, temp_file
        )
        assert result_path == temp_file
        with open(temp_file, "rb") as f:
            content = f.read()
        assert content == b"".join(chunks)
        os.remove(temp_file)


@pytest.mark.asyncio()
async def test_process_generated_charge_files_success(charge_files):
    proc = ChargeFileSplitProcessor(mtp_base_api_url="https://localhost.url")
    proc.download_zip_charge_file_from_azure_and_store = AsyncMock(
        side_effect=["/tmp/a.zip"]
    )

    result = await proc.process_generated_charge_files(
        charge_file_list=charge_files["items"]
    )
    assert result == ["/tmp/a.zip"]


@pytest.mark.asyncio()
async def test_process_generated_charge_files_exception_with_logging(
    charge_files, caplog
):
    proc = ChargeFileSplitProcessor(mtp_base_api_url="https://localhost.url")

    def force_error(*args, **kwargs):
        raise RuntimeError("An error occurred")

    proc.download_zip_charge_file_from_azure_and_store = AsyncMock(
        side_effect=force_error
    )

    with caplog.at_level(logging.ERROR):
        result = await proc.process_generated_charge_files(
            charge_file_list=charge_files["items"]
        )

        assert result is None
        assert any(
            "An Error occurred processing the charge files" in msg
            for msg in caplog.messages
        )
