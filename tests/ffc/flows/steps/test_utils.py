from ffc.flows.error import ERR_ORDER_TYPE_NOT_SUPPORTED
from ffc.flows.steps.utils import (
    reset_order_error,
    set_order_error,
    switch_order_to_failed,
)
from ffc.parameters import set_due_date


def test_switch_order_to_failed(
    mocker, mpt_client, processing_purchase_order, failed_purchase_order
):
    mock_fail_order = mocker.patch(
        "ffc.flows.steps.utils.fail_order",
        return_value=failed_purchase_order,
    )
    mock_send_email_notifications = mocker.patch(
        "ffc.flows.steps.utils.send_email_notification"
    )

    failed_order = switch_order_to_failed(
        mpt_client,
        processing_purchase_order,
        ERR_ORDER_TYPE_NOT_SUPPORTED.to_dict(order_type="Purchase"),
    )

    no_due_date_order = set_due_date(processing_purchase_order, None)
    assert failed_order == failed_purchase_order
    mock_fail_order.assert_called_once_with(
        mpt_client,
        processing_purchase_order["id"],
        ERR_ORDER_TYPE_NOT_SUPPORTED.to_dict(order_type="Purchase"),
        parameters=no_due_date_order["parameters"],
    )
    mock_send_email_notifications.assert_called_once_with(
        mpt_client,
        failed_purchase_order,
    )


def test_set_order_error(processing_purchase_order):
    order_msg = ERR_ORDER_TYPE_NOT_SUPPORTED.to_dict(
        order_type="Change",
    )
    updated_order = set_order_error(processing_purchase_order, order_msg)

    assert updated_order["error"] == order_msg


def test_reset_order_error(processing_purchase_order):
    order_msg = ERR_ORDER_TYPE_NOT_SUPPORTED.to_dict(
        order_type="Change",
    )
    processing_purchase_order["error"] = order_msg

    updated_order = reset_order_error(processing_purchase_order)

    assert updated_order["error"] is None
