from ffc.flows.order import OrderContext
from ffc.flows.steps.create_subscription import CreateSubscription


def test_create_subscriptions(
    mocker,
    mocked_next_step,
    mpt_client,
    subscriptions_factory,
    processing_purchase_order,
):
    subscription = subscriptions_factory()[0]
    mocked_create_subscription = mocker.patch(
        "ffc.flows.steps.create_subscription.create_subscription",
        return_value=subscription,
    )
    ctx = OrderContext(order=processing_purchase_order)
    step = CreateSubscription()

    step(mpt_client, ctx, mocked_next_step)

    mocked_next_step.assert_called_once()
    mocked_create_subscription.assert_called_once_with(
        mpt_client,
        processing_purchase_order["id"],
        {
            "name": "Subscription for Awesome product",
            "parameters": {},
            "externalIds": {},
            "lines": [
                {
                    "id": "ALI-2119-4550-8674-5962-0001",
                },
            ],
        },
    )


def test_skip_creating_subscriptions(
    mocker,
    mocked_next_step,
    mpt_client,
    subscriptions_factory,
    processing_purchase_order,
):
    subscription = subscriptions_factory()[0]
    processing_purchase_order["subscriptions"] = [subscription]
    mocked_create_subscription = mocker.patch(
        "ffc.flows.steps.create_subscription.create_subscription",
        return_value=subscription,
    )
    ctx = OrderContext(order=processing_purchase_order)
    step = CreateSubscription()

    step(mpt_client, ctx, mocked_next_step)

    mocked_next_step.assert_called_once()
    mocked_create_subscription.assert_not_called()
