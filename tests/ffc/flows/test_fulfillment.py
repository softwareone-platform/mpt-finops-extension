import pytest
from freezegun import freeze_time

from ffc.flows.error import ERR_ORDER_TYPE_NOT_SUPPORTED
from ffc.flows.fulfillment import fulfill_order


@freeze_time("2025-01-01")
def test_purchase_order(
    mocker,
    mpt_client,
    processing_purchase_order,
    subscriptions_factory,
    template,
    ffc_employee,
    ffc_organization,
):
    subscription = subscriptions_factory()[0]
    mocked_create_subscription = mocker.patch(
        "ffc.flows.steps.subscription.create_subscription",
        return_value=subscription,
    )
    mocker.patch(
        "ffc.flows.steps.order.get_product_template_or_default",
        return_value=template,
    )
    mocked_complete_order = mocker.patch(
        "ffc.flows.steps.order.complete_order",
        return_value=processing_purchase_order,
    )
    mocked_send_mpt_notification_complete_order = mocker.patch(
        "ffc.flows.steps.order.send_mpt_notification",
    )
    mocked_update_order_finops = mocker.patch("ffc.flows.steps.finops.update_order")
    mocked_update_order = mocker.patch("ffc.flows.steps.order.update_order")
    mocked_update_agreement = mocker.patch("ffc.flows.steps.order.update_agreement")

    mocked_ffc_client = mocker.MagicMock()
    mocked_ffc_client.get_employee.return_value = ffc_employee
    mocked_ffc_client.get_organizations_by_external_id.return_value = [ffc_organization]
    mocker.patch("ffc.flows.steps.finops.get_ffc_client", return_value=mocked_ffc_client)

    fulfill_order(mpt_client, processing_purchase_order)

    mocked_update_order_finops.assert_called_once()
    mocked_update_order.assert_called_once_with(
        mpt_client,
        processing_purchase_order["id"],
        template=template,
    )
    mocked_update_agreement.assert_called_once_with(
        mpt_client,
        processing_purchase_order["agreement"]["id"],
        externalIds={"vendor": ffc_organization["id"]},
    )
    mocked_create_subscription.assert_called_once_with(
        mpt_client,
        processing_purchase_order["id"],
        {
            "name": "Subscription for Awesome product",
            "parameters": {},
            "externalIds": {
                "vendor": ffc_organization["id"],
            },
            "lines": [{"id": "ALI-2119-4550-8674-5962-0001"}],
        },
    )
    mocked_send_mpt_notification_complete_order.assert_called_once()
    mocked_complete_order.assert_called_once_with(
        mpt_client,
        processing_purchase_order["id"],
        template,
        parameters={
            "fulfillment": [
                {
                    "externalId": "dueDate",
                    "id": "PAR-7208-0459-0007",
                    "name": "Due Date",
                    "phase": "Fulfillment",
                    "type": "Date",
                    "value": None,
                },
                {
                    "id": "PAR-7208-0459-0008",
                    "externalId": "isNewUser",
                    "name": "Is New User?",
                    "type": "Checkbox",
                    "phase": "Fulfillment",
                    "value": ["Yes"],
                },
                {
                    "id": "PAR-7208-0459-0009",
                    "externalId": "trialStartDate",
                    "name": "Trial Start Date",
                    "type": "Date",
                    "phase": "Fulfillment",
                    "value": "2025-01-01",
                },
                {
                    "id": "PAR-7208-0459-0010",
                    "externalId": "trialEndDate",
                    "name": "Trial Start Date",
                    "type": "Date",
                    "phase": "Fulfillment",
                    "value": "2025-01-31",
                },
                {
                    "id": "PAR-7208-0459-0011",
                    "externalId": "billedPercentage",
                    "name": "Billed Percentage",
                    "type": "SingleLineText",
                    "phase": "Fulfillment",
                    "value": "4",
                },
            ],
            "ordering": [
                {
                    "displayValue": "ACME Inc",
                    "externalId": "organizationName",
                    "id": "PAR-7208-0459-0004",
                    "name": "Organization Name",
                    "phase": "Order",
                    "type": "SingleLineText",
                    "value": "ACME Inc",
                    "error": None,
                },
                {
                    "displayValue": "PL NN pl@example.com",
                    "externalId": "adminContact",
                    "id": "PAR-7208-0459-0005",
                    "name": "Administrator",
                    "phase": "Order",
                    "type": "Contact",
                    "value": {
                        "email": "pl@example.com",
                        "firstName": "PL",
                        "lastName": "NN",
                        "phone": None,
                    },
                    "error": None,
                },
                {
                    "displayValue": "USD",
                    "externalId": "currency",
                    "id": "PAR-7208-0459-0006",
                    "name": "Currency",
                    "phase": "Order",
                    "type": "DropDown",
                    "value": "USD",
                    "error": None,
                },
            ],
        },
    )


@freeze_time("2025-01-01")
def test_terminate_order(
    mocker,
    mpt_client,
    processing_termination_order,
    template,
    ffc_organization,
):
    mocker.patch(
        "ffc.flows.steps.order.get_product_template_or_default",
        return_value=template,
    )
    mocked_complete_order = mocker.patch(
        "ffc.flows.steps.order.complete_order",
        return_value=processing_termination_order,
    )
    mocked_send_mpt_notification_complete_order = mocker.patch(
        "ffc.flows.steps.order.send_mpt_notification",
    )
    mocked_update_order = mocker.patch("ffc.flows.steps.order.update_order")

    mocked_ffc_client = mocker.MagicMock()
    mocked_ffc_client.get_organizations_by_external_id.return_value = [ffc_organization]
    mocker.patch("ffc.flows.steps.finops.get_ffc_client", return_value=mocked_ffc_client)

    fulfill_order(mpt_client, processing_termination_order)

    mocked_update_order.assert_called_once_with(
        mpt_client,
        processing_termination_order["id"],
        template=template,
    )

    mocked_send_mpt_notification_complete_order.assert_called_once()
    mocked_complete_order.assert_called_once_with(
        mpt_client,
        processing_termination_order["id"],
        template,
        parameters={
            "fulfillment": [
                {
                    "externalId": "dueDate",
                    "id": "PAR-7208-0459-0007",
                    "name": "Due Date",
                    "phase": "Fulfillment",
                    "type": "Date",
                    "value": None,
                },
                {
                    "id": "PAR-7208-0459-0008",
                    "externalId": "isNewUser",
                    "name": "Is New User?",
                    "type": "Checkbox",
                    "phase": "Fulfillment",
                },
                {
                    "id": "PAR-7208-0459-0009",
                    "externalId": "trialStartDate",
                    "name": "Trial Start Date",
                    "type": "Date",
                    "phase": "Fulfillment",
                    "value": "2025-01-01",
                },
                {
                    "id": "PAR-7208-0459-0010",
                    "externalId": "trialEndDate",
                    "name": "Trial Start Date",
                    "type": "Date",
                    "phase": "Fulfillment",
                    "value": "2025-01-31",
                },
                {
                    "id": "PAR-7208-0459-0011",
                    "externalId": "billedPercentage",
                    "name": "Billed Percentage",
                    "type": "SingleLineText",
                    "phase": "Fulfillment",
                    "value": "4",
                },
            ],
            "ordering": [],
        },
    )


@pytest.mark.parametrize(
    "order_to_fail",
    [
        "processing_change_order",
        "processing_configuration_order",
    ],
)
def test_other_order_types(
    request,
    mocker,
    mpt_client,
    order_to_fail,
):
    order_to_fail = request.getfixturevalue(order_to_fail)
    mocked_switch_order_to_failed = mocker.patch("ffc.flows.steps.order.switch_order_to_failed")

    fulfill_order(mpt_client, order_to_fail)

    mocked_switch_order_to_failed.assert_called_once_with(
        mpt_client,
        order_to_fail,
        ERR_ORDER_TYPE_NOT_SUPPORTED.to_dict(order_type=order_to_fail["type"]),
    )
