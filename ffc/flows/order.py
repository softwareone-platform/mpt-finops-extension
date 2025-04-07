from dataclasses import dataclass, field

from swo.mpt.extensions.flows.context import Context as BaseContext

from ffc.utils import find_first

MPT_ORDER_STATUS_PROCESSING = "Processing"
MPT_ORDER_STATUS_QUERYING = "Querying"
MPT_ORDER_STATUS_COMPLETED = "Completed"

ORDER_TYPE_PURCHASE = "Purchase"


def is_purchase_order(order):
    """
    Check if the order is a real purchase order or a subscriptions transfer order.
    Args:
        source (str): The order to check.

    Returns:
        bool: True if it is a real purchase order, False otherwise.
    """
    return order["type"] == ORDER_TYPE_PURCHASE


@dataclass
class OrderContext(BaseContext):
    order: dict
    employee: dict = field(init=False, default=None)
    organization: dict = field(init=False, default=None)

    def __str__(self):
        return f"{(self.type or '-').upper()} {self.order['id']}"

    @staticmethod
    def from_order(order: dict):
        return OrderContext(order=order)

    @property
    def type(self):
        return self.order["type"]

    @property
    def product_id(self):
        return self.order["product"]["id"]


def get_subscription_by_line_and_item_id(subscriptions, item_id, line_id):
    """
    Return a subscription by line id and sku.

    Args:
        subscriptions (list): a list of subscription obects.
        vendor_external_id (str): the item SKU
        line_id (str): the id of the order line that should contain the given SKU.

    Returns:
        dict: the corresponding subscription if it is found, None otherwise.
    """
    for subscription in subscriptions:
        item = find_first(
            lambda x: x["id"] == line_id and x["item"]["id"] == item_id,
            subscription["lines"],
        )

        if item:
            return subscription
