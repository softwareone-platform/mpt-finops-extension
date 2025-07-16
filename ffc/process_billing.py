import asyncio
import hashlib
import json
import logging
import tempfile
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import aiofiles
import aiofiles.os
from dateutil.relativedelta import relativedelta
from django.conf import settings
from httpx import HTTPStatusError

from ffc.billing.classes import AuthorizationProcessResult, CurrencyConversionInfo, Datasource
from ffc.billing.exceptions import ErrorJournalCreation, JournalStatusError, PrefixAdapter
from ffc.billing.helpers import (
    add_line_to_monthly_charge,
    calculate_entitlement_refund_lines,
    get_trial_data,
)
from ffc.clients.exchage_rates import ExchangeRatesAsyncClient
from ffc.clients.ffc import FFCAsyncClient
from ffc.clients.mpt import MPTAsyncClient
from ffc.utils import (
    async_groupby,
    compute_daily_expenses,
)

DRAFT = "Draft"
VALIDATED = "Validated"

logger = logging.getLogger(__name__)


async def process_billing(
    year: int, month: int, authorization_id: str | None = None, dry_run=False
):
    """
    This method starts the processing of all billings for each authorization.
    It also supports the processing of a single authorization if provided.
    Otherwise, it will process all the billings for all the authorizations.

    """
    product_id = settings.MPT_PRODUCTS_IDS[0]
    mpt_client = MPTAsyncClient()

    if authorization_id:
        authorization = await mpt_client.fetch_authorization(authorization_id)
        processor = AuthorizationProcessor(year, month, authorization, dry_run)
        await processor.process()
        return
    else:
        tasks = []
        semaphore = asyncio.Semaphore(
            int(settings.EXTENSION_CONFIG.get("FFC_BILLING_PROCESS_MAX_CONCURRENCY", "10"))
        )
        async for authorization in mpt_client.fetch_authorizations():
            processor = AuthorizationProcessor(
                year, month, authorization, dry_run, semaphore=semaphore
            )
            tasks.append(asyncio.create_task(processor.process()))

        logger.info(f"Processing {len(tasks)} authorizations for {product_id}")
        results = await asyncio.gather(*tasks)
        for result in results:
            # todo process errors and send notification
            pass

    await mpt_client.close()


class AuthorizationProcessor:
    def __init__(
        self,
        year: int,
        month: int,
        authorization: dict,
        dry_run: bool = False,
        semaphore: asyncio.Semaphore | None = None,
    ):
        self.year = year
        self.month = month
        self.authorization = authorization
        self.dry_run = dry_run
        self.semaphore = semaphore
        self.product_id = settings.MPT_PRODUCTS_IDS[0]
        self.ffc_client = FFCAsyncClient()
        self.mpt_client = MPTAsyncClient()
        self.exchange_rate_client = ExchangeRatesAsyncClient()
        self.billing_start_date = datetime(day=1, month=self.month, year=self.year, tzinfo=UTC)
        self.billing_end_date = self.billing_start_date + relativedelta(months=1, days=-1)
        self.DECIMAL_DIGITS = 4
        self.DECIMAL_PRECISION = Decimal("10") ** -self.DECIMAL_DIGITS
        self.exchange_rates = {}
        self.invalid_organizations = []
        self.logger  = PrefixAdapter(logging.getLogger(__name__),
                                     {'prefix': self.authorization.get("id")})



    @asynccontextmanager
    async def acquire_semaphore(self):
        try:
            if self.semaphore:
                await self.semaphore.acquire()
            yield
        finally:
            if self.semaphore:
                await self.semaphore.release()

    async def maybe_call(
        self,
        func,
        *args,
        **kwargs,
    ):
        if not self.dry_run:
            return await func(*args, **kwargs)

    async def build_filepath(self, auth_id):
        filepath = f"charges_{auth_id}_{self.year}_{self.month:02d}.jsonl"
        filepath = f"{tempfile.gettempdir()}/{filepath}" if not self.dry_run else filepath
        return filepath

    async def evaluate_journal_status(self, auth_id, journal_external_id):
        """
        Evaluates the status of a journal.

        Parameters:
            auth_id (str): Authorization identifier.
            journal_external_id (str): External ID of the journal.

        Returns:
            dict: The journal dictionary if valid or validated.
            None: If the journal is not found.

        Raises:
            JournalStatusError: If the journal exists but is not
            in 'Draft' or 'Validated' status.
        """
        journal = await self.mpt_client.get_journal(auth_id, journal_external_id)
        if not journal:
            self.logger.error(f"No journal found for external ID: {journal_external_id}")
            return None

        journal_id = journal["id"]
        journal_status = journal["status"]
        if journal_status == VALIDATED:
            self.logger.info(f"Found already validated journal: {journal_id}")
            return journal
        elif journal_status != DRAFT:
            self.logger.warning(f"Found the journal {journal_id} with status {journal_status}")
            raise JournalStatusError
        return journal

    async def get_journal_object(self, auth_id: str, journal_external_id: str):
        """ """
        try:
            journal_status = await self.evaluate_journal_status(auth_id, journal_external_id)
            if journal_status is None:
                return None
            journal = await self.mpt_client.create_journal(
                auth_id,
                journal_external_id,
                f"{self.billing_start_date.strftime('%b %Y')} charges",
                self.billing_start_date + relativedelta(months=1),
            )
            if journal is not None:
                self.logger.info(f"new journal created: {journal['id']}")
                return journal
            else:
                self.logger.error("error creating journal.")
                raise ErrorJournalCreation
        except JournalStatusError:
            raise JournalStatusError

    async def process(self):
        """ """
        auth_id = self.authorization["id"]
        result = AuthorizationProcessResult(authorization_id=self.authorization.get('id'))
        async with self.acquire_semaphore():
            try:
                # double check with production
                if not await self.mpt_client.count_active_agreements(
                    auth_id,
                    self.billing_start_date,
                    self.billing_end_date,
                ):
                    self.logger.info(f"No active agreement in the period {self.month}/{self.year}")
                    result.errors.append(f"No active agreement for authorization {auth_id}")
                    return result

                journal_external_id = f"{self.year:04d}{self.month:02d}"
                filepath = await self.maybe_call(self.build_filepath, auth_id=auth_id)
                journal = await self.maybe_call(
                    self.get_journal_object,
                    auth_id=auth_id,
                    journal_external_id=journal_external_id,
                )
                self.logger.info(
                    "generating charges file {filepath} "
                    f"currency {self.authorization['currency']}"
                )
                await self.write_charges_file(auth_id, journal)
                await self.maybe_call(
                    self.complete_journal_process(
                        auth_id,
                        filepath,
                        journal,
                        journal_external_id,
                    ),
                )
                await aiofiles.os.unlink(filepath)

            except HTTPStatusError as error:
                status = error.response.status_code
                reason = error.response.content.decode()
                if error.response.headers.get("Content-Type") == "application/json":
                    reason = error.response.json()
                self.logger.error(f"{status} - {reason}")

            except Exception as error:
                self.logger.error(f"An error occurred: {error}", exc_info=error)

    async def write_charges_file(self, auth_id, filepath):
        async with aiofiles.open(filepath, "w") as charges_file:
            async for organization in self.ffc_client.fetch_organizations(
                self.authorization["currency"],
            ):
                self.logger.info(
                    "Processing {organization['id']} - {organization['name']}:"
                    f" {organization['operations_external_id']}"
                )
                if organization["operations_external_id"] == "AGR-0000-0000-0000":
                    self.logger.info(
                        f"Skip organization {organization['id']} - "
                        f"{organization['name']} because of ID AGR-0000-0000-0000"
                    )
                    continue

                agreements = [
                    agreement
                    async for agreement in self.mpt_client.fetch_agreements(
                        organization["id"],
                    )
                ]
                if len(agreements) != 1:
                    self.logger.warning(f"len = 1 for the organization {organization['id']}")
                    self.invalid_organizations.append((organization, agreements))
                    continue

                if agreements[0]["authorization"]["id"] != auth_id:
                    self.logger.info(f"Skipping organization  {organization['id']} because "
                        "it belongs to an agreement with different authorization: "
                        f"{agreements[0]['authorization']['id']}")

                    continue

                await self.dump_organization_charges(
                    auth_id,
                    charges_file,
                    organization,
                    agreement=agreements[0] if len(agreements) == 1 else None,
                )

            if await charges_file.tell() == 0:
                return

    async def complete_journal_process(self, auth_id, filepath, journal, journal_external_id):
        """
        This method uploads and submits the given journal, attaching also the exchange rates
        files.
        If the given journal does not exist, a new one will be created using the provided
        authorization id.
        The journal will be only submitted if it is validated.
        """
        if not journal:
            journal = await self.mpt_client.create_journal(
                auth_id,
                journal_external_id,
                f"{self.billing_start_date.strftime('%b %Y')} charges",
                self.billing_start_date + relativedelta(months=1),
            )
            self.logger.info(f"new journal created: {journal['id']}")
        journal_id = journal["id"]
        for base_currency, exchange_rates_json in self.exchange_rates.items():
            await self.attach_exchange_rates(journal_id, base_currency, exchange_rates_json)
        await self.mpt_client.upload_charges(journal_id, open(filepath, "rb"))
        if await self.is_journal_validated(journal_id):
            await self.mpt_client.submit_journal(journal_id)
        else:
            self.logger.info(f"cannot submit the journal {journal_id}, "
                             f"it doesn't get validated")

    async def get_currency_conversion_info(
        self,
        organization: dict[str, Any],
    ) -> CurrencyConversionInfo:
        data_currency = organization["currency"]
        billing_currency = organization["billing_currency"]

        if data_currency == billing_currency:
            self.logger.info(
                f"organization {organization['id']} - {organization['name']} "
                "doesn't need currency conversion"
            )
            return CurrencyConversionInfo(data_currency, billing_currency, Decimal("1"))

        exchange_rates = await self.exchange_rate_client.fetch_exchange_rates(data_currency)
        return CurrencyConversionInfo(
            data_currency,
            billing_currency,
            Decimal(exchange_rates["conversion_rates"][billing_currency]).quantize(
                self.DECIMAL_PRECISION
            ),
            exchange_rates,
        )

    async def attach_exchange_rates(
        self, journal_id: str, currency: str, exchange_rates: dict[str, Any]
    ):
        hasher = hashlib.sha256()
        serialized = json.dumps(exchange_rates)
        hasher.update(serialized.encode())
        exchange_rates_hash = hasher.hexdigest()
        filename = f"{currency}_{exchange_rates_hash}"
        attachment = await self.mpt_client.fetch_journal_attachment(journal_id, f"{currency}_")
        if attachment:
            if attachment["name"] == filename:
                return
            await self.mpt_client.delete_journal_attachment(journal_id, attachment["id"])

        await self.mpt_client.create_journal_attachment(journal_id, filename, serialized)

    async def dump_organization_charges(
        self,
        authorization_id: str,
        charges_file: Any,
        organization: dict[str, Any],
        agreement: dict[str, Any] | None = None,
    ):
        organization_id = organization["id"]
        async for datasource_info, expenses in async_groupby(
            self.ffc_client.fetch_organization_expenses(organization_id, self.year, self.month),
            lambda x: Datasource(
                x["linked_datasource_id"],
                x["linked_datasource_type"],
                x["datasource_id"],
                x["datasource_name"],
            ),
        ):
            daily_expenses = {expense["day"]: Decimal(expense["expenses"]) for expense in expenses}
            self.logger.info(
                f"expenses for datasource "
                f"{datasource_info.linked_datasource_id} -> {daily_expenses=}"
            )
            trial_start, trial_end, billing_percentage = get_trial_data(agreement=agreement)
            charges = await self.generate_datasource_charges(
                authorization_id,
                organization,
                datasource_info.linked_datasource_id,
                datasource_info.linked_datasource_type,
                datasource_info.datasource_id,
                datasource_info.datasource_name,
                daily_expenses,
                billing_percentage,
                trial_start,
                trial_end,
            )
            self.logger.info(
                f"charges for datasource {datasource_info.linked_datasource_id} -> {charges=}"
            )
            await charges_file.writelines(charges)

    async def generate_datasource_charges(
        self,
        authorization_id: str,
        organization: dict,
        linked_datasource_id: str,
        linked_datasource_type: str,
        datasource_id: str,
        datasource_name: str,
        daily_expenses: dict[int, Decimal],
        billing_percentage: Decimal,
        trial_start: date | None,
        trial_end: date | None,
    ):
        organization_id = organization["id"]
        if not daily_expenses:  # No charges available for this datasource.
            return add_line_to_monthly_charge(
                vendor_external_id=linked_datasource_id,
                datasource_id=datasource_id,
                organization_id=organization_id,
                start_date=self.billing_start_date.date(),
                end_date=self.billing_end_date.date(),
                price=Decimal(0),
                datasource_name=datasource_name,
                decimal_precision=self.DECIMAL_PRECISION,
                description="No charges available for this datasource.",
            )

        amount = daily_expenses[max(daily_expenses.keys())]
        price_in_source_currency = (
            amount.quantize(self.DECIMAL_PRECISION)
            * billing_percentage.quantize(self.DECIMAL_PRECISION)
            / Decimal(100).quantize(self.DECIMAL_PRECISION)
        )
        idx = 1
        if price_in_source_currency == 0:
            return add_line_to_monthly_charge(
                vendor_external_id=f"{linked_datasource_id}-{idx:02d}",
                datasource_id=datasource_id,
                organization_id=organization_id,
                start_date=date(
                    self.billing_start_date.year,
                    self.billing_start_date.month,
                    min(daily_expenses.keys()),
                ),
                end_date=date(
                    self.billing_start_date.year,
                    self.billing_start_date.month,
                    max(daily_expenses.keys()),
                ),
                price=Decimal(0),
                datasource_name=datasource_name,
                decimal_precision=self.DECIMAL_PRECISION,
            )

        currency_conversion_info = await self.get_currency_conversion_info(
            organization,
        )
        exchange_rate = currency_conversion_info.exchange_rate
        self.exchange_rates[currency_conversion_info.base_currency] = (
            currency_conversion_info.exchange_rates
        )

        price_in_target_currency = price_in_source_currency.quantize(
            self.DECIMAL_PRECISION
        ) * exchange_rate.quantize(self.DECIMAL_PRECISION)

        self.logger.info(
            f"{authorization_id}: {organization_id=} "
            f"{linked_datasource_id=} {datasource_name=} - "
            f"{amount=} {billing_percentage=} {price_in_source_currency=} "
            f"{exchange_rate=} {price_in_target_currency=}"
        )
        # Generate charge with total monthly spending. positive line e ne esiste una per un certo ds
        charges = add_line_to_monthly_charge(
            vendor_external_id=f"{linked_datasource_id}-{idx:02d}",
            datasource_id=datasource_id,
            organization_id=organization_id,
            start_date=date(
                self.billing_start_date.year,
                self.billing_start_date.month,
                min(daily_expenses.keys()),
            ),
            end_date=date(
                self.billing_start_date.year,
                self.billing_start_date.month,
                max(daily_expenses.keys()),
            ),
            price=price_in_target_currency,
            datasource_name=datasource_name,
            decimal_precision=self.DECIMAL_PRECISION,
        )
        idx += 1

        daily_expenses = compute_daily_expenses(daily_expenses, self.billing_start_date.day)
        entitlement = (
            await self.ffc_client.fetch_entitlement(
                organization_id,
                datasource_id,
                linked_datasource_type,
                self.billing_start_date,
                self.billing_end_date,
            )
            or {}
        )
        ent_events = entitlement.get("events", {})
        calculate_entitlement_refund_lines(
            daily_expenses=daily_expenses,
            entitlement_id=entitlement.get("id"),
            entitlement_start_date=ent_events.get("redeemed", {}).get("at"),
            entitlement_termination_date=ent_events.get("terminated", {}).get("at"),
            trial_start_date=trial_start,
            trial_end_date=trial_end,
            billing_percentage=billing_percentage,
            billing_start_date=self.billing_start_date,
            billing_end_date=self.billing_end_date,
            exchange_rate=exchange_rate,
            decimal_precision=self.DECIMAL_PRECISION,
            charges=charges,
            organization_id=organization_id,
            linked_datasource_id=linked_datasource_id,
            datasource_name=datasource_name,
            datasource_id=datasource_id,
        )
        return charges

    async def is_journal_validated(self, journal_id, max_attempts=5):
        backoff_times = [0.15, 0.45, 1.05, 2.25, 4.65]

        for attempt in range(min(max_attempts, len(backoff_times))):
            journal = await self.mpt_client.get_journal_by_id(journal_id)
            if journal.get("status") == "Validated":
                return True
            await asyncio.sleep(backoff_times[attempt])

        return False
