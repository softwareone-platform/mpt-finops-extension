import json
import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from dateutil.rrule import DAILY, rrule
from django.conf import settings

from ffc.billing.classes import Refund
from ffc.parameters import get_billed_percentage, get_trial_end_date, get_trial_start_date

logger = logging.getLogger(__name__)

def get_trial_data(agreement: dict[str, Any] | None = None)-> tuple[Any | None, Any | None, Decimal]:
    trial_start = None
    trial_end = None
    billing_percentage = Decimal(settings.EXTENSION_CONFIG["DEFAULT_BILLED_PERCENTAGE"])
    if agreement:
        trial_start = get_trial_start_date(agreement)
        trial_end = get_trial_end_date(agreement)
        billing_percentage = Decimal(
            get_billed_percentage(agreement)
            or settings.EXTENSION_CONFIG["DEFAULT_BILLED_PERCENTAGE"]
        )

    return trial_start, trial_end, billing_percentage


def generate_charge_line(
        vendor_external_id: str,
        datasource_id: str,
        organization_id: str,
        start_date: date,
        end_date: date,
        price: Decimal,
        datasource_name: str,
        decimal_precision: Decimal,
        description: str = "",
    ):
        return json.dumps( {
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
                "unitPP": str(price.quantize(decimal_precision)),
                "PPx1": str(price.quantize(decimal_precision)),
            },
            "quantity": 1,
            "description": {
                "value1": datasource_name,
                "value2": description,
            },
            "segment": "COM",
        })

def calculate_entitlement_refund_lines(daily_expenses: dict[int, Decimal],
        entitlement_id: str | None,
        entitlement_start_date: str | None,
        entitlement_termination_date: str | None,
        trial_start_date: date | None,
        trial_end_date: date | None,
        billing_start_date: datetime | None,
        billing_end_date: datetime | None,
        billing_percentage: Decimal,
        exchange_rate: Decimal,
        decimal_precision: Decimal,
        charges: list,
        organization_id: str,
        linked_datasource_id: str,
        datasource_id: str,
        datasource_name: str,
):
    idx = 2
    refunds = generate_refunds(
        daily_expenses=daily_expenses,
        entitlement_id=entitlement_id,
        entitlement_start_date=entitlement_start_date,
        entitlement_termination_date=entitlement_termination_date,
        trial_start_date=trial_start_date,
        trial_end_date=trial_end_date,
        billing_start_date=billing_start_date,
        billing_end_date=billing_end_date,
    )
    for refund in refunds:
        expenses = Decimal(refund.amount)
        refund_in_source_currency = (
                expenses.quantize(decimal_precision)
                * billing_percentage.quantize(decimal_precision)
                / Decimal(100).quantize(decimal_precision)
        )
        refund_in_target_currency = refund_in_source_currency * exchange_rate.quantize(
            decimal_precision
        )
        add_line_to_monthly_charge(
            vendor_external_id=f"{linked_datasource_id}-{idx:02d}",
            datasource_id=datasource_id,
            organization_id=organization_id,
            start_date=refund.start_date,
            end_date=refund.end_date,
            price=-refund_in_target_currency,
            datasource_name=datasource_name,
            decimal_precision=decimal_precision,
            description=refund.description,
            charges=charges,

        )
        idx += 1
        # logger.info(
        #     f"{authorization_id}: {organization_id=} "
        #     f"{linked_datasource_id=} {datasource_name=} - "
        #     f"{amount=} {billing_percentage=} {price_in_source_currency=} "
        #     f"{exchange_rate=} {price_in_target_currency=}"
        # )



def generate_refunds(
        daily_expenses: dict[int, Decimal],
        entitlement_id: str | None,
        entitlement_start_date: str | None,
        entitlement_termination_date: str | None,
        trial_start_date: date | None,
        trial_end_date: date | None,
        billing_start_date: datetime | None,
        billing_end_date: datetime | None,
    ) -> list[Refund]:
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
            trial_refund_from = max(trial_start_date, billing_start_date)
            trial_refund_to = min(trial_end_date, billing_end_date)
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
                entitlement_termination = billing_end_date
            entitlement_days = {
                dt.date().day
                for dt in rrule(
                    DAILY,
                    dtstart=max(
                        datetime.fromisoformat(entitlement_start_date), billing_start_date
                    ),
                    until=min(
                        entitlement_termination,
                        billing_end_date,
                    ),
                )
                if dt.date().day not in trial_days
            }

        if trial_days:
            trial_amount =  sum(daily_expenses[d] for d in trial_days)

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
                            billing_start_date.year,
                            billing_start_date.month,
                            r_start,
                        ),
                        date(
                            billing_start_date.year,
                            billing_start_date.month,
                            r_end,
                        ),
                        f"Refund due to active entitlement {entitlement_id}",
                    )
                )

        return refund_lines


def add_line_to_monthly_charge(
        vendor_external_id: str,
        datasource_id: str,
        organization_id: str,
        start_date: date,
        end_date: date,
        price: Decimal,
        datasource_name: str,
        decimal_precision: Decimal,
        description: str = "",
        charges: list = None,

):
    if charges is None:
        charges = []
    line = generate_charge_line(
        vendor_external_id=vendor_external_id,
        datasource_id=datasource_id,
        organization_id=organization_id,
        start_date=start_date,
        end_date=end_date,
        price=price,
        datasource_name=datasource_name,
        decimal_precision=decimal_precision,
        description=description,
    )
    charges.append(f"{line}\n")
    return charges
