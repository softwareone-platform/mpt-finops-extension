from ffc.flows.order import OrderContext
from ffc.flows.steps.complete_order import CompleteOrder


def test_complete_order(
    mocker,
    mocked_next_step,
    mpt_client,
    processing_purchase_order,
    completed_purchase_order,
    template,
):
    mocked_complete_order = mocker.patch(
        "ffc.flows.steps.complete_order.complete_order",
        return_value=completed_purchase_order,
    )
    mocker.patch(
        "ffc.flows.steps.complete_order.get_product_template_or_default",
        return_value=template,
    )
    mocked_send_email_notification = mocker.patch(
        "ffc.flows.steps.complete_order.send_email_notification",
    )

    ctx = OrderContext(order=processing_purchase_order)
    step = CompleteOrder("Complete Template")

    step(mpt_client, ctx, mocked_next_step)

    mocked_next_step.assert_called_once()
    assert ctx.order == completed_purchase_order
    mocked_complete_order.assert_called_once_with(
        mpt_client,
        processing_purchase_order["id"],
        template,
        parameters=processing_purchase_order["parameters"],
    )
    mocked_send_email_notification.assert_called_once_with(
        mpt_client, completed_purchase_order
    )
