from swo.mpt.client.mpt import fail_order

from ffc.notifications import send_email_notification
from ffc.parameters import set_due_date


def switch_order_to_failed(client, order, status_notes):
    """
    Marks an MPT order as failed by resetting due date and updating its status.

    Args:
        client (MPTClient): An instance of the Marketplace platform client.
        order (dict): The MPT order to be marked as failed.
        status_notes (str): Additional notes or context related to the failure.

    Returns:
        dict: The updated order with the appropriate status and notes.
    """
    order = set_due_date(order, None)
    agreement = order["agreement"]
    order = fail_order(
        client, order["id"], status_notes, parameters=order["parameters"]
    )
    order["agreement"] = agreement
    send_email_notification(client, order)
    return order
