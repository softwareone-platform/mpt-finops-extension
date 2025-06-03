import logging
import traceback

from mpt_extension_sdk.flows.pipeline import Pipeline

from ffc.flows.error import ERR_ORDER_TYPE_NOT_SUPPORTED, strip_trace_id
from ffc.flows.order import (
    PURCHASE_TEMPLATE_NAME,
    TERMINATE_TEMPLATE_NAME,
    OrderContext,
    is_purchase_order,
    is_terminate_order,
)
from ffc.flows.steps import (
    CheckDueDate,
    CheckOrderParameters,
    CompleteOrder,
    CompletePurchaseOrder,
    CreateEmployee,
    CreateOrganization,
    CreateSubscription,
    DeleteOrganization,
    FailOrder,
    QueryIfInvalid,
    ResetDueDate,
    ResetOrderErrors,
    SetupAgreementExternalId,
    SetupDueDate,
    SetupFulfillmentParameters,
    StartOrderProcessing,
)
from ffc.notifications import notify_unhandled_exception_in_teams

logger = logging.getLogger(__name__)


purchase = Pipeline(
    ResetOrderErrors(),
    SetupDueDate(),
    CheckDueDate(),
    CheckOrderParameters(),
    QueryIfInvalid(),
    SetupFulfillmentParameters(),
    StartOrderProcessing(PURCHASE_TEMPLATE_NAME),
    CreateEmployee(),
    CreateOrganization(),
    SetupAgreementExternalId(),
    CreateSubscription(),
    ResetDueDate(),
    CompletePurchaseOrder(PURCHASE_TEMPLATE_NAME),
)

terminate = Pipeline(
    ResetOrderErrors(),
    SetupDueDate(),
    CheckDueDate(),
    StartOrderProcessing(TERMINATE_TEMPLATE_NAME),
    DeleteOrganization(),
    ResetDueDate(),
    CompleteOrder(TERMINATE_TEMPLATE_NAME),
)

fail = Pipeline(
    FailOrder(ERR_ORDER_TYPE_NOT_SUPPORTED),
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
        elif is_terminate_order(order):
            terminate.run(client, context)
        else:
            fail.run(client, context)

    except Exception:  # pragma: no cover
        # should be covered by SDK tests
        notify_unhandled_exception_in_teams(
            "fulfillment",
            order["id"],
            strip_trace_id(traceback.format_exc()),
        )
        raise
