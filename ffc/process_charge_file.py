import asyncio
import logging
import os
import tempfile
from typing import Any

import aiofiles
import httpx

from ffc.client import get_httpx_ffc_api_client

logger = logging.getLogger(__name__)

SEARCH_COLUMN_NAME = "Subscription Search Value"


async def read_the_response_in_chunks_and_write_to_file(
    response: httpx.Response, file_path, chunk_size=1024
):
    """
    This function reads the response in chunks and writes it to a file asynchronously.
    """
    async with aiofiles.open(file_path, "wb") as file:
        async for chunk in response.aiter_bytes(chunk_size=chunk_size):
            await file.write(chunk)
    logger.info(f"Charge File Downloaded and saved: {file_path}")
    return file_path


class ChargeFileSplitProcessor:
    def __init__(self, mtp_base_api_url: str):
        self.finops_client = get_httpx_ffc_api_client()
        self.MPT_API_BASE_URL = mtp_base_api_url

    async def fetch_generated_charge_files(self) -> list:
        """
        This method fetches all the charge files in GENERATED status
        """
        return await self.finops_client.get_generated_charge_files()

    async def download_zip_charge_file_from_azure_and_store(
        self, client: httpx.AsyncClient, charge_file: dict[str, Any], tmp_dir: str
    ) -> str | None:
        """
        This method downloads asynchronously downloads a charge file from the FFC_OPERATIONS API
        and stores it as a zip file in a temporary directory.
        Args:
            client (httpx.AsyncClient): The HTTP client used to make asynchronous requests.
            charge_file (dict[str, Any]): A dictionary containing the charge file.
            tmp_dir: The temporary directory to store the downloaded zip file.
        """
        charge_file_id = charge_file["id"]
        initial_url = f"{self.finops_client.api_base_url}/ops/v1/charges/{charge_file_id}/download"
        headers = self.finops_client.get_ffc_operations_authorization_headers()
        try:
            response = await client.get(initial_url, headers=headers)
            if response.status_code != 307:
                logger.error(
                    f"Unexpected status code {response.status_code} for {charge_file_id}"
                )
                return None
            redirect_url = response.headers[
                "Location"
            ]  # extract the download url location from the headers
            url_response = await client.get(
                redirect_url
            )  # the URL has a short-lived sas token
            if url_response.status_code != 200:
                logger.error(
                    f"Failed to download  {charge_file_id}, status: {url_response.status_code}"
                )
                return None
            file_path = os.path.join(tmp_dir, f"{charge_file_id}.zip")
            return await read_the_response_in_chunks_and_write_to_file(
                url_response, file_path
            )
        except Exception as error:
            logger.exception(f"Error downloading {charge_file_id}: {error}")
            return None

    async def process_generated_charge_files(
        self, charge_file_list: list[dict[str, Any]]
    ) -> list[Any] | None:
        """
        This method processes all the charge files in the GENERATED status
        and for each of them it will download the related zip file from Azure Blob Storage

        Args:
            charge_file_list: a list of dicts containing the charge file, like the following example
            {
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
        Returns : A list of the paths where the charge files are stored, like
        ['/var/folders/07/7_4bnbgx3xg8845xyq266g1w0000gn/T/FCHG-1035-3738-7350.zip']
        """
        try:
            temp_dir = (
                tempfile.gettempdir()
            )  # the tmp location where the file will be stored

            async with httpx.AsyncClient() as client:
                tasks = [
                    self.download_zip_charge_file_from_azure_and_store(
                        client=client, tmp_dir=temp_dir, charge_file=charge_file
                    )
                    for charge_file in charge_file_list
                ]
                results = await asyncio.gather(*tasks)
            zip_file_paths_list = [file_path for file_path in results if file_path]
            return zip_file_paths_list
        except Exception as error:
            logger.exception(f"An Error occurred processing the charge files: {error}")
            return None
