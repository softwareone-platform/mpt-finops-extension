from ffc.flows.error import ERR_ORDER_TYPE_NOT_SUPPORTED
from ffc.flows.order import OrderContext
from ffc.flows.steps.validation import OrderTypeIsNotSupported


def test_order_type_is_not_supported(
    mocked_next_step,
    mpt_client,
    processing_change_order,
):
    ctx = OrderContext(order=processing_change_order)
    step = OrderTypeIsNotSupported()

    step(mpt_client, ctx, mocked_next_step)

    error_msg = ERR_ORDER_TYPE_NOT_SUPPORTED.to_dict(
        order_type=processing_change_order["type"],
    )
    assert ctx.validation_succeeded is False
    assert ctx.order["error"] == error_msg
    mocked_next_step.assert_not_called()
