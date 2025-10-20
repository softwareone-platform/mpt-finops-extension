import asyncio
import sys
from datetime import date

from dateutil.relativedelta import relativedelta
from django.core.management.base import BaseCommand

from ffc.billing.process_billing import (
    process_billing,
)


class Command(BaseCommand):
    help = "Synchronize agreements on anniversary."

    def add_arguments(self, parser):  # pragma no cover
        parser.add_argument(
            "--dry-run",
            action="store_true",
            default=False,
            help="Test generation of billing files without making changes",
        )

        parser.add_argument(
            "--authorization",
            help="Generate billing file for given authorization",
        )
        parser.add_argument(
            "--year",
            type=int,
            default=date.today().year,
            help="Year for billing period",
        )
        parser.add_argument(
            "--month",
            type=int,
            default=(date.today() - relativedelta(months=1)).month,
            help="Year for billing period",
        )
        parser.add_argument(
            "--cutoff-day",
            type=int,
            default=5,
            help="The cutoff day to run the process for.",
        )

    def handle(self, *args, **options):
        cutoff_day = options["cutoff_day"]
        if cutoff_day not in range(1, 29):
            self.stderr.write(self.style.ERROR("cutoff-day must be between 1 and 28 (inclusive)"))
            sys.exit(1)
        asyncio.run(
            process_billing(
                options["year"],
                options["month"],
                authorization_id=options.get("authorization"),
                dry_run=options["dry_run"],
                cutoff_day=cutoff_day,
            )
        )
