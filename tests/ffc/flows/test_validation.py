import pytest

from ffc.flows.error import ERR_ORDER_TYPE_NOT_SUPPORTED
from ffc.flows.validation import (
    validate_order,
    validate_other_orders,
    validate_purchase_order,
)


def test_validate_purchase(
    mpt_client,
    processing_purchase_order,
):
    has_errors, order = validate_purchase_order(
        mpt_client,
        processing_purchase_order,
    )

    assert has_errors is False
    assert order["error"] is None


@pytest.mark.parametrize(
    "order",
    [
        "processing_change_order",
        "processing_termination_order",
        "processing_configuration_order",
    ],
)
def test_validate_other_orders(
    request,
    mpt_client,
    order,
):
    order = request.getfixturevalue(order)

    has_errors, order = validate_other_orders(mpt_client, order)

    err_msg = ERR_ORDER_TYPE_NOT_SUPPORTED.to_dict(order_type=order["type"])
    assert has_errors is True
    assert order["error"] == err_msg


def test_validate_order_purchase(
    mpt_client,
    processing_purchase_order,
):
    order = validate_order(mpt_client, processing_purchase_order)

    assert order["error"] is None


@pytest.mark.parametrize(
    "order",
    [
        "processing_change_order",
        "processing_termination_order",
        "processing_configuration_order",
    ],
)
def test_validation_order_other(
    request,
    mpt_client,
    order,
):
    order = request.getfixturevalue(order)

    order = validate_order(mpt_client, order)

    assert order["error"] is not None
