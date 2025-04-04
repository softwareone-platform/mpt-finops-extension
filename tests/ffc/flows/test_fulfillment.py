from freezegun import freeze_time

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
    mocked_send_email_notification_complete_order = mocker.patch(
        "ffc.flows.steps.order.send_email_notification",
    )
    mocked_update_agreement = mocker.patch("ffc.flows.steps.order.update_agreement")

    mocked_ffc_client = mocker.MagicMock()
    mocked_ffc_client.get_employee.return_value = ffc_employee
    mocked_ffc_client.get_organization_by_external_id.return_value = ffc_organization
    mocker.patch(
        "ffc.flows.steps.finops.get_ffc_client", return_value=mocked_ffc_client
    )

    fulfill_order(mpt_client, processing_purchase_order)

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
    mocked_send_email_notification_complete_order.assert_called_once_with(
        mpt_client,
        processing_purchase_order,
    )
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
                }
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
                },
                {
                    "displayValue": "USD",
                    "externalId": "currency",
                    "id": "PAR-7208-0459-0006",
                    "name": "Currency",
                    "phase": "Order",
                    "type": "DropDown",
                    "value": "USD",
                },
            ],
        },
    )
