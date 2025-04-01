from swo.mpt.extensions.flows.pipeline import Pipeline

from ffc.flows.steps import (
    CheckDueDate,
    CompleteOrder,
    CreateSubscription,
    ResetDueDate,
    SetupDueDate,
)

purchase = Pipeline(
    SetupDueDate(),
    CheckDueDate(),
    CreateSubscription(),
    ResetDueDate(),
    CompleteOrder("purchase_order"),
)

change_order = Pipeline(
    SetupDueDate(),
    CheckDueDate(),
    ResetDueDate(),
    CompleteOrder("purchase_order"),
)

terminate = Pipeline(
    SetupDueDate(),
    CheckDueDate(),
    ResetDueDate(),
    CompleteOrder("purchase_order"),
)
