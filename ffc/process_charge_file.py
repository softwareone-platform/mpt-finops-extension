import asyncio
import logging
import tempfile
from typing import Any

from django.conf import settings

from ffc.client import get_httpx_ffc_api_client

logger = logging.getLogger(__name__)


class ChargeFileSplitProcessor:
    def __init__(
        self,
    ):
        self.finops_client = get_httpx_ffc_api_client()
        self.semaphore = asyncio.Semaphore(
            int(
                settings.EXTENSION_CONFIG.get(
                    "FFC_BILLING_PROCESS_MAX_CONCURRENCY", "10"
                )
            )
        )

    async def process_charge_file(self, charge_file_id: str, download_folder: str):
        async with self.semaphore:
            # first download the zip file related to the given charge_file_id
            zip_file_path = await self.finops_client.get_charges_file_download_url(
                charge_file_id=charge_file_id, download_folder=download_folder
            )
            if zip_file_path is None:
                logger.error(
                    f"No file was downloaded for the charge file: {charge_file_id} ."
                )

    async def process_generated_charge_files(self) -> list[Any] | None:
        """
        This method downloads all the charge files in the GENERATED status
        and for each of them it will download the related zip file from Azure Blob Storage
        The charge file in the GENERATED status is a list like the following example
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
            download_folder = tempfile.gettempdir()
            charge_file_list = await self.finops_client.get_generated_charge_files()
            tasks = [
                self.process_charge_file(
                    charge_file_id=charge_file["id"], download_folder=download_folder
                )
                for charge_file in charge_file_list
            ]
            await asyncio.gather(*tasks)
        except Exception as error:
            logger.exception(f"An Error occurred processing the charge files: {error}")
            return None


def start_processing_charge_file():  # pragma: no cover
    processor = ChargeFileSplitProcessor()
    asyncio.run(processor.process_generated_charge_files())
