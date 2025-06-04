from datetime import date

from ffc.parameters import (
    PARAM_DUE_DATE,
    PARAM_IS_NEW_USER,
    get_due_date,
    get_fulfillment_parameter,
    get_ordering_parameter,
    get_parameter,
    set_due_date,
    set_is_new_user,
    set_ordering_parameter_error,
)


def test_get_parameter(processing_purchase_order):
    parameter = get_parameter(
        "fulfillment",
        processing_purchase_order,
        PARAM_DUE_DATE,
    )

    assert parameter == {
        "id": "PAR-7208-0459-0007",
        "externalId": PARAM_DUE_DATE,
        "name": "Due Date",
        "type": "Date",
        "phase": "Fulfillment",
        "value": "2025-01-01",
    }


def test_get_parameter_does_not_exist(processing_purchase_order):
    assert get_parameter("fulfillment", processing_purchase_order, "unknownParameter") == {}


def test_set_ordering_parameter_error(processing_purchase_order):
    order_with_error = set_ordering_parameter_error(
        processing_purchase_order,
        "organizationName",
        "Error in your parameter",
    )

    due_date_param = get_ordering_parameter(order_with_error, "organizationName")
    assert due_date_param == {
        "id": "PAR-7208-0459-0004",
        "externalId": "organizationName",
        "name": "Organization Name",
        "type": "SingleLineText",
        "phase": "Order",
        "displayValue": "ACME Inc",
        "value": "ACME Inc",
        "error": "Error in your parameter",
        "constraints": {
            "hidden": False,
            "required": True,
        },
    }


def test_get_due_date(processing_purchase_order):
    due_date = get_due_date(processing_purchase_order)

    assert due_date == date(2025, 1, 1)


def test_get_due_date_empty(first_attempt_processing_purchase_order):
    due_date = get_due_date(first_attempt_processing_purchase_order)

    assert due_date is None


def test_set_due_date(processing_purchase_order):
    new_due_date = date(2025, 1, 2)
    updated_order = set_due_date(processing_purchase_order, new_due_date)

    assert get_due_date(updated_order) == new_due_date


def test_set_is_new_user(processing_purchase_order):
    updated_order = set_is_new_user(processing_purchase_order, True)

    is_new_user = get_fulfillment_parameter(updated_order, PARAM_IS_NEW_USER)
    assert is_new_user["value"] == ["Yes"]
