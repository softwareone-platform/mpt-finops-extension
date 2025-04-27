from ffc.flows.order import OrderContext
from ffc.flows.steps.order import (
    CheckOrderParameters,
    CompleteOrder,
    FailOrder,
    QueryIfInvalid,
    ResetOrderErrors,
    SetupAgreementExternalId,
    StartOrderProcessing,
)
from ffc.parameters import PARAM_PHASE_ORDERING


def test_complete_order(
    mocker,
    mocked_next_step,
    mpt_client,
    processing_purchase_order,
    completed_purchase_order,
    template,
):
    mocked_complete_order = mocker.patch(
        "ffc.flows.steps.order.complete_order",
        return_value=completed_purchase_order,
    )
    mocker.patch(
        "ffc.flows.steps.order.get_product_template_or_default",
        return_value=template,
    )
    mocked_send_email_notification = mocker.patch(
        "ffc.flows.steps.order.send_email_notification",
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


def test_check_order_parameters_passed(
    mocked_next_step,
    mpt_client,
    processing_purchase_order,
):
    ctx = OrderContext(order=processing_purchase_order)
    step = CheckOrderParameters()

    step(mpt_client, ctx, mocked_next_step)

    mocked_next_step.assert_called_once()
    assert ctx.validation_succeeded is True


def test_check_order_parameters_invalid(
    mocked_next_step,
    mpt_client,
    processing_purchase_order,
):
    processing_purchase_order["parameters"]["ordering"][0]["value"] = None

    ctx = OrderContext(order=processing_purchase_order)
    step = CheckOrderParameters()

    step(mpt_client, ctx, mocked_next_step)

    mocked_next_step.assert_called_once()
    assert ctx.validation_succeeded is False


def test_query_if_invalid(
    mocker,
    mocked_next_step,
    mpt_client,
    processing_purchase_order,
    querying_purchase_order,
    template,
):
    processing_purchase_order["parameters"]["ordering"][0]["value"] = None
    mocked_query_order = mocker.patch(
        "ffc.flows.steps.order.query_order",
        return_value=querying_purchase_order,
    )
    mocker.patch(
        "ffc.flows.steps.order.get_product_template_or_default",
        return_value=template,
    )
    mocked_send_email_notification = mocker.patch(
        "ffc.flows.steps.order.send_email_notification",
    )

    ctx = OrderContext(
        order=processing_purchase_order,
        validation_succeeded=False,
    )
    step = QueryIfInvalid()

    step(mpt_client, ctx, mocked_next_step)

    mocked_next_step.assert_not_called()
    mocked_query_order.assert_called_once_with(
        mpt_client,
        processing_purchase_order["id"],
        template=template,
    )
    mocked_send_email_notification.assert_called_once_with(
        mpt_client,
        querying_purchase_order,
    )


def test_do_not_query_if_valid(
    mocker,
    mocked_next_step,
    mpt_client,
    processing_purchase_order,
    querying_purchase_order,
    template,
):
    processing_purchase_order["parameters"]["ordering"][0]["value"] = None
    mocked_query_order = mocker.patch(
        "ffc.flows.steps.order.query_order",
        return_value=querying_purchase_order,
    )
    mocker.patch(
        "ffc.flows.steps.order.get_product_template_or_default",
        return_value=template,
    )
    mocked_send_email_notification = mocker.patch(
        "ffc.flows.steps.order.send_email_notification",
    )

    ctx = OrderContext(
        order=processing_purchase_order,
        validation_succeeded=True,
    )
    step = QueryIfInvalid()

    step(mpt_client, ctx, mocked_next_step)

    mocked_next_step.assert_called_once()
    mocked_query_order.assert_not_called()
    mocked_send_email_notification.assert_not_called()


def test_setup_agreement_external_id(
    mocker,
    mocked_next_step,
    mpt_client,
    processing_purchase_order,
    ffc_organization,
):
    mocked_update_agreement = mocker.patch("ffc.flows.steps.order.update_agreement")

    ctx = OrderContext(order=processing_purchase_order)
    ctx.organization = ffc_organization
    step = SetupAgreementExternalId()

    step(mpt_client, ctx, mocked_next_step)

    mocked_next_step.assert_called_once()
    mocked_update_agreement.assert_called_once_with(
        mpt_client,
        processing_purchase_order["agreement"]["id"],
        externalIds={"vendor": ffc_organization["id"]},
    )


def test_reset_order_error(
    mocker,
    mocked_next_step,
    mpt_client,
    processing_purchase_order,
):
    ctx = OrderContext(order=processing_purchase_order)
    step = ResetOrderErrors()

    step(mpt_client, ctx, mocked_next_step)

    assert ctx.order["error"] is None
    assert all(
        (
            param["error"] is None
            for param in ctx.order["parameters"][PARAM_PHASE_ORDERING]
        ),
    )


def test_start_order_processing_same_template(
    mocker,
    mocked_next_step,
    mpt_client,
    processing_purchase_order,
    template,
):
    processing_purchase_order["template"] = template
    mocker.patch(
        "ffc.flows.steps.order.get_product_template_or_default",
        return_value=template,
    )
    mocked_update_order = mocker.patch("ffc.flows.steps.order.update_order")
    mocked_send_email_notification = mocker.patch(
        "ffc.flows.steps.order.send_email_notification"
    )
    ctx = OrderContext(order=processing_purchase_order)
    step = StartOrderProcessing("Purchase")

    step(mpt_client, ctx, mocked_next_step)

    mocked_next_step.assert_called_once()
    mocked_update_order.assert_not_called()
    mocked_send_email_notification.assert_not_called()


def test_start_order_processing(
    mocker,
    mocked_next_step,
    mpt_client,
    processing_purchase_order,
    template,
):
    mocker.patch(
        "ffc.flows.steps.order.get_product_template_or_default",
        return_value=template,
    )
    mocked_update_order = mocker.patch("ffc.flows.steps.order.update_order")
    mocked_send_email_notification = mocker.patch(
        "ffc.flows.steps.order.send_email_notification"
    )
    ctx = OrderContext(order=processing_purchase_order)
    step = StartOrderProcessing("Purchase")

    step(mpt_client, ctx, mocked_next_step)

    mocked_next_step.assert_called_once()
    mocked_update_order.assert_called_once_with(
        mpt_client,
        processing_purchase_order["id"],
        template=template,
    )
    mocked_send_email_notification.assert_not_called()


def test_start_order_processing_send_notification(
    mocker,
    mocked_next_step,
    mpt_client,
    first_attempt_processing_purchase_order,
    template,
):
    first_attempt_processing_purchase_order["template"] = template
    mocker.patch(
        "ffc.flows.steps.order.get_product_template_or_default",
        return_value=template,
    )
    mocked_update_order = mocker.patch("ffc.flows.steps.order.update_order")
    mocked_send_email_notification = mocker.patch(
        "ffc.flows.steps.order.send_email_notification"
    )
    ctx = OrderContext(order=first_attempt_processing_purchase_order)
    step = StartOrderProcessing("Purchase")

    step(mpt_client, ctx, mocked_next_step)

    mocked_next_step.assert_called_once()
    mocked_update_order.assert_not_called()
    mocked_send_email_notification.assert_called_once_with(
        mpt_client,
        first_attempt_processing_purchase_order,
    )


def test_fail_order(
    mocker,
    mocked_next_step,
    mpt_client,
    processing_purchase_order,
):
    mocked_switch_order_to_failed = mocker.patch(
        "ffc.flows.steps.order.switch_order_to_failed"
    )
    ctx = OrderContext(order=processing_purchase_order)
    step = FailOrder("reason")

    step(mpt_client, ctx, mocked_next_step)

    mocked_next_step.assert_not_called()
    mocked_switch_order_to_failed.assert_called_once_with(
        mpt_client,
        processing_purchase_order,
        "reason",
    )
