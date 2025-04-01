from freezegun import freeze_time

from ffc.flows.fulfillment import fulfill_order


@freeze_time("2025-01-01")
def test_purchase_order(
    mocker,
    mpt_client,
    processing_purchase_order,
    subscriptions_factory,
    template,
):
    subscription = subscriptions_factory()[0]
    mocked_create_subscription = mocker.patch(
        "ffc.flows.steps.create_subscription.create_subscription",
        return_value=subscription,
    )
    mocker.patch(
        "ffc.flows.steps.complete_order.get_product_template_or_default",
        return_value=template,
    )
    mocked_complete_order = mocker.patch(
        "ffc.flows.steps.complete_order.complete_order",
        return_value=processing_purchase_order,
    )
    mocked_send_email_notification_complete_order = mocker.patch(
        "ffc.flows.steps.complete_order.send_email_notification",
    )

    fulfill_order(mpt_client, processing_purchase_order)

    mocked_create_subscription.assert_called_once_with(
        mpt_client,
        processing_purchase_order["id"],
        {
            "name": "Subscription for Awesome product",
            "parameters": {},
            "externalIds": {},
            "lines": [
                {"id": "ALI-2119-4550-8674-5962-0001"}
            ]
        },
    )
    mocked_send_email_notification_complete_order.assert_called_once_with(
        mpt_client,
        processing_purchase_order,
    )
    mocked_complete_order.assert_called_once_with(
        mpt_client,
        processing_purchase_order["id"],
        template,
        parameters={
            "fulfillment":
            [
                {
                    "externalId": "dueDate",
                    "id": "PAR-7208-0459-0007",
                    "name": "Due Date",
                    "phase": "Fulfillment",
                    "type": "Date",
                    "value": None
                }
            ],
            "ordering":
            [
                {
                    "displayValue": "ACME Inc",
                    "externalId": "organizationName",
                    "id": "PAR-7208-0459-0004",
                    "name": "Organization Name",
                    "phase": "Order",
                    "type": "SingleLineText",
                    "value": "ACME Inc"
                },
                {
                    "displayValue": "PL NN pl@example.com",
                    "externalId": "adminContact",
                    "id": "PAR-7208-0459-0005",
                    "name": "Administrator",
                    "phase": "Order",
                    "type": "Contact",
                    "value":
                    {
                        "email": "pl@example.com",
                        "firstName": "PL",
                        "lastName": "NN",
                        "phone": None
                    }
                },
                {
                    "displayValue": "USD",
                    "externalId": "currency",
                    "id": "PAR-7208-0459-0006",
                    "name": "Currency",
                    "phase": "Order",
                    "type": "DropDown",
                    "value": "USD"
                }
            ]
        },
    )
