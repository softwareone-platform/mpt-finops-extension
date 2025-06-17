import asyncio
import logging
import tempfile
from dataclasses import dataclass
from typing import Any

import aiofiles
from django.conf import settings

from ffc.client import (
    get_httpx_exchange_rate_client,
    get_httpx_ffc_api_client,
    get_httpx_mtp_api_client,
)
from ffc.generate_charges import generate_charges_file

logger = logging.getLogger(__name__)


@dataclass
class BillingProcess:
    product_id: str
    month: int
    year: int
    day: int | None = None
    authorization_id: str | None = None
    finops_client = get_httpx_ffc_api_client()
    mtp_client = get_httpx_mtp_api_client()
    exchange_rate_client = get_httpx_exchange_rate_client()
    semaphore = asyncio.Semaphore(
        int(settings.EXTENSION_CONFIG.get("FFC_BILLING_PROCESS_MAX_CONCURRENCY", "10"))
    )

    async def get_or_create_journal_file(self, authorization_id: str, month: int, year: int):
        """
        This method checks an existing journal file for the given authorization's ID.
        If it doesn't exist, it creates a new journal file for the given authorization's ID
        and returns it.
        Otherwise, it returns the journal file already created.

        Args:
            authorization_id: The authorization ID
            month: The month
            year: The year

        Returns: a Journal Obj like in
            https://softwareone.atlassian.net/wiki/spaces/mpt/pages/5959090509/Billing+Attachment+Object#Example
            or None if an error occurred.
        """
        external_vendor_id = f"{year:04d}{month:02d}"
        journal = await self.mtp_client.get_journal_file(
            authorization_id=authorization_id,
            external_vendor_id=external_vendor_id,
        )
        if journal is None:
            logger.error(
                f"The Journal file for the authorization {authorization_id} was not fetched"
            )
            return None
        if len(journal) == 0:
            # Journal does not exist, attempt to create it
            journal = await self.mtp_client.create_journal(
                authorization_id=authorization_id,
                month=month,
                year=year,
            )
            if journal is None:
                logger.error(
                    f"The Journal file for the authorization {authorization_id} was not created"
                )
                return None
        return journal

    async def check_attachment_duplicate_and_delete(self, journal_id: str, filename: str):
        response = await self.mtp_client.fetch_journal_attachments(
            journal_id=journal_id, filename=filename
        )
        if response is None:
            logger.error(
                f"Unexpected response from fetching journal attachments for journal id {journal_id}"
            )
            return None
        if len(response) > 0:
            attachment_id = response[0].get("id")
            # an attachment for the given journal id already exists
            # delete it so as it can be replaced.
            await self.mtp_client.delete_journal_attachment(
                journal_id=journal_id,
                attachment_id=attachment_id,
            )
        return True

    async def rate_conversion(self, exchanges_rates: dict):
        pass  # pragma: no cover

    async def check_if_rate_conversion_is_required(
        self, organization: dict[str, Any], journal_file_id: str
    ) -> dict[str, int | float] | None:
        """
        This method fetches the currency conversion rate if required, and it also attaches
        the conversion rate file to the provided journal_file_id.
        Args:
            organization (dict[str, Any]): The organization dictionary.
            journal_file_id (str): the given Journal file ID

        Returns:
            A dict with the conversion rate.
        Raises:
            RuntimeError: If the conversion rate is None.
        """
        # data currency                  # billing currency
        if organization["currency"] != organization["billing_currency"]:
            # we need to convert
            currency = organization["currency"]
            exchanges_rates = await self.exchange_rate_client.fetch_exchange_rate(currency=currency)
            if exchanges_rates is None:
                logger.error(f"An error occurred while fetching exchange rate for {currency}")
                raise RuntimeError(f"An error occurred while fetching exchange rate for {currency}")
            filename = f"{currency}_{self.month}{self.year}"  # pragma: no cover
            # todo best to use EUR_file_sha256 to name the filename and use  like instead of eq in rq
            await self.check_attachment_duplicate_and_delete(
                journal_id=journal_file_id, filename=filename
            )  # pragma: no cover
            await self.mtp_client.create_journal_attachment(
                journal_file_id=journal_file_id, exchanges_rates=exchanges_rates, filename=filename
            )  # pragma: no cover
            return exchanges_rates
        else:
            return None

    async def get_journal_id_for_the_authorization(self, authorization_id: str) -> str | None:
        """
        This method fetches the journal ID from the given authorization ID.
        Args:
            authorization_id: The authorization ID
        Returns: The Journal ID or None if an error occurred.
        """

        journal_file = await self.get_or_create_journal_file(
            authorization_id=authorization_id, month=self.month, year=self.year
        )
        if journal_file is None:
            logger.error(
                f"The Journal file was not created for the authorization {authorization_id}"
            )
            return None
        return journal_file["id"]

    async def process_billing_per_authorization(self, authorization_data: dict[str, Any]):
        async with self.semaphore:
            try:
                journal_file_id = await self.get_journal_id_for_the_authorization(
                    authorization_id=authorization_data["id"]
                )
                organizations_per_currency = await (
                    self.finops_client.fetch_organizations_by_billing_currency(
                        billing_currency=authorization_data["currency"]
                    )
                )
                if len(organizations_per_currency) == 0:
                    logger.info(
                        f"No organizations found for Authorization ID {authorization_data['id']}"
                    )
                    return None

                tmp_folder = tempfile.gettempdir()

                filepath = f"{tmp_folder}/charges_{authorization_data['id']}_{self.year}_{self.month}.jsonl"
                async with aiofiles.open(filepath, "w") as fp:
                    for organization in organizations_per_currency:
                        if organization["operations_external_id"] == "AGR-0000-0000-0000":
                            logger.info(
                                f"Skipping organization {organization["id"]} {organization["name"]} "
                                f"because of ID AGR-0000-0000"
                            )

                        agreements = await self.mtp_client.fetch_agreement_details_by_authorization(
                            authorization_id=authorization_data["id"],
                            organization_id=organization["id"],
                        )
                        if len(agreements) != 1:
                            logger.warning(
                                f"Found {len(agreements)} while we were expecting 1 for the organization {organization['id']}"
                            )
                            continue
                        exchanges_rates = await self.check_if_rate_conversion_is_required(
                            organization=organization,
                            journal_file_id=journal_file_id,
                        )
                        charge_file = await generate_charges_file(
                            agreement=agreements,
                            organization=organization,
                            year=self.year,
                            month=self.month,
                            fp=fp,
                            exchanges_rates=exchanges_rates,
                        )

                        await self.upload_and_submit_journal(
                            journal_file_id=journal_file_id,
                            charge_jsonl_file_path=charge_file,
                        )
            except Exception as error:
                logger.error("An error occurred", exc_info=error)
                return

    async def upload_and_submit_journal(
        self, journal_file_id: str, charge_jsonl_file_path: str
    ) -> None:
        await self.mtp_client.upload_journal(
            journal_id=journal_file_id,
            file_path=charge_jsonl_file_path,
            description=f"Charge file for {self.year} {self.month}",
        )
        await self.mtp_client.submit_journal(journal_id=journal_file_id)

    async def process_all_billings(self):
        """
        This method starts the processing of all billings for each authorization.
        It also supports the processing of a single authorization if provided.
        Otherwise, it will process all the billings for all the authorizations.

        """
        if self.authorization_id:
            authorization_data = await self.mtp_client.fetch_authorizations(
                authorization_id=self.authorization_id,
                product_id=self.product_id,
            )
            if authorization_data is None:
                logger.error(f"Authorization ID {self.authorization_id} not found")
                return None
            return await self.process_billing_per_authorization(
                authorization_data=authorization_data
            )
        else:
            authorizations_data = await self.mtp_client.fetch_authorizations(
                product_id=self.product_id
            )
            tasks = []
            if len(authorizations_data) > 0:
                for authorization in authorizations_data:
                    tasks.append(
                        self.process_billing_per_authorization(authorization_data=authorization)
                    )
                logger.info(f"Processing {len(tasks)} billings tasks for {self.product_id}")
                return await asyncio.gather(*tasks)
            else:
                logger.error(f"No authorizations found for product {self.product_id}")
                return None
