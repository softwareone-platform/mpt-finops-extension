import copy
from datetime import UTC, datetime

import jwt
import pytest
import responses
from swo.mpt.extensions.runtime.djapp.conf import get_for_product


@pytest.fixture()
def requests_mocker():
    """
    Allow mocking of http calls made with requests.
    """
    with responses.RequestsMock() as rsps:
        yield rsps


@pytest.fixture()
def order_parameters_factory():
    def _order_parameters():
        return [
            {
                "id": "PAR-7208-0459-0004",
                "externalId": "organizationName",
                "name": "Organization Name",
                "type": "SingleLineText",
                "phase": "Order",
                "displayValue": "ACME Inc",
                "value": "ACME Inc",
            },
            {
                "id": "PAR-7208-0459-0005",
                "externalId": "adminContact",
                "name": "Administrator",
                "type": "Contact",
                "phase": "Order",
                "displayValue": "PL NN pl@example.com",
                "value": {
                    "firstName": "PL",
                    "lastName": "NN",
                    "email": "pl@example.com",
                    "phone": None,
                },
            },
            {
                "id": "PAR-7208-0459-0006",
                "externalId": "currency",
                "name": "Currency",
                "type": "DropDown",
                "phase": "Order",
                "displayValue": "USD",
                "value": "USD",
            },
        ]

    return _order_parameters


@pytest.fixture()
def fulfillment_parameters_factory():
    def _fulfillment_parameters():
        return [
            {
                "id": "PAR-7208-0459-0007",
                "externalId": "dueDate",
                "name": "Due Date",
                "type": "Date",
                "phase": "Fulfillment",
                "value": "2025-01-01",
            }
        ]

    return _fulfillment_parameters


@pytest.fixture()
def items_factory():
    def _items(
        item_id=1,
        name="Awesome product",
        external_vendor_id="FINOPS-ITEM-00001",
    ):
        return [
            {
                "id": f"ITM-1234-1234-1234-{item_id:04d}",
                "name": name,
                "externalIds": {
                    "vendor": external_vendor_id,
                },
            },
        ]

    return _items


@pytest.fixture()
def lines_factory(agreement):
    agreement_id = agreement["id"].split("-", 1)[1]

    def _items(
        line_id=1,
        item_id=1,
        name="Awesome product",
        old_quantity=0,
        quantity=170,
        external_vendor_id="FINOPS-ITEM-00001",
        unit_purchase_price=1234.55,
    ):
        line = {
            "item": {
                "id": f"ITM-1234-1234-1234-{item_id:04d}",
                "name": name,
                "externalIds": {
                    "vendor": external_vendor_id,
                },
            },
            "oldQuantity": old_quantity,
            "quantity": quantity,
            "price": {
                "unitPP": unit_purchase_price,
            },
        }
        if line_id:
            line["id"] = f"ALI-{agreement_id}-{line_id:04d}"
        return [line]

    return _items


@pytest.fixture()
def subscriptions_factory(lines_factory):
    def _subscriptions(
        subscription_id="SUB-1000-2000-3000",
        product_name="Awesome product",
        vendor_id="123-456-789",
        start_date=None,
        commitment_date=None,
        lines=None,
    ):
        start_date = (
            start_date.isoformat() if start_date else datetime.now(UTC).isoformat()
        )
        lines = lines_factory() if lines is None else lines
        return [
            {
                "id": subscription_id,
                "name": f"Subscription for {product_name}",
                "parameters": {"fulfillment": [{}]},
                "externalIds": {
                    "vendor": vendor_id,
                },
                "lines": lines,
                "startDate": start_date,
                "commitmentDate": commitment_date,
            }
        ]

    return _subscriptions


@pytest.fixture()
def agreement_factory(buyer, order_parameters_factory, fulfillment_parameters_factory):
    def _agreement(
        licensee_name="My beautiful licensee",
        licensee_address=None,
        licensee_contact=None,
        use_buyer_address=False,
        subscriptions=None,
        fulfillment_parameters=None,
        ordering_parameters=None,
        lines=None,
    ):
        if not subscriptions:
            subscriptions = [
                {
                    "id": "SUB-1000-2000-3000",
                    "status": "Active",
                    "item": {
                        "id": "ITM-0000-0001-0001",
                    },
                },
                {
                    "id": "SUB-1234-5678",
                    "status": "Terminated",
                    "item": {
                        "id": "ITM-0000-0001-0002",
                    },
                },
            ]

        licensee = {
            "name": licensee_name,
            "address": licensee_address,
            "useBuyerAddress": use_buyer_address,
        }
        if licensee_contact:
            licensee["contact"] = licensee_contact

        return {
            "id": "AGR-2119-4550-8674-5962",
            "href": "/commerce/agreements/AGR-2119-4550-8674-5962",
            "icon": None,
            "name": "Product Name 1",
            "audit": {
                "created": {
                    "at": "2023-12-14T18:02:16.9359",
                    "by": {"id": "USR-0000-0001"},
                },
                "updated": None,
            },
            "listing": {
                "id": "LST-9401-9279",
                "href": "/listing/LST-9401-9279",
                "priceList": {
                    "id": "PRC-9457-4272-3691",
                    "href": "/v1/price-lists/PRC-9457-4272-3691",
                    "currency": "USD",
                },
            },
            "licensee": licensee,
            "buyer": buyer,
            "seller": {
                "id": "SEL-9121-8944",
                "href": "/accounts/sellers/SEL-9121-8944",
                "name": "Software LN",
                "icon": "/static/SEL-9121-8944/icon.png",
                "address": {
                    "country": "US",
                },
            },
            "client": {
                "id": "ACC-9121-8944",
                "href": "/accounts/sellers/ACC-9121-8944",
                "name": "Software LN",
                "icon": "/static/ACC-9121-8944/icon.png",
            },
            "product": {
                "id": "PRD-1111-1111",
            },
            "authorization": {"id": "AUT-1234-5678"},
            "lines": lines or [],
            "subscriptions": subscriptions,
            "parameters": {
                "ordering": ordering_parameters or order_parameters_factory(),
                "fulfillment": fulfillment_parameters
                or fulfillment_parameters_factory(),
            },
        }

    return _agreement


@pytest.fixture()
def licensee(buyer):
    return {
        "id": "LCE-1111-2222-3333",
        "name": "FF Buyer good enough",
        "useBuyerAddress": True,
        "address": buyer["address"],
        "contact": buyer["contact"],
        "buyer": buyer,
        "account": {
            "id": "ACC-1234-1234",
            "name": "Client Account",
        },
    }


@pytest.fixture()
def listing(buyer):
    return {
        "id": "LST-9401-9279",
        "href": "/listing/LST-9401-9279",
        "priceList": {
            "id": "PRC-9457-4272-3691",
            "href": "/v1/price-lists/PRC-9457-4272-3691",
            "currency": "USD",
        },
        "product": {
            "id": "PRD-1234-1234",
            "name": "Product Name",
        },
        "vendor": {
            "id": "ACC-1234-vendor-id",
            "name": "Vendor Name",
        },
    }


@pytest.fixture()
def buyer():
    return {
        "id": "BUY-3731-7971",
        "href": "/accounts/buyers/BUY-3731-7971",
        "name": "A buyer",
        "icon": "/static/BUY-3731-7971/icon.png",
        "address": {
            "country": "US",
            "state": "CA",
            "city": "San Jose",
            "addressLine1": "3601 Lyon St",
            "addressLine2": "",
            "postCode": "94123",
        },
        "contact": {
            "firstName": "Cic",
            "lastName": "Faraone",
            "email": "francesco.faraone@softwareone.com",
            "phone": {
                "prefix": "+1",
                "number": "4082954078",
            },
        },
    }


@pytest.fixture()
def seller():
    return {
        "id": "SEL-9121-8944",
        "href": "/accounts/sellers/SEL-9121-8944",
        "name": "SWO US",
        "icon": "/static/SEL-9121-8944/icon.png",
        "address": {
            "country": "US",
            "region": "CA",
            "city": "San Jose",
            "addressLine1": "3601 Lyon St",
            "addressLine2": "",
            "postCode": "94123",
        },
        "contact": {
            "firstName": "Francesco",
            "lastName": "Faraone",
            "email": "francesco.faraone@softwareone.com",
            "phone": {
                "prefix": "+1",
                "number": "4082954078",
            },
        },
    }


@pytest.fixture()
def template():
    return {
        "id": "TPL-1234-1234-4321",
        "name": "Default Template",
    }


@pytest.fixture()
def agreement(buyer, licensee, listing):
    return {
        "id": "AGR-2119-4550-8674-5962",
        "href": "/commerce/agreements/AGR-2119-4550-8674-5962",
        "icon": None,
        "name": "Product Name 1",
        "audit": {
            "created": {
                "at": "2023-12-14T18:02:16.9359",
                "by": {"id": "USR-0000-0001"},
            },
            "updated": None,
        },
        "subscriptions": [
            {
                "id": "SUB-1000-2000-3000",
                "status": "Active",
                "lines": [
                    {
                        "id": "ALI-0010",
                        "item": {
                            "id": "ITM-1234-1234-1234-0010",
                            "name": "Item 0010",
                            "externalIds": {
                                "vendor": "external-id1",
                            },
                        },
                        "quantity": 10,
                    }
                ],
            },
            {
                "id": "SUB-1234-5678",
                "status": "Terminated",
                "lines": [
                    {
                        "id": "ALI-0011",
                        "item": {
                            "id": "ITM-1234-1234-1234-0011",
                            "name": "Item 0011",
                            "externalIds": {
                                "vendor": "external-id2",
                            },
                        },
                        "quantity": 4,
                    }
                ],
            },
        ],
        "listing": listing,
        "licensee": licensee,
        "buyer": buyer,
        "seller": {
            "id": "SEL-9121-8944",
            "href": "/accounts/sellers/SEL-9121-8944",
            "name": "Software LN",
            "icon": "/static/SEL-9121-8944/icon.png",
            "address": {
                "country": "US",
            },
        },
        "product": {
            "id": "PRD-1111-1111",
        },
    }


@pytest.fixture()
def order_factory(
    settings,
    agreement,
    order_parameters_factory,
    fulfillment_parameters_factory,
    lines_factory,
    status="Processing",
):
    """
    Marketplace platform order for tests.
    """

    def _order(
        order_id="ORD-0792-5000-2253-4210",
        order_type="Purchase",
        order_parameters=None,
        fulfillment_parameters=None,
        lines=None,
        subscriptions=None,
        external_ids=None,
        status=status,
        template=None,
    ):
        order_parameters = (
            order_parameters_factory() if order_parameters is None else order_parameters
        )
        fulfillment_parameters = (
            fulfillment_parameters_factory()
            if fulfillment_parameters is None
            else fulfillment_parameters
        )

        lines = lines_factory() if lines is None else lines
        subscriptions = [] if subscriptions is None else subscriptions

        order = {
            "id": order_id,
            "error": None,
            "href": "/commerce/orders/ORD-0792-5000-2253-4210",
            "agreement": agreement,
            "authorization": {"id": "AUT-1234-4567", "currency": "USD,"},
            "type": order_type,
            "status": status,
            "clientReferenceNumber": None,
            "notes": "First order to try",
            "lines": lines,
            "subscriptions": subscriptions,
            "parameters": {
                "fulfillment": fulfillment_parameters,
                "ordering": order_parameters,
            },
            "audit": {
                "created": {
                    "at": "2023-12-14T18:02:16.9359",
                    "by": {"id": "USR-0000-0001"},
                },
                "updated": None,
            },
            "product": {
                "id": settings.MPT_PRODUCTS_IDS[0],
                "href": "/catalog/products/PRD-7208-0459",
                "name": "SoftwareOne FinOps for Cloud",
                "externalIds": {},
                "icon": "/v1/catalog/products/PRD-7208-0459/icon",
                "status": "Published",
            },
        }
        if external_ids:
            order["externalIds"] = external_ids
        if template:
            order["template"] = template
        return order

    return _order


@pytest.fixture()
def processing_purchase_order(order_factory):
    return order_factory()


@pytest.fixture()
def processing_change_order(order_factory):
    return order_factory(order_type="Change")


@pytest.fixture()
def processing_termination_order(order_factory):
    return order_factory(order_type="Terminate")


@pytest.fixture()
def processing_configuration_order(order_factory):
    return order_factory(order_type="Configuration")


@pytest.fixture()
def first_attempt_processing_purchase_order(processing_purchase_order):
    for param in processing_purchase_order["parameters"]["fulfillment"]:
        del param["value"]

    return processing_purchase_order


@pytest.fixture()
def failed_purchase_order(order_factory):
    failed_order = order_factory(status="Failed")
    failed_order["statusNotes"] = {
        "id": "EXT001",
        "message": "Order can't be processed. Failure reason: error",
    }

    return failed_order


@pytest.fixture()
def completed_purchase_order(order_factory, subscriptions_factory):
    return order_factory(status="Completed", subscriptions=subscriptions_factory())


@pytest.fixture()
def querying_purchase_order(order_factory):
    return order_factory(status="Querying")


@pytest.fixture()
def draft_purchase_valid_order(order_factory):
    return order_factory(status="Draft")


@pytest.fixture()
def draft_purchase_invalid_order(draft_purchase_valid_order):
    draft_purchase_valid_order["parameters"]["ordering"][0]["value"] = None
    return draft_purchase_valid_order


@pytest.fixture()
def webhook(settings):
    return {
        "id": "WH-123-123",
        "criteria": {"product.id": settings.MPT_PRODUCTS_IDS[0]},
    }


@pytest.fixture()
def mpt_client(settings):
    """
    Create an instance of the MPT client used by the extension.
    """
    settings.MPT_API_BASE_URL = "https://localhost"
    from mpt_extension_sdk.core.utils import setup_client

    return setup_client()


@pytest.fixture()
def mpt_error_factory():
    """
    Generate an error message returned by the Marketplace platform.
    """

    def _mpt_error(
        status,
        title,
        detail,
        trace_id="00-27cdbfa231ecb356ab32c11b22fd5f3c-721db10d009dfa2a-00",
        errors=None,
    ):
        error = {
            "status": status,
            "title": title,
            "detail": detail,
            "traceId": trace_id,
        }
        if errors:
            error["errors"] = errors

        return error

    return _mpt_error


@pytest.fixture()
def mpt_list_response():
    def _wrap_response(objects_list):
        return {
            "data": objects_list,
        }

    return _wrap_response


@pytest.fixture()
def jwt_token(settings):
    iat = nbf = int(datetime.now().timestamp())
    exp = nbf + 300
    return jwt.encode(
        {
            "iss": "mpt",
            "aud": "aws.ext.s1.com",
            "iat": iat,
            "nbf": nbf,
            "exp": exp,
            "webhook_id": "WH-123-123",
        },
        get_for_product(settings, "WEBHOOKS_SECRETS", "PRD-1111-1111"),
        algorithm="HS256",
    )


@pytest.fixture()
def extension_settings(settings):
    current_extension_config = copy.copy(settings.EXTENSION_CONFIG)
    yield settings
    settings.EXTENSION_CONFIG = current_extension_config


@pytest.fixture()
def mock_env_webhook_secret():
    return '{ "webhook_secret": "WEBHOOK_SECRET" }'


@pytest.fixture()
def mock_email_notification_sender():
    return "email_sender"


@pytest.fixture()
def mocked_next_step(mocker):
    return mocker.MagicMock()


@pytest.fixture()
def ffc_organization():
    return {
        "name": "Nimbus Nexus Inc.",
        "currency": "EUR",
        "billing_currency": "USD",
        "operations_external_id": "AGR-9876-5534-9172",
        "events": {
            "created": {
                "at": "2025-04-03T15:04:25.894Z",
                "by": {"id": "string", "type": "user", "name": "Barack Obama"},
            },
            "updated": {
                "at": "2025-04-03T15:04:25.894Z",
                "by": {"id": "string", "type": "user", "name": "Barack Obama"},
            },
            "deleted": {
                "at": "2025-04-03T15:04:25.894Z",
                "by": {"id": "string", "type": "user", "name": "Barack Obama"},
            },
        },
        "id": "FORG-1234-1234-1234",
        "linked_organization_id": "ee7ebfaf-a222-4209-aecc-67861694a488",
        "status": "active",
        "expenses_info": {
            "limit": "10,000.00",
            "expenses_last_month": "4,321.26",
            "expenses_this_month": "2,111.49",
            "expenses_this_month_forecast": "5,001.12",
            "possible_monthly_saving": "4.66",
        },
    }


@pytest.fixture()
def ffc_employee():
    return {
        "email": "test@exaple.com",
        "display_name": "Tor James Parker",
        "created_at": "2025-04-04T09:11:36.291Z",
        "last_login": "2025-04-04T09:11:36.291Z",
        "roles_count": 0,
        "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    }
