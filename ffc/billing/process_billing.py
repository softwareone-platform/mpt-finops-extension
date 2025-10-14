import asyncio
import hashlib
import json
import logging
import tempfile
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime
from io import BytesIO
from pathlib import Path
from typing import Any, AsyncGenerator, Coroutine

import aiofiles
import aiofiles.os
from _decimal import Decimal
from dateutil.relativedelta import relativedelta
from dateutil.rrule import DAILY, rrule
from django.conf import settings
from httpx import HTTPStatusError

from ffc.billing.dataclasses import (
    CurrencyConversionInfo,
    Datasource,
    ProcessResult,
    ProcessResultInfo,
    Refund,
    TrialInfo,
)
from ffc.billing.exceptions import (
    ExchangeRatesClientError,
    JournalStatusError,
    JournalSubmitError,
)
from ffc.billing.notification_helper import send_notifications
from ffc.clients.exchage_rates import ExchangeRatesAsyncClient
from ffc.clients.ffc import FFCAsyncClient
from ffc.clients.mpt import MPTAsyncClient
from ffc.parameters import get_billed_percentage, get_trial_end_date, get_trial_start_date
from ffc.utils import (
    async_groupby,
    compute_daily_expenses,
)

DRAFT = "Draft"
VALIDATED = "Validated"
REVIEW = "Review"
GENERATING = "Generating"
GENERATED = "Generated"
ACCEPTED = "Accepted"
COMPLETED = "Completed"
VALID_STATUS = [DRAFT, VALIDATED, REVIEW, GENERATING, GENERATED, ACCEPTED, COMPLETED]

logger = logging.getLogger(__name__)


class PrefixAdapter(logging.LoggerAdapter):
    def process(self, msg, kwargs):
        return f"[{self.extra['prefix']}] {msg}", kwargs


async def process_billing(
    year: int,
    month: int,
    cutoff_day: int,
    authorization_id: str | None = None,
    dry_run=False,
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
        response = await asyncio.gather(*tasks)
        await send_notifications(results=response, year=year, month=month, cutoff_day=cutoff_day)

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
        self.authorization_id = authorization["id"]
        self.dry_run = dry_run
        self.semaphore = semaphore
        self.product_id = settings.MPT_PRODUCTS_IDS[0]
        self.ffc_client = FFCAsyncClient()
        self.mpt_client = MPTAsyncClient()
        self.exchange_rate_client = ExchangeRatesAsyncClient()
        self.billing_start_date = datetime(day=1, month=self.month, year=self.year, tzinfo=UTC)
        self.billing_end_date = self.billing_start_date + relativedelta(months=1, seconds=-1)
        self.DECIMAL_DIGITS = 4
        self.DECIMAL_PRECISION = Decimal("10") ** -self.DECIMAL_DIGITS
        self.exchange_rates: dict[str, Any] = {}
        self.invalid_organizations: list[Any] = []
        self.logger = PrefixAdapter(
            logging.getLogger(__name__), {"prefix": self.authorization.get("id")}
        )

    async def _safe_unlink(self, filepath: str) -> None:
        try:
            await aiofiles.os.unlink(filepath)
        except FileNotFoundError:
            self.logger.debug(f"File {filepath} not found during cleanup, ignoring")
        except Exception as error:
            self.logger.warning(f"Failed to cleanup file {filepath}: {error}")

    @asynccontextmanager
    async def acquire_semaphore(self) -> AsyncGenerator[None, Any]:
        """
        This method acquires and releases a  semaphore.
        """
        try:
            if self.semaphore:
                await self.semaphore.acquire()
            yield
        finally:
            if self.semaphore:
                self.semaphore.release()

    async def maybe_call(
        self,
        func,
        *args,
        **kwargs,
    ) -> Any | None:
        """
        Conditionally calls and awaits the given asynchronous function.

        If `self.dry_run` is False, this method awaits and returns the result
        of `func(*args, **kwargs)`.
        If `self.dry_run` is True, the function is not called and None is returned.

        Parameters:
            func (Callable[..., Awaitable]): The asynchronous function to
            potentially call.
            *args: Positional arguments to pass to the function.
            **kwargs: Keyword arguments to pass to the function.

        Returns:
            Any: The result of the awaited function, or None if in dry-run mode.
        """
        if not self.dry_run:
            return await func(*args, **kwargs)
        return None

    def build_filepath(self) -> str:
        """
        Constructs and returns the file path for a charges JSONL file.

        The file name is formatted as:
            `charges_<authorization_id>_<year>_<month>.jsonl`

        If `self.dry_run` is False, the file is placed in the system temporary directory.
        If `self.dry_run` is True, only the file name is returned (no path prepended).

        Returns:
            str: The constructed file path or file name depending on dry-run mode.
        """
        filepath = f"charges_{self.authorization_id}_{self.year}_{self.month:02d}.jsonl"
        filepath = f"{tempfile.gettempdir()}/{filepath}" if not self.dry_run else filepath
        return filepath

    async def evaluate_journal_status(self, journal_external_id):
        """
        Evaluates the status of a journal.

        Parameters:
            journal_external_id (str): External ID of the journal.

        Returns:
            dict: The journal dictionary if valid or validated.
            None: If the journal is not found.

        Raises:
            JournalStatusError: If the journal exists but is not
            in 'Draft' or 'Validated' status.
        """
        journal = await self.mpt_client.get_journal(self.authorization_id, journal_external_id)
        if not journal:
            error_msg = f"No journal found for external ID: {journal_external_id}"
            self.logger.info(error_msg)
            return None
        journal_id = journal["id"]
        journal_status = journal["status"]
        if journal_status in VALID_STATUS:
            msg = f"Already found journal: {journal_id} with status {journal_status}"
            self.logger.info(msg)
            return journal
        else:
            error_msg = f"Found the journal {journal_id} with status {journal_status}"
            self.logger.error(error_msg)
            raise JournalStatusError(error_msg, journal_id)

    async def process(self) -> ProcessResultInfo:
        """
        This method is responsible for passing a journal with status VALIDATED to
        the function that writes the charges into a file and then to complete the
        process by submitting the journal.
        """

        async with self.acquire_semaphore():
            try:
                active_agreements = await self.mpt_client.count_active_agreements(
                    self.authorization_id,
                    self.billing_start_date,
                    self.billing_end_date,
                )
                self.logger.info(
                    f"{active_agreements} agreements have been "
                    f"found for authorization {self.authorization_id}"
                )
                if not active_agreements:
                    self.logger.info(f"No active agreement in the period {self.month}/{self.year}")
                    result_info = ProcessResultInfo(
                        authorization_id=self.authorization_id, result=ProcessResult.JOURNAL_SKIPPED
                    )
                    result_info.message = (
                        f"No active agreement for authorization {self.authorization_id}"
                    )

                    return result_info

                journal_external_id = f"{self.year:04d}{self.month:02d}"
                filepath = self.build_filepath()
                try:
                    journal = await self.maybe_call(
                        self.evaluate_journal_status, journal_external_id
                    )
                    if journal and journal["status"] == VALIDATED:
                        await self.maybe_call(self.mpt_client.submit_journal, journal["id"])
                        result_info = ProcessResultInfo(
                            authorization_id=self.authorization_id,
                            result=ProcessResult.JOURNAL_GENERATED,
                        )
                        result_info.journal_id = journal["id"]
                        return result_info

                    elif journal and journal["status"] != DRAFT:
                        result_info = ProcessResultInfo(
                            authorization_id=self.authorization_id,
                            result=ProcessResult.JOURNAL_SKIPPED,
                        )
                        result_info.journal_id = journal["id"]
                        return result_info

                except JournalStatusError as error:
                    self.logger.warning(error)
                    result_info = ProcessResultInfo(
                        authorization_id=self.authorization_id, result=ProcessResult.JOURNAL_SKIPPED
                    )
                    result_info.message = str(error)
                    result_info.journal_id = error.journal_id
                    return result_info
                self.logger.info(
                    f"generating charges file {filepath} "
                    f"currency {self.authorization['currency']}"
                )
                try:
                    has_charges = await self.write_charges_file(filepath=filepath)
                    if has_charges:
                        created_journal = await self.maybe_call(
                            self.complete_journal_process,
                            filepath,
                            journal,
                            journal_external_id,
                        )
                        await self.maybe_call(self._safe_unlink, filepath)
                        result_info = ProcessResultInfo(
                            authorization_id=self.authorization_id,
                            result=ProcessResult.JOURNAL_GENERATED,
                        )
                        result_info.journal_id = (created_journal or {}).get("id", "-")
                        return result_info
                    else:
                        result_info = ProcessResultInfo(
                            authorization_id=self.authorization_id,
                            result=ProcessResult.JOURNAL_SKIPPED,
                        )
                        result_info.message = "No charges for this authorization."
                        return result_info

                except JournalSubmitError as error:
                    self.logger.warning(error)
                    result_info = ProcessResultInfo(
                        authorization_id=self.authorization_id, result=ProcessResult.ERROR
                    )
                    result_info.message = str(error)
                    result_info.journal_id = error.journal_id
                    return result_info

            except HTTPStatusError as error:
                status = error.response.status_code
                reason = error.response.content.decode()
                if error.response.headers.get("Content-Type") == "application/json":
                    reason = error.response.json()
                self.logger.error(f"{status} - {reason}")
                result_info = ProcessResultInfo(
                    authorization_id=self.authorization_id, result=ProcessResult.ERROR
                )
                result_info.message = str(error)
                return result_info

            except Exception as error:
                self.logger.error(f"An error occurred: {error}", exc_info=error)
                result_info = ProcessResultInfo(
                    authorization_id=self.authorization_id, result=ProcessResult.ERROR
                )
                result_info.message = str(error)
                return result_info

    async def write_charges_file(self, filepath) -> bool:
        """
        This method writes the charges file to the given filepath.
        If there is more than one agreement for an organization, it won't be processed.
        If the authorization's in the agreement is not the same as the authorization's ID caller
        it will be skipped as well as it will be processed later.
        Parameters:
            filepath (str): the file path to write the charges file to.
        Returns:
            True if the charges file was written successfully.
            False if the charges file was not written.
        """
        async with aiofiles.open(filepath, "w") as charges_file:
            async for organization in self.ffc_client.fetch_organizations(
                self.authorization["currency"],
            ):
                self.logger.info(
                    f"Processing {organization['id']} - {organization['name']}:"
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
                    self.logger.warning(
                        f"Found {len(agreements)} while we were expecting "
                        f"1 for the organization {organization['id']}"
                    )
                    self.invalid_organizations.append((organization, agreements))
                    continue

                if agreements[0]["authorization"]["id"] != self.authorization_id:
                    self.logger.info(
                        f"Skipping organization {organization['id']} because "
                        "it belongs to an agreement with different authorization: "
                        f"{agreements[0]['authorization']['id']}"
                    )

                    continue

                await self.dump_organization_charges(
                    charges_file,
                    organization,
                    agreement=agreements[0],
                )

            if await charges_file.tell() == 0:
                return False
            return True

    async def complete_journal_process(self, filepath, journal, journal_external_id) -> dict:
        """
        This method uploads and submits the given journal, attaching also the exchange rates
        files.
        If the given journal does not exist, a new one will be created using the provided
        authorization id.
        The journal will be only submitted if it is validated.
        """
        if not journal:
            journal = await self.mpt_client.create_journal(
                self.authorization_id,
                journal_external_id,
                f"{self.billing_start_date.strftime('%b %Y')} charges",
                self.billing_start_date + relativedelta(months=1),
            )
            self.logger.info(f"new journal created: {journal['id']}")
        journal_id = journal["id"]
        for base_currency, exchange_rates_json in self.exchange_rates.items():
            await self.attach_exchange_rates(journal_id, base_currency, exchange_rates_json)

        async with aiofiles.open(filepath, "rb") as file:
            data = await file.read()
        buf = BytesIO(data)
        buf.name = Path(filepath).name
        await self.mpt_client.upload_charges(journal_id, buf)
        if await self.is_journal_status_validated(journal_id):
            self.logger.info(f"submitting the journal {journal_id}.")
            await self.mpt_client.submit_journal(journal_id)
            return journal
        else:
            error_msg = f"cannot submit the journal {journal_id} it doesn't get validated"
            self.logger.info(error_msg)
            raise JournalSubmitError(error_msg, journal_id)

    async def get_currency_conversion_info(
        self,
        organization: dict[str, Any],
    ) -> CurrencyConversionInfo:
        """
        This method checks if a conversion is needed.
        If the data currency and the billing currency are not the same,
        we need to fetch the exchange rates.
        """
        data_currency = organization["currency"]
        billing_currency = organization["billing_currency"]

        if data_currency == billing_currency:
            self.logger.info(
                f"organization {organization['id']} - {organization['name']} "
                "doesn't need currency conversion"
            )
            return CurrencyConversionInfo(data_currency, billing_currency, Decimal("1"))

        exchange_rates = await self.exchange_rate_client.fetch_exchange_rates(data_currency)
        if not exchange_rates:
            self.logger.error(
                f"An error occurred while fetching exchange rates for {data_currency}"
            )
            raise ExchangeRatesClientError

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
    ) -> Coroutine | None:
        """
        This method checks if an attachment already exists for the given journal.
        If it exists, it will be deleted and a new one will be created with the
        given exchange rates.
        If no attachment exists, a new one will be created.
        """
        hasher = hashlib.sha256()
        serialized = json.dumps(exchange_rates)
        hasher.update(serialized.encode())
        exchange_rates_hash = hasher.hexdigest()
        filename = f"{currency}_{exchange_rates_hash}"
        attachment = await self.mpt_client.fetch_journal_attachment(journal_id, f"{currency}_")
        if attachment:  # pragma no cover
            if attachment["name"] == filename:
                return None
            await self.mpt_client.delete_journal_attachment(journal_id, attachment["id"])

        return await self.mpt_client.create_journal_attachment(journal_id, filename, serialized)

    async def dump_organization_charges(
        self,
        charges_file: Any,
        organization: dict[str, Any],
        agreement: dict[str, Any],
    ) -> Coroutine | None:
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
            daily_expenses = {
                expense["day"]: Decimal(expense["total_expenses"]) for expense in expenses
            }
            self.logger.info(
                f"expenses for datasource "
                f"{datasource_info.linked_datasource_id} -> {daily_expenses=}"
            )
            charges = await self.generate_datasource_charges(
                organization,
                agreement,
                datasource_info.linked_datasource_id,
                datasource_info.linked_datasource_type,
                datasource_info.datasource_id,
                datasource_info.datasource_name,
                daily_expenses,
            )
            self.logger.info(
                f"charges for datasource {datasource_info.linked_datasource_id} : {charges}"
            )
            await charges_file.writelines(charges)

    async def generate_datasource_charges(
        self,
        organization: dict,
        agreement: dict[str, Any],
        linked_datasource_id: str,
        linked_datasource_type: str,
        datasource_id: str,
        datasource_name: str,
        daily_expenses: dict[int, Decimal],
    ) -> list[str]:
        """
        This method generates all the charges for the given datasource and
        calculates the refund for the Trials and Entitlements periods.
        """
        organization_id = organization["id"]
        if not daily_expenses:  # No charges available for this datasource.
            return [
                self.generate_charge_line(
                    f"{linked_datasource_id}-01",
                    datasource_id,
                    organization_id,
                    self.billing_start_date,
                    self.billing_end_date,
                    Decimal(0),
                    datasource_name,
                    description="No charges available for this datasource.",
                )
            ]

        billing_percentage = get_billing_percentage(agreement=agreement)
        amount = daily_expenses[max(daily_expenses.keys())]
        price_in_source_currency = (amount * billing_percentage / Decimal(100)).quantize(
            self.DECIMAL_PRECISION
        )
        start_dt = self.billing_start_date.replace(day=min(daily_expenses.keys())).date()
        end_dt = self.billing_start_date.replace(day=max(daily_expenses.keys())).date()

        if price_in_source_currency == Decimal(0):
            return [
                self.generate_charge_line(
                    f"{linked_datasource_id}-01",
                    datasource_id,
                    organization_id,
                    start_dt,
                    end_dt,
                    Decimal(0),
                    datasource_name,
                )
            ]

        currency_conversion_info = await self.get_currency_conversion_info(
            organization,
        )
        exchange_rate = currency_conversion_info.exchange_rate
        if currency_conversion_info.exchange_rates:
            self.exchange_rates[currency_conversion_info.base_currency] = (
                currency_conversion_info.exchange_rates
            )

        price_in_target_currency = price_in_source_currency.quantize(
            self.DECIMAL_PRECISION
        ) * exchange_rate.quantize(self.DECIMAL_PRECISION)

        self.logger.info(
            f": {organization_id=} "
            f"{linked_datasource_id=} {datasource_name=} - "
            f"{amount=} {billing_percentage=} {price_in_source_currency=} "
            f"{exchange_rate=} {price_in_target_currency=}"
        )
        charges = [
            self.generate_charge_line(
                f"{linked_datasource_id}-01",
                datasource_id,
                organization_id,
                start_dt,
                end_dt,
                price_in_target_currency,
                datasource_name,
            )
        ]
        charges.extend(
            await self.generate_refund_lines(
                daily_expenses=daily_expenses,
                agreement=agreement,
                exchange_rate=exchange_rate,
                organization_id=organization_id,
                linked_datasource_id=linked_datasource_id,
                linked_datasource_type=linked_datasource_type,
                datasource_name=datasource_name,
                datasource_id=datasource_id,
            )
        )
        return charges

    async def is_journal_status_validated(self, journal_id, max_attempts=5) -> bool:
        backoff_times = [0.15, 0.45, 1.05, 2.25, 4.65]

        for attempt in range(min(max_attempts, len(backoff_times))):
            journal = await self.mpt_client.get_journal_by_id(journal_id)
            if journal.get("status") == "Validated":
                return True
            await asyncio.sleep(backoff_times[attempt])

        return False

    def generate_refunds(
        self,
        daily_expenses: dict[int, Decimal],
        agreement: dict[str, Any],
        entitlement_id: str | None,
        entitlement_start_date: str | None = None,
        entitlement_termination_date: str | None = None,
    ) -> list[Refund]:
        """
        This function generates a list of refunds for a billing period, considering
        the trials and entitlements period. Trials get priority over Entitlements
        """
        refund_lines = []
        trial_days: set[int] = set()
        trial_start_date, trial_end_date = get_trial_dates(agreement=agreement)
        if trial_start_date and trial_end_date and trial_end_date >= self.billing_start_date.date():
            trial_info = self.get_trial_info(
                trial_start_date,
                trial_end_date,
            )
            trial_amount = Decimal(
                sum(daily_expenses.get(day, Decimal("0")) for day in trial_info.trial_days)
            )
            trial_days = trial_info.trial_days
            refund_lines.append(
                Refund(
                    trial_amount,
                    trial_info.refund_from,
                    trial_info.refund_to,
                    (
                        "Refund due to trial period "
                        f"(from {trial_start_date.strftime('%d %b %Y')} "  # type: ignore
                        f"to {trial_end_date.strftime('%d %b %Y')})"  # type: ignore
                    ),
                )
            )

        if entitlement_start_date:
            entitlement_days = self.get_entitlement_days(
                trial_days=trial_days,
                entitlement_start_date=entitlement_start_date,
                entitlement_end_date=entitlement_termination_date,
            )
            for r_start, r_end in split_entitlement_days_into_ranges(entitlement_days):
                ent_amount = Decimal(
                    sum(daily_expenses.get(day, 0) for day in range(r_start, r_end + 1))
                )

                refund_lines.append(
                    Refund(
                        ent_amount,
                        date(
                            year=self.billing_start_date.year,
                            month=self.billing_start_date.month,
                            day=r_start,
                        ),
                        date(
                            year=self.billing_start_date.year,
                            month=self.billing_start_date.month,
                            day=r_end,
                        ),
                        f"Refund due to active entitlement {entitlement_id}",
                    )
                )
        return refund_lines

    async def generate_refund_lines(
        self,
        daily_expenses: dict[int, Decimal],
        agreement: dict[str, Any],
        exchange_rate: Decimal,
        organization_id: str,
        linked_datasource_id: str,
        linked_datasource_type: str,
        datasource_id: str,
        datasource_name: str,
    ) -> list[str]:
        """
        This function calculates the refund lines for a billing period
        """
        daily_expenses = compute_daily_expenses(daily_expenses, self.billing_end_date.day)
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
        entitlement_id = entitlement.get("id")
        entitlement_start_date = ent_events.get("redeemed", {}).get("at")
        entitlement_termination_date = ent_events.get("terminated", {}).get("at")
        billing_percentage = get_billing_percentage(agreement=agreement)
        idx = 2
        charges = []
        refunds = self.generate_refunds(
            daily_expenses=daily_expenses,
            agreement=agreement,
            entitlement_id=entitlement_id,
            entitlement_start_date=entitlement_start_date,
            entitlement_termination_date=entitlement_termination_date,
        )
        for refund in refunds:
            expenses = Decimal(refund.amount)
            refund_in_source_currency = (
                expenses.quantize(self.DECIMAL_PRECISION)
                * billing_percentage.quantize(self.DECIMAL_PRECISION)
                / Decimal(100).quantize(self.DECIMAL_PRECISION)
            )
            refund_in_target_currency = refund_in_source_currency * exchange_rate.quantize(
                self.DECIMAL_PRECISION
            )
            charges.append(
                self.generate_charge_line(
                    f"{linked_datasource_id}-{idx:02d}",
                    datasource_id,
                    organization_id,
                    refund.start_date,
                    refund.end_date,
                    -refund_in_target_currency,
                    datasource_name,
                    refund.description,
                )
            )

            idx += 1
        return charges

    def get_trial_info(
        self,
        trial_start_date: date,
        trial_end_date: date,
    ) -> TrialInfo:
        # Trial period can start or end on month other than billing month period.
        # In this situation, we need to limit refunded expenses
        # to a period overlapping with billing month.
        # Example, billing month is June 1-30, a trial period is May 17 - June 17
        # We need to refund expenses from June 1st to June 17th
        trial_refund_from = max(trial_start_date, self.billing_start_date.date())
        trial_refund_to = min(trial_end_date, self.billing_end_date.date())
        trial_days = {
            dt.date().day for dt in rrule(DAILY, dtstart=trial_refund_from, until=trial_refund_to)
        }
        return TrialInfo(trial_days, trial_refund_from, trial_refund_to)

    def get_entitlement_days(
        self,
        trial_days: set[int],
        entitlement_start_date: str,
        entitlement_end_date: str | None = None,
    ) -> set[int]:
        """
        Calculate the set of entitlement day numbers within a date range,
        excluding the given trial day numbers.

        Args:
            entitlement_start_date (str): ISO format start date string.
            entitlement_end_date (Optional[str]): ISO format end date string, or None.
            trial_days (Optional[Set[int]]): Set of trial day numbers (1–31)

        Returns:
            Set[int]: Set of day numbers (1–31) representing entitlement days.
        """
        start_date = max(
            datetime.fromisoformat(entitlement_start_date).date(), self.billing_start_date.date()
        )
        end_date = min(
            datetime.fromisoformat(entitlement_end_date).date()
            if entitlement_end_date
            else self.billing_end_date.date(),
            self.billing_end_date.date(),
        )
        entitlement_days = {
            dt.date().day
            for dt in rrule(DAILY, dtstart=start_date, until=end_date)
            if dt.date().day not in trial_days
        }
        return entitlement_days

    def generate_charge_line(
        self,
        vendor_external_id: str,
        datasource_id: str,
        organization_id: str,
        start_date: date,
        end_date: date,
        price: Decimal,
        datasource_name: str,
        description: str = "",
    ) -> str:
        """
        This function generates a charge line for a vendor and datasource.
        """
        line = json.dumps(
            {
                "externalIds": {
                    "vendor": vendor_external_id,
                    "invoice": "-",
                    "reference": datasource_id,
                },
                "search": {
                    "subscription": {
                        "criteria": "subscription.externalIds.vendor",
                        "value": organization_id,
                    },
                    "item": {
                        "criteria": "item.externalIds.vendor",
                        "value": settings.EXTENSION_CONFIG["FFC_EXTERNAL_PRODUCT_ID"],
                    },
                },
                "period": {
                    "start": datetime(
                        start_date.year, start_date.month, start_date.day, tzinfo=UTC
                    ).isoformat(),
                    "end": datetime(
                        end_date.year,
                        end_date.month,
                        end_date.day,
                        hour=23,
                        minute=59,
                        second=59,
                        microsecond=0,
                        tzinfo=UTC,
                    ).isoformat(),
                },
                "price": {
                    "unitPP": str(price.quantize(self.DECIMAL_PRECISION)),
                    "PPx1": str(price.quantize(self.DECIMAL_PRECISION)),
                },
                "quantity": 1,
                "description": {
                    "value1": datasource_name,
                    "value2": description,
                },
                "segment": "COM",
            }
        )
        return f"{line}\n"


def get_trial_dates(agreement: dict[str, Any]) -> tuple[Any, Any]:
    trial_start = get_trial_start_date(agreement)
    trial_end = get_trial_end_date(agreement)
    return trial_start, trial_end


def get_billing_percentage(agreement: dict[str, Any]) -> Decimal:
    return Decimal(
        get_billed_percentage(agreement).get("value")
        or settings.EXTENSION_CONFIG["DEFAULT_BILLED_PERCENTAGE"]
    )


def split_entitlement_days_into_ranges(entitlement_days: set[int]):
    if not entitlement_days:
        return []
    sorted_days = sorted(entitlement_days)
    ranges = []
    start = prev = sorted_days[0]
    for d in sorted_days[1:]:
        if d == prev + 1:
            prev = d
        else:  # pragma no cover
            # investigate how to test this case
            ranges.append((start, prev))
            start = prev = d
    ranges.append((start, prev))
    return ranges
