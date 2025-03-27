from swo.mpt.extensions.flows.pipeline import Pipeline

from ffc.flows.steps import CompleteOrder, CreateSubscription

purchase = Pipeline(
    CreateSubscription(),
    CompleteOrder("purchase_order"),
)

change_order = Pipeline(
    CreateSubscription(),
    CompleteOrder("purchase_order"),
)

terminate = Pipeline(
    CompleteOrder("purchase_order"),
)
