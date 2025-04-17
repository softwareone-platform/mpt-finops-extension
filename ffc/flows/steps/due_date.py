import logging
from datetime import date, timedelta

from django.conf import settings
from mpt_extension_sdk.flows.pipeline import Step
from mpt_extension_sdk.mpt_http.mpt import update_order

from ffc.flows.steps.utils import switch_order_to_failed
from ffc.notifications import send_email_notification
from ffc.parameters import get_due_date, set_due_date

logger = logging.getLogger(__name__)


class SetupDueDate(Step):
    """
    Sets Due date for processing order and sends email
    if it is first attempt to process the order
    """

    def __call__(self, client, context, next_step):
        due_date = get_due_date(context.order)

        if due_date:
            logging.info(
                f"Due date parameter was setup before {due_date.strftime('%Y-%m-%d')}: skip",
            )
            next_step(client, context)
            return

        due_date = date.today() + timedelta(
            days=int(settings.EXTENSION_CONFIG.get("DUE_DATE_DAYS"))
        )
        context.order = set_due_date(context.order, due_date)
        update_order(
            client,
            context.order["id"],
            parameters=context.order["parameters"],
        )
        logging.info(
            f"Due date parameter was setup {due_date.strftime('%Y-%m-%d')}",
        )

        # means that's first attempt to process an order
        # send notification to the customer
        send_email_notification(client, context.order)

        next_step(client, context)


class CheckDueDate(Step):
    """
    Check due date, if it is expired - fail the order
    """

    def __call__(self, client, context, next_step):
        due_date = get_due_date(context.order)
        if date.today() > due_date:
            reason = f"Due date is reached {due_date.strftime('%Y-%m-%d')}"
            logging.info(
                f"Swith order {context.order['id']} to failed status. Reason: {reason}"
            )
            switch_order_to_failed(
                client,
                context.order,
                reason,
            )
            return

        next_step(client, context)


class ResetDueDate(Step):
    """
    In order not to move due date parameter to the next order
    through agreement parameter
    reset it to None before complete the order
    """

    def __call__(self, client, context, next_step):
        context.order = set_due_date(context.order, None)
        next_step(client, context)
