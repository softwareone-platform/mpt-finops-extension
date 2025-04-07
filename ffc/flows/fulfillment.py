import logging
import traceback

from swo.mpt.extensions.flows.pipeline import Pipeline

from ffc.flows.error import strip_trace_id
from ffc.flows.order import (
    OrderContext,
    is_purchase_order,
)
from ffc.flows.steps import (
    CheckDueDate,
    CheckOrderParameters,
    CompleteOrder,
    CreateEmployee,
    CreateOrganization,
    CreateSubscription,
    ResetDueDate,
    SetupAgreementExternalId,
    SetupDueDate,
)
from ffc.notifications import notify_unhandled_exception_in_teams

logger = logging.getLogger(__name__)


purchase = Pipeline(
    SetupDueDate(),
    CheckDueDate(),
    CheckOrderParameters(),
    CreateEmployee(),
    CreateOrganization(),
    SetupAgreementExternalId(),
    CreateSubscription(),
    ResetDueDate(),
    CompleteOrder("purchase_order"),
)


def fulfill_order(client, order):
    """
    Fulfills an order of any type by processing the necessary actions
    based on the provided parameters.

    Args:
        client (MPTClient): An instance of the client for consuming the MPT platform API.
        order (dict): The order that needs to be processed.

    Returns:
        None
    """
    logger.info(f'Start processing {order["type"]} order {order["id"]}')
    context = OrderContext.from_order(order)
    try:
        if is_purchase_order(order):
            purchase.run(client, context)
    except Exception:
        notify_unhandled_exception_in_teams(
            "fulfillment",
            order["id"],
            strip_trace_id(traceback.format_exc()),
        )
        raise
