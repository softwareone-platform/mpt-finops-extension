import logging
import traceback

from swo.mpt.extensions.flows.pipeline import Pipeline

from ffc.flows.error import strip_trace_id
from ffc.flows.order import OrderContext, is_purchase_order
from ffc.flows.steps.order import CheckOrderParameters
from ffc.notifications import notify_unhandled_exception_in_teams

logger = logging.getLogger(__name__)


def validate_order(client, order):
    """
    Performs the validation of a draft order.

    Args:
        mpt_client (MPTClient): The client used to consume the MPT API.
        order (dict): The order to validate

    Returns:
        dict: The validated order.
    """
    try:
        has_errors = False

        if is_purchase_order(order):
            has_errors, order = validate_purchase_order(client, order)

        logger.info(
            f"Validation of order {order['id']} succeeded "
            f"with{'out' if not has_errors else ''} errors"
        )
        return order
    except Exception:
        notify_unhandled_exception_in_teams(
            "validation",
            order["id"],
            strip_trace_id(traceback.format_exc()),
        )
        raise


def validate_purchase_order(client, order):
    pipeline = Pipeline(
        CheckOrderParameters(),
    )
    context = OrderContext(order=order)
    pipeline.run(client, context)
    return not context.validation_succeeded, context.order
