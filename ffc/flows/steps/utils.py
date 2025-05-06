from copy import deepcopy

from mpt_extension_sdk.mpt_http.mpt import fail_order

from ffc.notifications import send_email_notification
from ffc.parameters import set_due_date


def switch_order_to_failed(client, order, error):
    """
    Marks an MPT order as failed by resetting due date and updating its status.

    Args:
        client (MPTClient): An instance of the Marketplace platform client.
        order (dict): The MPT order to be marked as failed.
        error (dict): Additional notes or context related to the failure. {id, message}

    Returns:
        dict: The updated order with the appropriate status and notes.
    """
    order = set_due_date(order, None)
    agreement = order["agreement"]
    order = fail_order(client, order["id"], error, parameters=order["parameters"])
    order["agreement"] = agreement
    send_email_notification(client, order)
    return order


def reset_order_error(order):
    """
    Set order error message to None

    Args:
        order (dict): An MPT order dict representation

    Returns:
        dict: The update order with
    """
    return set_order_error(order, None)


def set_order_error(order, error):
    """
    Set order error message

    Args:
        order (dict): An MPT order dict representation
        error (dict): an error dict with id, message fields

    Returns:
        dict: The update order with
    """
    updated_order = deepcopy(order)
    updated_order["error"] = error
    return updated_order
