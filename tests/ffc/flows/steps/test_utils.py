from ffc.flows.steps.utils import switch_order_to_failed
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
        mpt_client, processing_purchase_order, "error"
    )

    no_due_date_order = set_due_date(processing_purchase_order, None)
    assert failed_order == failed_purchase_order
    mock_fail_order.assert_called_once_with(
        mpt_client,
        processing_purchase_order["id"],
        "error",
        parameters=no_due_date_order["parameters"],
    )
    mock_send_email_notifications.assert_called_once_with(
        mpt_client,
        failed_purchase_order,
    )
