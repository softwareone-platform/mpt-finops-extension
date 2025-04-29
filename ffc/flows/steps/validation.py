from mpt_extension_sdk.flows.pipeline import Step

from ffc.flows.error import ERR_ORDER_TYPE_NOT_SUPPORTED
from ffc.flows.steps.utils import set_order_error


class OrderTypeIsNotSupported(Step):
    """
    Return constant error on validation request
    """

    def __call__(self, client, context, next_step):
        context.validation_succeeded = False
        context.order = set_order_error(
            context.order,
            ERR_ORDER_TYPE_NOT_SUPPORTED.to_dict(order_type=context.order["type"]),
        )
