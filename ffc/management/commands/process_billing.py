import asyncio
import sys
from datetime import date

from dateutil.relativedelta import relativedelta
from django.core.management.base import BaseCommand

from ffc.billing.process_billing import (
    process_billing,
)


class Command(BaseCommand):
    help = "Generate billing files for a given period."

    def add_arguments(self, parser):  # pragma no cover
        previous_month = date.today() - relativedelta(months=1)
        parser.add_argument(
            "--dry-run",
            action="store_true",
            default=False,
            help="Test generation of billing files without making changes.",
        )

        parser.add_argument(
            "--authorization",
            help="Generate billing file for given authorization.",
        )
        parser.add_argument(
            "--year",
            type=int,
            default=previous_month.year,
            help=f"Year for billing period. Default to {previous_month.year}",
        )
        parser.add_argument(
            "--month",
            type=int,
            default=previous_month.month,
            help=f"Month for billing period. Default to {previous_month.month}.",
        )
        parser.add_argument(
            "--cutoff-day",
            type=int,
            default=5,
            help="The cutoff day to run the process for. Default is the 5th",
        )

    def handle(self, *args, **options):
        cutoff_day = options["cutoff_day"]
        billing_month = options["month"]
        billing_year = options["year"]
        today = date.today()

        if not (1 <= cutoff_day <= 28):
            self.stderr.write(
                self.style.ERROR("The cutoff-day must be between 1 and 28 (inclusive)")
            )
            sys.exit(1)

        if not (1 <= billing_month <= 12):
            self.stderr.write(
                self.style.ERROR("The billing month must be between 1 and 12 (inclusive)")
            )
            sys.exit(1)
        if (billing_year, billing_month) > (today.year, today.month):
            self.stderr.write(self.style.ERROR("The billing period cannot be in the future"))
            sys.exit(1)
        asyncio.run(
            process_billing(
                billing_year,
                billing_month,
                authorization_id=options.get("authorization"),
                dry_run=options["dry_run"],
                cutoff_day=cutoff_day,
            )
        )
