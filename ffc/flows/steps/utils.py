from copy import deepcopy

from mpt_extension_sdk.mpt_http.mpt import fail_order

from ffc.notifications import send_email_notification
from ffc.parameters import set_due_date


def switch_order_to_failed(client, order, reason):
    """
    Marks an MPT order as failed by resetting due date and updating its status.

    Args:
        client (MPTClient): An instance of the Marketplace platform client.
        order (dict): The MPT order to be marked as failed.
        reason, reason (str): Additional notes or context related to the failure.

    Returns:
        dict: The updated order with the appropriate status and notes.
    """
    order = set_due_date(order, None)
    agreement = order["agreement"]
    # TODO: incorrect number of parameters in SDK :-( fix it
    order = fail_order(
        client, order["id"], reason, reason, parameters=order["parameters"]
    )
    order["agreement"] = agreement
    send_email_notification(client, order)
    return order


def reset_order_error(order):
    updated_order = deepcopy(order)
    updated_order["error"] = None
    return updated_order
