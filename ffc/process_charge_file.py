import asyncio
import logging
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any

from django.conf import settings

from ffc.client import get_httpx_ffc_api_client, get_httpx_mtp_api_client
from ffc.utils import (
    AsyncExcelWriter,
    extract_zip_files,
    read_excel_headers_and_rows,
)

logger = logging.getLogger(__name__)
SUBSCRIPTION_SEARCH_VALUE_COLUMN_NAME = "Subscription Search Value"


class ChargeFileSplitProcessor:
    def __init__(
        self,
    ):
        self.finops_client = get_httpx_ffc_api_client()
        self.mtp_client = get_httpx_mtp_api_client()
        self.authorization_id_mapping = defaultdict(list)
        self.semaphore = asyncio.Semaphore(
            int(
                settings.EXTENSION_CONFIG.get(
                    "FFC_BILLING_PROCESS_MAX_CONCURRENCY", "10"
                )
            )
        )

    async def process_charge_file(self, charge_file_id: str, download_folder: str):
        """
        This method downloads the zipped file from FCC API and extracts the Excel charge file and
        the JSON files related to the currencies conversion rate used.
        It also extracts the Headers and Rows from the Excel charge file and invokes
        the method to fetch the agreement's details related to the charge file.


        Args:
            charge_file_id: The id of the charge file ( FCHG-1035-3738-7350)
            download_folder: The folder where the downloaded files will be saved

        """
        async with self.semaphore:
            # first download the zip file related to the given charge_file_id
            zip_file_path = await self.finops_client.download_charges_file(
                charge_file_id=charge_file_id, download_folder=download_folder
            )

            if zip_file_path is not None and Path(zip_file_path).is_file():
                folder = f"{download_folder}/{charge_file_id}"
                # extract the xlsx charge file and the JSON currency conversion files
                (
                    xlsx_file_path,
                    json_files_path,
                ) = await asyncio.get_event_loop().run_in_executor(
                    None, extract_zip_files, zip_file_path, folder
                )
                # save headers and rows of the xlsx file
                headers, rows = await asyncio.get_event_loop().run_in_executor(
                    None, read_excel_headers_and_rows, xlsx_file_path
                )
                # process each row and fetch its related agreement's details
                await self.process_excel_content_and_get_agreement_details(
                    headers=headers, rows=rows
                )
                # split the charge file
                await self.split_and_save_charge_file(headers=headers)

            else:
                logger.error(
                    f"No file was downloaded for the charge file: {charge_file_id} ."
                )

    async def process_excel_content_and_get_agreement_details(
        self, headers: list[str], rows: list[Any]
    ) -> list[str] | None:
        """
        This method processes the given Excel file to read the
        SUBSCRIPTION_SEARCH_VALUE_COLUMN_NAME's value (FORG-XXX-YYY-ZZZ) and fetches the related
        agreement details from the MTP APIs.

        Args:
            headers (list[str]): The headers of the charge Excel file.
            rows (list[Any]): The rows of the charge Excel file to process.


        Returns: A list of Agreement Details like
         [
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
                ...
            }
        ]

        """

        if SUBSCRIPTION_SEARCH_VALUE_COLUMN_NAME not in headers:  # pragma: no cover
            return None
        # this is the value (FORG-1317-5652-8045) we need to get the Agreement's details
        search_index = headers.index(SUBSCRIPTION_SEARCH_VALUE_COLUMN_NAME)

        for row in rows:
            forg_id = row[search_index]
            if forg_id:
                agreement_details = (
                    await self.mtp_client.fetch_subscription_and_agreement_details(
                        subscription_search_value=forg_id
                    )
                )

                try:
                    authorization_id = agreement_details[0]["agreement"][
                        "authorization"
                    ]["id"]
                    self.authorization_id_mapping[authorization_id].append(row)
                except (IndexError, KeyError, TypeError):
                    logger.error(f"No agreement details found for {forg_id}")
                    continue
            else:  # pragma no cover
                logger.info(f"No agreement auth id was found for row: {row}")

    async def split_and_save_charge_file(self, headers: list[str]):
        """
        This method creates a new Excel file for each AUTH ID stored as keys in the
        authorization_id_mapping dictionary and writes the content of the
        rows,  stored as values.

        The   looks like
        {'AUTH-123-456-987': [(
            1, 'subscription.externalIds.vendor',
            'FORG-4801-6958-2949',
            'item.externalIds.vendor', 'FIN-0001-P1M', '29-Apr-2025', 0.0,
            '3d0fe384-b1cf', 'AWS SSO', '6b1d3f21')]
        }
        Args:
            headers (list[str]): The headers of the split Excel file to write
        """
        split_files = []
        # the folder where the charge file split by AUTH will be stored.
        split_file_save_folder = Path(tempfile.gettempdir())
        async with AsyncExcelWriter() as writer:
            for authorization_id, rows in self.authorization_id_mapping.items():
                split_filename = f"{authorization_id}.xlsx"
                output_path = split_file_save_folder / split_filename
                if str(output_path) not in split_files:  # pragma no cover
                    split_files.append(str(output_path))
                await writer.add_rows(str(output_path), headers, rows)

        self.authorization_id_mapping = []
        return split_files

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
