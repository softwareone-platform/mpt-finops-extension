import asyncio
import hashlib
import json
import logging
import tempfile
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any, List

import aiofiles
import aiofiles.os
from dateutil.relativedelta import relativedelta
from dateutil.rrule import DAILY, rrule
from django.conf import settings
from httpx import HTTPStatusError

from ffc.clients.exchage_rates import ExchangeRatesAsyncClient
from ffc.clients.ffc import FFCAsyncClient
from ffc.clients.mpt import MPTAsyncClient
from ffc.utils import (
    async_groupby,
    convert_expenses_to_daily,
    get_ff_parameter,
)

logger = logging.getLogger(__name__)


@dataclass
class Datasource:
    linked_datasource_id: str
    linked_datasource_type: str
    datasource_id: str
    datasource_name: str


@dataclass
class Refund:
    amount: Decimal
    start_date: date
    end_date: date
    description: str


@dataclass
class CurrencyConversionInfo:
    base_currency: str
    billing_currency: str
    exchange_rate: Decimal
    exchange_rates: dict[str, Any] | None = None


class BillingProcess:
    def __init__(
        self,
        year: int,
        month: int,
        authorization_id: str | None = None,
        dry_run: bool = False,
    ):
        self.year = year
        self.month = month
        self.authorization_id = authorization_id
        self.dry_run = dry_run
        self.product_id = settings.MPT_PRODUCTS_IDS[0]
        self.ffc_client = FFCAsyncClient()
        self.mpt_client = MPTAsyncClient()
        self.exchange_rate_client = ExchangeRatesAsyncClient()
        self.billing_start_date = datetime(day=1, month=self.month, year=self.year, tzinfo=UTC)
        self.billing_end_date = self.billing_start_date + relativedelta(months=1, days=-1)
        self.semaphore = asyncio.Semaphore(
            int(settings.EXTENSION_CONFIG.get("FFC_BILLING_PROCESS_MAX_CONCURRENCY", "10"))
        )
        self.DECIMAL_DIGITS = 4
        self.DECIMAL_PRECISION = Decimal("10") ** -self.DECIMAL_DIGITS

    async def run(self):
        """
        This method starts the processing of all billings for each authorization.
        It also supports the processing of a single authorization if provided.
        Otherwise, it will process all the billings for all the authorizations.

        """
        if self.authorization_id:
            authorization = await self.mpt_client.fetch_authorization(self.authorization_id)
            await self.process_authorization(authorization)
            return
        else:
            tasks = []
            async for authorization in self.mpt_client.fetch_authorizations():
                tasks.append(asyncio.create_task(self.process_authorization(authorization)))

            logger.info(f"Processing {len(tasks)} authorizations for {self.product_id}")
            await asyncio.gather(*tasks)

        await self.ffc_client.close()
        await self.mpt_client.close()
        await self.exchange_rate_client.close()

    async def process_authorization(self, authorization: dict[str, Any]):
        auth_id = authorization["id"]

        async with self.semaphore:
            try:
                # double check with production
                if not await self.mpt_client.count_active_agreements(
                    auth_id,
                    self.billing_start_date,
                    self.billing_end_date,
                ):
                    logger.info(
                        f"{auth_id}: No active agreement for authorization {auth_id} "
                        f"in the period {self.month}/{self.year}",
                    )
                    return

                journal = None
                journal_id = None

                if not self.dry_run:
                    journal_external_id = f"{self.year:04d}{self.month:02d}"

                    journal = await self.mpt_client.get_journal(auth_id, journal_external_id)

                    if journal:
                        journal_id = journal["id"]
                        journal_status = journal["status"]
                        if journal_status == "Validated":
                            logger.info(
                                f"{auth_id}: Submit already validated journal: {journal_id}"
                            )
                            await self.mpt_client.submit_journal(journal_id)
                            return
                        elif journal_status != "Draft":
                            logger.warning(
                                f"{auth_id}: Found the journal {journal_id} "
                                f"with status {journal_status}"
                            )
                            return

                filepath = f"charges_{auth_id}_{self.year}_{self.month:02d}.jsonl"
                if not self.dry_run:
                    filepath = f"{tempfile.gettempdir()}/{filepath}"

                logger.info(
                    f"{auth_id}: generating charges file {filepath} "
                    f"currency {authorization['currency']}"
                )
                exchange_rates = {}
                async with aiofiles.open(filepath, "w") as charges_file:
                    async for organization in self.ffc_client.fetch_organizations(
                        authorization["currency"],
                    ):
                        logger.info(
                            f"{auth_id}: Processing {organization['id']} - {organization['name']}:"
                            f" {organization['operations_external_id']}"
                        )
                        if organization["operations_external_id"] == "AGR-0000-0000-0000":
                            logger.info(
                                f"{auth_id}: Skip organization {organization['id']} - "
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
                            logger.warning(
                                f"{auth_id}: Found {len(agreements)} while we were expecting "
                                f"1 for the organization {organization['id']}"
                            )
                            continue

                        if agreements[0]["authorization"]["id"] != auth_id:
                            logger.warning(
                                f"{auth_id}: Skipping organization  {organization['id']} because "
                                "it belongs to an agreement with different authorization: "
                                f"{agreements[0]['authorization']['id']}"
                            )
                            continue

                        currency_conversion_info = await self.get_currency_conversion_info(
                            auth_id,
                            organization,
                        )
                        exchange_rates[currency_conversion_info.base_currency] = (
                            currency_conversion_info.exchange_rates
                        )
                        await self.dump_organization_charges(
                            auth_id,
                            charges_file,
                            organization,
                            currency_conversion_info.exchange_rate,
                            agreement=agreements[0] if len(agreements) == 1 else None,
                        )

                    if await charges_file.tell() == 0:
                        return


                if not self.dry_run:
                    if not journal:
                        journal = await self.mpt_client.create_journal(
                            auth_id,
                            journal_external_id,
                            f"{self.billing_start_date.strftime('%b %Y')} charges",
                            self.billing_start_date + relativedelta(months=1),
                        )
                        journal_id = journal["id"]
                        logger.info(f"{auth_id}: new journal created: {journal['id']}")

                    for base_currency, exchange_rates_json in exchange_rates.items():
                        await self.attach_exchange_rates(journal_id, base_currency, exchange_rates_json)

                    await self.mpt_client.upload_charges(journal_id, open(filepath, "rb"))

                    if await self.is_journal_validated(journal_id):
                        await self.mpt_client.submit_journal(journal_id)
                    else:
                        logger.warning(
                            f"{auth_id}: cannot submit the journal "
                            f"{journal_id}, it doesn't get validated",
                        )
                    await aiofiles.os.unlink(filepath)

            except HTTPStatusError as he:
                status = he.response.status_code
                reason = ""
                if he.response.headers.get("Content-Type") == "application/json":
                    reason = he.response.json()
                else:
                    reason = he.response.content.decode()
                logger.error(f"{status} - {reason}")

            except Exception as error:
                logger.error("An error occurred", exc_info=error)


    async def get_currency_conversion_info(
        self,
        authorization_id: str,
        organization: dict[str, Any],
    ) -> CurrencyConversionInfo:
        data_currency = organization["currency"]
        billing_currency = organization["billing_currency"]

        if data_currency == billing_currency:
            logger.info(
                f"{authorization_id}: organization {organization['id']} - {organization['name']} "
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
        self, journal_id: str, currency: str, exchage_rates: dict[str, Any]
    ):
        hasher = hashlib.sha256()
        serialized = json.dumps(exchage_rates)
        hasher.update(serialized.encode())
        exchange_rates_hash = hasher.hexdigest()
        filename = f"{currency}_{exchange_rates_hash}"
        attachment = await self.mpt_client.fetch_journal_attachment(journal_id, f"{currency}_")
        if attachment:
            if attachment["name"] == filename:
                return
            await self.mpt_client.delete_journal_attachment(journal_id, attachment["id"])

        await self.mpt_client.create_journal_attachment(journal_id, filename, serialized)

    def generate_refunds(
        self,
        daily_expenses: dict[int, Decimal],
        entitlement_id: str | None,
        entitlement_start_date: str | None,
        entitlement_termination_date: str | None,
        trial_start_date: date | None,
        trial_end_date: date | None,
    ) -> List[dict[str, Any]]:
        refund_lines = []
        trial_days = set()
        entitlement_days = set()

        trial_refund_from = None
        trial_refund_to = None
        if trial_start_date and trial_end_date:
            # Trial period can start or end on month other than billing month period.
            # In this situation, we need to limit refunded expenses
            # to a period overlapping with billing month.
            # Example, billing month is June 1-30, a trial period is May 17 - June 17
            # We need to refund expenses from June 1st to June 17th
            trial_refund_from = max(trial_start_date, self.billing_start_date.date())
            trial_refund_to = min(trial_end_date, self.billing_end_date.date())
            trial_days = {
                dt.date().day
                for dt in rrule(
                    DAILY,
                    dtstart=trial_refund_from,
                    until=trial_refund_to,
                )
            }

        if entitlement_start_date:
            if entitlement_termination_date:
                entitlement_termination = datetime.fromisoformat(
                    entitlement_termination_date,
                )
            else:
                entitlement_termination = self.billing_end_date
            entitlement_days = {
                dt.date().day
                for dt in rrule(
                    DAILY,
                    dtstart=max(
                        datetime.fromisoformat(entitlement_start_date), self.billing_start_date
                    ),
                    until=min(
                        entitlement_termination,
                        self.billing_end_date,
                    ),
                )
                if dt.date().day not in trial_days
            }

        if trial_days:
            trial_amount = sum(daily_expenses[d] for d in trial_days)

            refund_lines.append(
                Refund(
                    trial_amount,
                    trial_refund_from,
                    trial_refund_to,
                    (
                        "Refund due to trial period "
                        f"(from {trial_start_date.strftime("%d %b %Y")} "  # type: ignore
                        f"to {trial_end_date.strftime("%d %b %Y")})"  # type: ignore
                    ),
                )
            )

        if entitlement_days:
            sorted_days = sorted(entitlement_days)
            ranges = []
            start = prev = sorted_days[0]
            for d in sorted_days[1:]:
                if d == prev + 1:
                    prev = d
                else:
                    ranges.append((start, prev))
                    start = prev = d
            ranges.append((start, prev))

            for r_start, r_end in ranges:
                ent_amount = sum(daily_expenses[d] for d in range(r_start, r_end + 1))

                refund_lines.append(
                    Refund(
                        ent_amount,
                        date(
                            self.billing_start_date.year,
                            self.billing_start_date.month,
                            r_start,
                        ),
                        date(
                            self.billing_start_date.year,
                            self.billing_start_date.month,
                            r_end,
                        ),
                        f"Refund due to active entitlement {entitlement_id}",
                    )
                )

        return refund_lines

    async def dump_organization_charges(
        self,
        authorization_id: str,
        charges_file: Any,
        organization: dict[str, Any],
        exchange_rate: Decimal,
        agreement: dict[str, Any] | None = None,
    ):
        if agreement:
            trial_start = get_ff_parameter(agreement, "trialStartDate", is_date=True)
            trial_end = get_ff_parameter(agreement, "trialEndDate", is_date=True)
            billing_percentage = Decimal(
                get_ff_parameter(agreement, "billedPercentage")
                or settings.EXTENSION_CONFIG["DEFAULT_BILLED_PERCENTAGE"]
            )
            logger.info(
                f"{authorization_id}: agreement {agreement['id']} found for organization "
                f"{organization['id']} {organization['name']} -> "
                f"{billing_percentage=} {trial_start=} {trial_end=}"
            )
        else:
            trial_start = None
            trial_end = None
            billing_percentage = Decimal(settings.EXTENSION_CONFIG["DEFAULT_BILLED_PERCENTAGE"])
            logger.info(
                f"{authorization_id}: agreement not found for organization "
                f"{organization['id']} {organization['name']} -> "
                f"{billing_percentage=}"
            )

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
            logger.info(
                f"{authorization_id}: expenses for "
                f"datasource {datasource_info.linked_datasource_id} -> {daily_expenses=}"
            )
            charges = await self.generate_datasource_charges(
                authorization_id,
                organization_id,
                datasource_info.linked_datasource_id,
                datasource_info.linked_datasource_type,
                datasource_info.datasource_id,
                datasource_info.datasource_name,
                daily_expenses,
                billing_percentage,
                exchange_rate,
                trial_start,
                trial_end,
            )
            logger.info(
                f"{authorization_id}: charges for "
                f"datasource {datasource_info.linked_datasource_id} -> {charges=}"
            )
            await charges_file.writelines(charges)

    async def generate_datasource_charges(
        self,
        authorization_id: str,
        organization_id: str,
        linked_datasource_id: str,
        linked_datasource_type: str,
        datasource_id: str,
        datasource_name: str,
        daily_expenses: dict[int, Any],
        billing_percentage: Decimal,
        exchange_rate: Decimal,
        trial_start: date | None,
        trial_end: date | None,
    ):
        if not daily_expenses:
            line = json.dumps(
                self.get_charge_line(
                    linked_datasource_id,
                    datasource_id,
                    organization_id,
                    self.billing_start_date.date(),
                    self.billing_end_date.date(),
                    Decimal(0),
                    datasource_name,
                    description="No charges available for this datasource.",
                )
            )
            return [f"{line}\n"]

        charges = []

        idx = 1

        amount = daily_expenses[max(daily_expenses.keys())]

        price_in_source_currency = (
            amount.quantize(self.DECIMAL_PRECISION)
            * billing_percentage.quantize(self.DECIMAL_PRECISION)
            / Decimal(100).quantize(self.DECIMAL_PRECISION)
        )

        price_in_target_currency = price_in_source_currency.quantize(
            self.DECIMAL_PRECISION
        ) * exchange_rate.quantize(self.DECIMAL_PRECISION)

        logger.info(
            f"{authorization_id}: {organization_id=} "
            f"{linked_datasource_id=} {datasource_name=} - "
            f"{amount=} {billing_percentage=} {price_in_source_currency=} "
            f"{exchange_rate=} {price_in_target_currency=}"
        )

        line = json.dumps(
            self.get_charge_line(
                f"{linked_datasource_id}-{idx:02d}",
                datasource_id,
                organization_id,
                date(
                    self.billing_start_date.year,
                    self.billing_start_date.month,
                    min(daily_expenses.keys()),
                ),
                date(
                    self.billing_start_date.year,
                    self.billing_start_date.month,
                    max(daily_expenses.keys()),
                ),
                price_in_target_currency,
                datasource_name,
            )
        )
        # Generate charge with total monthly spending
        charges.append(f"{line}\n")

        if price_in_target_currency == Decimal("0"):
            return charges

        idx += 1

        # As we assume that expenses can be missing for some days, we recreate missing days
        # with expenses of the previous day
        daily_expenses[0] = 0
        for i in range(1, self.billing_end_date.day + 1):
            if i not in daily_expenses:
                daily_expenses[i] = daily_expenses[i - 1]
        daily_expenses = convert_expenses_to_daily(daily_expenses)

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

        refunds = self.generate_refunds(
            daily_expenses=daily_expenses,
            entitlement_id=entitlement.get("id"),
            entitlement_start_date=ent_events.get("redeemed", {}).get("at"),
            entitlement_termination_date=ent_events.get("terminated", {}).get("at"),
            trial_start_date=trial_start,
            trial_end_date=trial_end,
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

            line = json.dumps(
                self.get_charge_line(
                    f"{linked_datasource_id}-{idx:02d}",
                    datasource_id,
                    organization_id,
                    refund.start_date,
                    refund.end_date,
                    -refund_in_target_currency,
                    datasource_name,
                    description=refund.description,
                )
            )
            charges.append(f"{line}\n")
            idx += 1

            logger.info(
                f"{authorization_id}: {organization_id=} "
                f"{linked_datasource_id=} {datasource_name=} - "
                f"{amount=} {billing_percentage=} {price_in_source_currency=} "
                f"{exchange_rate=} {price_in_target_currency=}"
            )

        return charges

    def get_charge_line(
        self,
        vendor_external_id: str,
        datasource_id: str,
        organization_id: str,
        start_date: date,
        end_date: date,
        price: Decimal,
        datasource_name: str,
        description: str = "",
    ):
        return {
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
                "start": start_date.isoformat(),
                "end": end_date.isoformat(),
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

    async def is_journal_validated(self, journal_id):
        attempt = 0
        sleeps = [0.15, 0.45, 1.05, 2.25, 4.65]
        while attempt < 5:
            journal = await self.mpt_client.get_journal_by_id(journal_id)
            if journal["status"] == "Validated":
                return True
            await asyncio.sleep(sleeps[attempt])
            attempt += 1
        return False
