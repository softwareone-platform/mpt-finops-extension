import logging
from datetime import date, timedelta

from django.conf import settings
from mpt_extension_sdk.flows.pipeline import Step
from mpt_extension_sdk.mpt_http.mpt import update_order

from ffc.flows.error import ERR_DUE_DATE_IS_REACHED
from ffc.flows.steps.utils import switch_order_to_failed
from ffc.notifications import send_mpt_notification
from ffc.parameters import get_due_date, set_due_date

logger = logging.getLogger(__name__)


class SetupDueDate(Step):
    """
    Sets Due date for processing order and sends a notification
    if it is the first attempt to process the order
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
        # sends a notification to the customer
        send_mpt_notification(client, context)

        next_step(client, context)


class CheckDueDate(Step):
    """
    Check due date, if it is expired - fail the order
    """

    def __call__(self, client, context, next_step):
        due_date = get_due_date(context.order)
        if date.today() > due_date:
            due_date_str = due_date.strftime("%Y-%m-%d")
            logging.info(
                f"Swith order {context.order['id']} to failed status. "
                f"Reason: due date is reached {due_date_str}"
            )
            switch_order_to_failed(
                client,
                context.order,
                ERR_DUE_DATE_IS_REACHED.to_dict(due_date=due_date.strftime("%Y-%m-%d")),
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
