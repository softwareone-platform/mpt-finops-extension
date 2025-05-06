from datetime import date

from freezegun import freeze_time

from ffc.flows.error import ERR_DUE_DATE_IS_REACHED
from ffc.flows.order import OrderContext
from ffc.flows.steps.due_date import CheckDueDate, ResetDueDate, SetupDueDate
from ffc.parameters import get_due_date, set_due_date


@freeze_time("2025-02-01")
def test_setup_due_date(
    mocker,
    settings,
    mocked_next_step,
    mpt_client,
    first_attempt_processing_purchase_order,
):
    ctx = OrderContext(order=first_attempt_processing_purchase_order)
    step = SetupDueDate()
    settings.EXTENSION_CONFIG["DUE_DATE_DAYS"] = 10

    mocked_send_email_notification = mocker.patch(
        "ffc.flows.steps.due_date.send_email_notification"
    )
    mocked_update_order = mocker.patch("ffc.flows.steps.due_date.update_order")

    step(mpt_client, ctx, mocked_next_step)

    next_due_date = date(2025, 2, 11)
    # TODO: should be in fixtures
    order_with_due_date = set_due_date(
        first_attempt_processing_purchase_order, next_due_date
    )

    assert get_due_date(ctx.order) == next_due_date
    mocked_send_email_notification.assert_called_once_with(
        mpt_client, order_with_due_date
    )
    mocked_update_order.assert_called_once_with(
        mpt_client,
        order_with_due_date["id"],
        parameters=order_with_due_date["parameters"],
    )
    mocked_next_step.assert_called_once()


@freeze_time("2025-02-01")
def test_setup_due_date_was_setup(
    mocker,
    settings,
    mocked_next_step,
    mpt_client,
    processing_purchase_order,
):
    due_date = get_due_date(processing_purchase_order)
    ctx = OrderContext(order=processing_purchase_order)

    step = SetupDueDate()
    settings.EXTENSION_CONFIG["DUE_DATE_DAYS"] = 10

    mocked_send_email_notification = mocker.patch(
        "ffc.flows.steps.due_date.send_email_notification"
    )
    mocked_update_order = mocker.patch("ffc.flows.steps.due_date.update_order")

    step(mpt_client, ctx, mocked_next_step)

    assert get_due_date(ctx.order) == due_date
    mocked_send_email_notification.assert_not_called()
    mocked_update_order.assert_not_called()
    mocked_next_step.assert_called_once()


def test_reset_due_date(
    mocked_next_step,
    mpt_client,
    processing_purchase_order,
):
    ctx = OrderContext(order=processing_purchase_order)
    step = ResetDueDate()

    step(mpt_client, ctx, mocked_next_step)

    assert get_due_date(ctx.order) is None
    mocked_next_step.assert_called_once()


@freeze_time("2024-12-01")
def test_check_due_date(
    mocker, mocked_next_step, mpt_client, processing_purchase_order
):
    ctx = OrderContext(order=processing_purchase_order)
    step = CheckDueDate()

    mocked_switch_order_to_failed = mocker.patch(
        "ffc.flows.steps.due_date.switch_order_to_failed"
    )

    step(mpt_client, ctx, mocked_next_step)

    mocked_next_step.assert_called_once()
    mocked_switch_order_to_failed.assert_not_called()


@freeze_time("2025-02-01")
def test_check_due_date_fail_order(
    mocker, mocked_next_step, mpt_client, processing_purchase_order
):
    ctx = OrderContext(order=processing_purchase_order)
    step = CheckDueDate()

    mocked_switch_order_to_failed = mocker.patch(
        "ffc.flows.steps.due_date.switch_order_to_failed"
    )

    step(mpt_client, ctx, mocked_next_step)

    mocked_next_step.assert_not_called()
    mocked_switch_order_to_failed.assert_called_once_with(
        mpt_client,
        processing_purchase_order,
        ERR_DUE_DATE_IS_REACHED.to_dict(due_date="2025-01-01"),
    )
