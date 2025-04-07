from ffc.flows.validation import validate_purchase_order


def test_validate_purchase_order_valid(mpt_client, draft_purchase_valid_order):
    has_errors, _ = validate_purchase_order(mpt_client, draft_purchase_valid_order)

    assert has_errors is False


def test_validate_purchase_order_invalid(mpt_client, draft_purchase_invalid_order):
    has_errors, _ = validate_purchase_order(mpt_client, draft_purchase_invalid_order)

    assert has_errors is True
