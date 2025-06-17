import asyncio
from datetime import date

from dateutil.relativedelta import relativedelta
from django.core.management.base import BaseCommand

from ffc.process_billing import (
    BillingProcess,
)


class Command(BaseCommand):
    help = "Synchronize agreements on anniversary."

    def add_arguments(self, parser):
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

    def handle(self, *args, **options):
        bp = BillingProcess(
            options["year"],
            options["month"],
            authorization_id=options.get("authorization"),
            dry_run=options["dry_run"],
        )
        asyncio.run(bp.run())
