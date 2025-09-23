import copy
from datetime import UTC, datetime
from decimal import Decimal
from typing import Generator

import httpx
import jwt
import pytest
import responses
from swo.mpt.extensions.runtime.djapp.conf import get_for_product

from ffc.billing.dataclasses import ProcessResult, ProcessResultInfo
from ffc.billing.process_billing import AuthorizationProcessor
from ffc.clients.base import BaseAsyncAPIClient


@pytest.fixture()
def requests_mocker():
    """
    Allow mocking of http calls made with requests.
    """
    with responses.RequestsMock() as rsps:
        yield rsps


@pytest.fixture()
def get_organizations():
    return [
        {
            "name": "SoftwareOne (Test Environment)",
            "currency": "USD",
            "billing_currency": "EUR",
            "operations_external_id": "ACC-1234-5678",
            "events": {
                "created": {
                    "at": "2025-04-03T15:18:02.408803Z",
                    "by": {"id": "FUSR-6956-9254", "type": "user", "name": "FrancescoFaraone"},
                },
                "updated": {
                    "at": "2025-04-22T13:32:00.599322Z",
                    "by": {"id": "FUSR-6956-9254", "type": "user", "name": "FrancescoFaraone"},
                },
            },
            "id": "FORG-4801-6958-2949",
            "linked_organization_id": "3d0fe384-b1cf-4929-ad5e-1aa544f93dd5",
            "status": "active",
        },
    ]


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
        start_date = start_date.isoformat() if start_date else datetime.now(UTC).isoformat()
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
                "fulfillment": fulfillment_parameters or fulfillment_parameters_factory(),
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
        "client": {
            "id": "ACC-9121-8944",
            "href": "/accounts/sellers/ACC-9121-8944",
            "name": "Software LN",
            "icon": "/static/ACC-9121-8944/icon.png",
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
    return order_factory(
        order_type="Termination",
        order_parameters=[],
    )


@pytest.fixture()
def processing_configuration_order(order_factory):
    return order_factory(order_type="Configuration")


@pytest.fixture()
def first_attempt_processing_purchase_order(processing_purchase_order):
    params_with_values = [
        p for p in processing_purchase_order["parameters"]["fulfillment"] if "value" in p
    ]
    for param in params_with_values:
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
def entitlement():
    return {
        "items": [
            {
                "name": "dfgfsdgsdgfsdfgfasf",
                "affiliate_external_id": "34534563456",
                "datasource_id": "34654563456",
                "id": "FENT-2502-5308-4600",
                "owner": {
                    "id": "FACC-8686-4136",
                    "name": "Test Accept invitation for existing user",
                    "type": "affiliate",
                },
                "status": "new",
                "events": {
                    "created": {
                        "at": "2025-07-10T08:22:44.126636Z",
                        "by": {"id": "FUSR-2345-9426", "type": "user", "name": "Tomasz"},
                    },
                    "updated": {
                        "at": "2025-07-10T08:22:44.051141Z",
                        "by": {"id": "FUSR-2345-9426", "type": "user", "name": "Tomasz"},
                    },
                },
            },
            {
                "name": "wqrwertwetwr",
                "affiliate_external_id": "234523456234562",
                "datasource_id": "sdfasfdasdf",
                "id": "FENT-2625-7695-6282",
                "owner": {
                    "id": "FACC-8686-4136",
                    "name": "Test Accept invitation for existing user",
                    "type": "affiliate",
                },
                "status": "new",
                "events": {
                    "created": {
                        "at": "2025-07-10T08:22:11.400321Z",
                        "by": {"id": "FUSR-2345-9426", "type": "user", "name": "Tomasz"},
                    },
                    "updated": {
                        "at": "2025-07-10T08:22:11.303663Z",
                        "by": {"id": "FUSR-2345-9426", "type": "user", "name": "Tomasz"},
                    },
                },
            },
            {
                "name": "345345345345dfsdfvzadfvasxddvf",
                "affiliate_external_id": "2253453456",
                "datasource_id": "4523653456",
                "id": "FENT-5197-1585-4783",
                "owner": {
                    "id": "FACC-8686-4136",
                    "name": "Test Accept invitation for existing user",
                    "type": "affiliate",
                },
                "status": "new",
                "events": {
                    "created": {
                        "at": "2025-07-10T08:21:38.010646Z",
                        "by": {"id": "FUSR-2345-9426", "type": "user", "name": "Tomasz"},
                    },
                    "updated": {
                        "at": "2025-07-10T08:21:37.937403Z",
                        "by": {"id": "FUSR-2345-9426", "type": "user", "name": "Tomasz"},
                    },
                },
            },
            {
                "name": "qweqweqw",
                "affiliate_external_id": "qweqweqwe",
                "datasource_id": "34534545",
                "id": "FENT-8654-8302-7297",
                "owner": {
                    "id": "FACC-8686-4136",
                    "name": "Test Accept invitation for existing user",
                    "type": "affiliate",
                },
                "status": "new",
                "events": {
                    "created": {
                        "at": "2025-07-10T08:21:19.516501Z",
                        "by": {"id": "FUSR-2345-9426", "type": "user", "name": "Tomasz"},
                    },
                    "updated": {
                        "at": "2025-07-10T08:21:19.437454Z",
                        "by": {"id": "FUSR-2345-9426", "type": "user", "name": "Tomasz"},
                    },
                },
            },
            {
                "name": "ewrwerwer",
                "affiliate_external_id": "wqweqwe",
                "datasource_id": "qweqwe",
                "id": "FENT-1432-3132-9430",
                "owner": {
                    "id": "FACC-8686-4136",
                    "name": "Test Accept invitation for existing user",
                    "type": "affiliate",
                },
                "status": "new",
                "events": {
                    "created": {
                        "at": "2025-07-10T08:21:03.567451Z",
                        "by": {"id": "FUSR-2345-9426", "type": "user", "name": "Tomasz"},
                    },
                    "updated": {
                        "at": "2025-07-10T08:21:03.496876Z",
                        "by": {"id": "FUSR-2345-9426", "type": "user", "name": "Tomasz"},
                    },
                },
            },
            {
                "name": "rwerwer",
                "affiliate_external_id": "cco-34234345",
                "datasource_id": "231423",
                "id": "FENT-8186-0526-2061",
                "owner": {
                    "id": "FACC-8686-4136",
                    "name": "Test Accept invitation for existing user",
                    "type": "affiliate",
                },
                "status": "new",
                "events": {
                    "created": {
                        "at": "2025-07-10T08:20:45.160288Z",
                        "by": {"id": "FUSR-2345-9426", "type": "user", "name": "Tomasz"},
                    },
                    "updated": {
                        "at": "2025-07-10T08:20:45.085988Z",
                        "by": {"id": "FUSR-2345-9426", "type": "user", "name": "Tomasz"},
                    },
                },
            },
            {
                "name": "sfsadfasdfdsa",
                "affiliate_external_id": "asdfasdf",
                "datasource_id": "asdfsadf",
                "id": "FENT-7190-2021-5257",
                "owner": {
                    "id": "FACC-8686-4136",
                    "name": "Test Accept invitation for existing user",
                    "type": "affiliate",
                },
                "status": "new",
                "events": {
                    "created": {
                        "at": "2025-07-10T08:08:35.055703Z",
                        "by": {"id": "FUSR-6956-9254", "type": "user", "name": "FrancescoFaraone"},
                    },
                    "updated": {
                        "at": "2025-07-10T08:08:34.961701Z",
                        "by": {"id": "FUSR-6956-9254", "type": "user", "name": "FrancescoFaraone"},
                    },
                },
            },
            {
                "name": "Cic",
                "affiliate_external_id": "tetesksk292929",
                "datasource_id": "kskskssksks",
                "id": "FENT-5279-3531-9327",
                "owner": {"id": "FACC-5810-4583", "name": "Test", "type": "affiliate"},
                "status": "new",
                "events": {
                    "created": {
                        "at": "2025-07-10T08:08:11.717386Z",
                        "by": {"id": "FUSR-6956-9254", "type": "user", "name": "FrancescoFaraone"},
                    },
                    "updated": {
                        "at": "2025-07-10T08:08:11.645376Z",
                        "by": {"id": "FUSR-6956-9254", "type": "user", "name": "FrancescoFaraone"},
                    },
                },
            },
            {
                "name": "Test 2 ",
                "affiliate_external_id": "Test 1234567",
                "datasource_id": "dhdhdfgdhj",
                "id": "FENT-3855-5465-8262",
                "owner": {"id": "FACC-5810-4583", "name": "Test", "type": "affiliate"},
                "status": "new",
                "events": {
                    "created": {
                        "at": "2025-07-10T08:07:49.140003Z",
                        "by": {"id": "FUSR-6956-9254", "type": "user", "name": "FrancescoFaraone"},
                    },
                    "updated": {
                        "at": "2025-07-10T08:07:49.051657Z",
                        "by": {"id": "FUSR-6956-9254", "type": "user", "name": "FrancescoFaraone"},
                    },
                },
            },
            {
                "name": "Test",
                "affiliate_external_id": "Test123456",
                "datasource_id": "abcd",
                "id": "FENT-6617-4434-4125",
                "owner": {
                    "id": "FACC-8686-4136",
                    "name": "Test Accept invitation for existing user",
                    "type": "affiliate",
                },
                "status": "new",
                "events": {
                    "created": {
                        "at": "2025-07-10T08:07:30.818813Z",
                        "by": {"id": "FUSR-6956-9254", "type": "user", "name": "FrancescoFaraone"},
                    },
                    "updated": {
                        "at": "2025-07-10T08:07:30.729431Z",
                        "by": {"id": "FUSR-6956-9254", "type": "user", "name": "FrancescoFaraone"},
                    },
                },
            },
            {
                "name": "Test delete",
                "affiliate_external_id": "one-two-delete",
                "datasource_id": "ds-delete-id",
                "id": "FENT-2389-3478-4085",
                "owner": {"id": "FACC-1515-3385", "name": "The Turing Team", "type": "affiliate"},
                "status": "deleted",
                "events": {
                    "created": {
                        "at": "2025-05-22T14:40:19.211236Z",
                        "by": {
                            "id": "FUSR-2150-8141",
                            "type": "user",
                            "name": "Aleksandra Ovchinnikova",
                        },
                    },
                    "updated": {
                        "at": "2025-05-22T14:45:10.882997Z",
                        "by": {
                            "id": "FUSR-2150-8141",
                            "type": "user",
                            "name": "Aleksandra Ovchinnikova",
                        },
                    },
                    "deleted": {
                        "at": "2025-05-22T14:45:11.017527Z",
                        "by": {
                            "id": "FUSR-2150-8141",
                            "type": "user",
                            "name": "Aleksandra Ovchinnikova",
                        },
                    },
                },
            },
            {
                "name": "Full cycle test",
                "affiliate_external_id": "one-two-one",
                "datasource_id": "full-ds-id",
                "id": "FENT-2609-0912-9266",
                "linked_datasource_id": "0708f18c-b23a-4652-8fd1-5d95f89226a9",
                "linked_datasource_name": "MPT Finops (Dev)",
                "linked_datasource_type": "azure_cnr",
                "owner": {"id": "FACC-1515-3385", "name": "The Turing Team", "type": "affiliate"},
                "status": "terminated",
                "events": {
                    "created": {
                        "at": "2025-05-22T14:37:12.724341Z",
                        "by": {
                            "id": "FUSR-2150-8141",
                            "type": "user",
                            "name": "Aleksandra Ovchinnikova",
                        },
                    },
                    "updated": {
                        "at": "2025-05-22T14:39:18.641970Z",
                        "by": {
                            "id": "FUSR-2150-8141",
                            "type": "user",
                            "name": "Aleksandra Ovchinnikova",
                        },
                    },
                    "redeemed": {
                        "at": "2025-05-22T14:38:35.569897Z",
                        "by": {
                            "id": "FORG-4801-6958-2949",
                            "name": "SoftwareOne (Test Environment)",
                            "operations_external_id": "ACC-1234-5678",
                        },
                    },
                    "terminated": {
                        "at": "2025-05-22T14:39:18.775267Z",
                        "by": {
                            "id": "FUSR-2150-8141",
                            "type": "user",
                            "name": "Aleksandra Ovchinnikova",
                        },
                    },
                },
            },
            {
                "name": "Fake entitlement for testing redeem",
                "affiliate_external_id": "one-two-three",
                "datasource_id": "my-ds-id",
                "id": "FENT-5791-2178-5994",
                "owner": {"id": "FACC-1515-3385", "name": "The Turing Team", "type": "affiliate"},
                "status": "new",
                "events": {
                    "created": {
                        "at": "2025-04-22T17:48:30.320143Z",
                        "by": {"id": "FUSR-6956-9254", "type": "user", "name": "FrancescoFaraone"},
                    },
                    "updated": {
                        "at": "2025-04-22T17:48:30.262507Z",
                        "by": {"id": "FUSR-6956-9254", "type": "user", "name": "FrancescoFaraone"},
                    },
                },
            },
            {
                "name": "I will not pay for dev env",
                "affiliate_external_id": "AGR-0000-9999",
                "datasource_id": "0fd2fbdf-d2cc-42e3-9749-1747b6b1fe83",
                "id": "FENT-7955-5617-4625",
                "owner": {"id": "FACC-1515-3385", "name": "The Turing Team", "type": "affiliate"},
                "status": "new",
                "events": {
                    "created": {
                        "at": "2025-04-22T17:48:04.420250Z",
                        "by": {"id": "FUSR-6956-9254", "type": "user", "name": "FrancescoFaraone"},
                    },
                    "updated": {
                        "at": "2025-04-22T17:48:04.267931Z",
                        "by": {"id": "FUSR-6956-9254", "type": "user", "name": "FrancescoFaraone"},
                    },
                },
            },
        ],
        "total": 14,
        "limit": 50,
        "offset": 0,
    }


@pytest.fixture()
def expenses():
    return [
        {
            "events": {
                "created": {"at": "2025-05-31T09:00:10.791181Z"},
                "updated": {"at": "2025-05-31T21:00:10.900386Z"},
            },
            "id": "FDSX-9720-0822-5699",
            "datasource_id": "2d2f328c-1407-4e5e-ba59-1cbad182940f",
            "linked_datasource_id": "947cbf94-afc3-4055-b96d-eff284c36a09",
            "datasource_name": "CHaaS (Production)",
            "linked_datasource_type": "azure_cnr",
            "organization": {
                "id": "FORG-4801-6958-2949",
                "name": "SoftwareOne (Test Environment)",
                "operations_external_id": "ACC-1234-5678",
            },
            "year": 2025,
            "day": 31,
            "month": 5,
            "expenses": "5484.1464",
        },
        {
            "events": {
                "created": {"at": "2025-05-31T09:00:10.895964Z"},
                "updated": {"at": "2025-05-31T21:00:10.900386Z"},
            },
            "id": "FDSX-1412-2194-1623",
            "datasource_id": "6c73c89e-7e5b-43b5-a7c4-1b0cb260dafb",
            "linked_datasource_id": "1aa5f619-eab6-4d80-a11f-b2765c4a4795",
            "datasource_name": "CHaaS (QA)",
            "linked_datasource_type": "azure_cnr",
            "organization": {
                "id": "FORG-4801-6958-2949",
                "name": "SoftwareOne (Test Environment)",
                "operations_external_id": "ACC-1234-5678",
            },
            "year": 2025,
            "day": 31,
            "month": 5,
            "expenses": "2244.3480",
        },
        {
            "events": {
                "created": {"at": "2025-05-31T09:00:10.935998Z"},
                "updated": {"at": "2025-05-31T21:00:10.900386Z"},
            },
            "id": "FDSX-7626-5167-0610",
            "datasource_id": "91819a1c-c7d3-4b89-bc9f-39f85bff4666",
            "linked_datasource_id": "d4321470-cfa8-4a67-adf5-c11faf491e14",
            "datasource_name": "CPA (Development and Test)",
            "linked_datasource_type": "azure_cnr",
            "organization": {
                "id": "FORG-4801-6958-2949",
                "name": "SoftwareOne (Test Environment)",
                "operations_external_id": "ACC-1234-5678",
            },
            "year": 2025,
            "day": 31,
            "month": 5,
            "expenses": "36368.0435",
        },
        {
            "events": {
                "created": {"at": "2025-05-31T09:00:10.980464Z"},
                "updated": {"at": "2025-05-31T21:00:10.900386Z"},
            },
            "id": "FDSX-3900-5021-3406",
            "datasource_id": "01643997-4d64-4718-8114-15e488ce3f61",
            "linked_datasource_id": "100efd88-28fb-49f1-946b-edbf78ad4650",
            "datasource_name": "CPA (Infrastructure)",
            "linked_datasource_type": "azure_cnr",
            "organization": {
                "id": "FORG-4801-6958-2949",
                "name": "SoftwareOne (Test Environment)",
                "operations_external_id": "ACC-1234-5678",
            },
            "year": 2025,
            "day": 31,
            "month": 5,
            "expenses": "12012.9029",
        },
        {
            "events": {
                "created": {"at": "2025-05-31T09:00:11.020795Z"},
                "updated": {"at": "2025-05-31T21:00:10.900386Z"},
            },
            "id": "FDSX-5514-3587-5985",
            "datasource_id": "b6689fdb-ac8c-4116-8136-c7a179cb5be6",
            "linked_datasource_id": "1812ae7a-890f-413a-a4e3-9a76c357cfb2",
            "datasource_name": "CPA (QA and Production)",
            "linked_datasource_type": "azure_cnr",
            "organization": {
                "id": "FORG-4801-6958-2949",
                "name": "SoftwareOne (Test Environment)",
                "operations_external_id": "ACC-1234-5678",
            },
            "year": 2025,
            "day": 31,
            "month": 5,
            "expenses": "140492.1680",
        },
        {
            "events": {
                "created": {"at": "2025-05-31T09:00:11.061262Z"},
                "updated": {"at": "2025-05-31T21:00:10.900386Z"},
            },
            "id": "FDSX-9091-3723-8599",
            "datasource_id": "203689795269",
            "linked_datasource_id": "b9204d35-9508-423e-8c0e-493d7c89f123",
            "datasource_name": "Marketplace (Dev)",
            "linked_datasource_type": "aws_cnr",
            "organization": {
                "id": "FORG-4801-6958-2949",
                "name": "SoftwareOne (Test Environment)",
                "operations_external_id": "ACC-1234-5678",
            },
            "year": 2025,
            "day": 31,
            "month": 5,
            "expenses": "449.7770",
        },
        {
            "events": {
                "created": {"at": "2025-05-31T09:00:11.104151Z"},
                "updated": {"at": "2025-05-31T21:00:10.900386Z"},
            },
            "id": "FDSX-3762-3669-2884",
            "datasource_id": "654035049067",
            "linked_datasource_id": "3f584d10-4293-4599-8ad5-413acc72fd45",
            "datasource_name": "Marketplace (Production)",
            "linked_datasource_type": "aws_cnr",
            "organization": {
                "id": "FORG-4801-6958-2949",
                "name": "SoftwareOne (Test Environment)",
                "operations_external_id": "ACC-1234-5678",
            },
            "year": 2025,
            "day": 31,
            "month": 5,
            "expenses": "763.9655",
        },
        {
            "events": {
                "created": {"at": "2025-05-31T09:00:11.142825Z"},
                "updated": {"at": "2025-05-31T21:00:10.900386Z"},
            },
            "id": "FDSX-4432-7370-5890",
            "datasource_id": "563690021965",
            "linked_datasource_id": "fb0088de-2e3c-4ffe-b6e4-dc075503473d",
            "datasource_name": "Marketplace (Staging)",
            "linked_datasource_type": "aws_cnr",
            "organization": {
                "id": "FORG-4801-6958-2949",
                "name": "SoftwareOne (Test Environment)",
                "operations_external_id": "ACC-1234-5678",
            },
            "year": 2025,
            "day": 31,
            "month": 5,
            "expenses": "1.5603",
        },
        {
            "events": {
                "created": {"at": "2025-05-31T09:00:11.402325Z"},
                "updated": {"at": "2025-05-31T21:00:10.900386Z"},
            },
            "id": "FDSX-5882-3175-6293",
            "datasource_id": "89b098bc-b400-4578-8058-8416b0c25f6b",
            "linked_datasource_id": "cb78a18a-6adc-4780-9402-d175086accdc",
            "datasource_name": "MPT Finops (Production)",
            "linked_datasource_type": "azure_cnr",
            "organization": {
                "id": "FORG-4801-6958-2949",
                "name": "SoftwareOne (Test Environment)",
                "operations_external_id": "ACC-1234-5678",
            },
            "year": 2025,
            "day": 31,
            "month": 5,
            "expenses": "2866.7103",
        },
        {
            "events": {
                "created": {"at": "2025-05-31T09:00:11.602225Z"},
                "updated": {"at": "2025-05-31T21:00:10.900386Z"},
            },
            "id": "FDSX-5883-8914-3036",
            "datasource_id": "63f2c438-c0e1-4606-ac10-eb6aa149c6cb",
            "linked_datasource_id": "12fa3bce-5513-40c8-96d7-0be2fc47ebcf",
            "datasource_name": "MPT Finops (Staging)",
            "linked_datasource_type": "azure_cnr",
            "organization": {
                "id": "FORG-4801-6958-2949",
                "name": "SoftwareOne (Test Environment)",
                "operations_external_id": "ACC-1234-5678",
            },
            "year": 2025,
            "day": 31,
            "month": 5,
            "expenses": "2948.0483",
        },
        {
            "events": {
                "created": {"at": "2025-05-31T09:00:11.729544Z"},
                "updated": {"at": "2025-05-31T21:00:10.900386Z"},
            },
            "id": "FDSX-5383-4251-5606",
            "datasource_id": "285102913731",
            "linked_datasource_id": "c86dfcec-08ba-4007-a617-8f53efbfba06",
            "datasource_name": "SoftwareOne AWS",
            "linked_datasource_type": "aws_cnr",
            "organization": {
                "id": "FORG-4801-6958-2949",
                "name": "SoftwareOne (Test Environment)",
                "operations_external_id": "ACC-1234-5678",
            },
            "year": 2025,
            "day": 31,
            "month": 5,
            "expenses": "147974.7328",
        },
        {
            "events": {
                "created": {"at": "2025-05-31T09:00:11.185263Z"},
                "updated": {"at": "2025-05-31T21:00:10.900386Z"},
            },
            "id": "FDSX-9914-5293-7158",
            "datasource_id": "996403779197",
            "linked_datasource_id": "2a3db41b-bcd9-48b1-824f-87acfb510f88",
            "datasource_name": "Marketplace (Test)",
            "linked_datasource_type": "aws_cnr",
            "organization": {
                "id": "FORG-4801-6958-2949",
                "name": "SoftwareOne (Test Environment)",
                "operations_external_id": "ACC-1234-5678",
            },
            "year": 2025,
            "day": 31,
            "month": 5,
            "expenses": "22.3045",
        },
        {
            "events": {
                "created": {"at": "2025-05-31T09:00:11.224685Z"},
                "updated": {"at": "2025-05-31T21:00:10.900386Z"},
            },
            "id": "FDSX-8478-3286-4449",
            "datasource_id": "e30e2a6e-0712-48c3-8685-3298df063633",
            "linked_datasource_id": "b509e2e2-20a4-48eb-ac60-b291338feff4",
            "datasource_name": "MPT (Dev)",
            "linked_datasource_type": "azure_cnr",
            "organization": {
                "id": "FORG-4801-6958-2949",
                "name": "SoftwareOne (Test Environment)",
                "operations_external_id": "ACC-1234-5678",
            },
            "year": 2025,
            "day": 31,
            "month": 5,
            "expenses": "3678.8134",
        },
        {
            "events": {
                "created": {"at": "2025-05-31T09:00:11.264197Z"},
                "updated": {"at": "2025-05-31T21:00:10.900386Z"},
            },
            "id": "FDSX-5166-9927-9966",
            "datasource_id": "ef415e11-361a-4f91-8b3c-23aeb9c8f2ac",
            "linked_datasource_id": "96e23b8d-854b-42d7-8b59-264e6f314b2d",
            "datasource_name": "MPT (Production)",
            "linked_datasource_type": "azure_cnr",
            "organization": {
                "id": "FORG-4801-6958-2949",
                "name": "SoftwareOne (Test Environment)",
                "operations_external_id": "ACC-1234-5678",
            },
            "year": 2025,
            "day": 31,
            "month": 5,
            "expenses": "0.0004",
        },
        {
            "events": {
                "created": {"at": "2025-05-31T09:00:11.312828Z"},
                "updated": {"at": "2025-05-31T21:00:10.900386Z"},
            },
            "id": "FDSX-3043-7639-0675",
            "datasource_id": "dea8e892-1212-42c9-afa0-3b87e7bfffd5",
            "linked_datasource_id": "a611abd8-9cde-4b17-ab54-31f9d43dc955",
            "datasource_name": "MPT (Test)",
            "linked_datasource_type": "azure_cnr",
            "organization": {
                "id": "FORG-4801-6958-2949",
                "name": "SoftwareOne (Test Environment)",
                "operations_external_id": "ACC-1234-5678",
            },
            "year": 2025,
            "day": 31,
            "month": 5,
            "expenses": "2564.4489",
        },
        {
            "events": {
                "created": {"at": "2025-05-31T09:00:11.688224Z"},
                "updated": {"at": "2025-05-31T09:00:11.688232Z"},
            },
            "id": "FDSX-6912-0266-0891",
            "datasource_id": "a7e5cb3a-1b68-445b-9234-7cebea7a6458",
            "linked_datasource_id": "fe5d1e82-2b10-4786-8f44-0dfd7ac3144a",
            "datasource_name": "MPT Platform (Staging)",
            "linked_datasource_type": "azure_cnr",
            "organization": {
                "id": "FORG-4801-6958-2949",
                "name": "SoftwareOne (Test Environment)",
                "operations_external_id": "ACC-1234-5678",
            },
            "year": 2025,
            "day": 31,
            "month": 5,
            "expenses": "0.0000",
        },
        {
            "events": {
                "created": {"at": "2025-05-31T09:00:11.644465Z"},
                "updated": {"at": "2025-05-31T09:00:11.644473Z"},
            },
            "id": "FDSX-3079-0267-3379",
            "datasource_id": "a37be38a-56e4-4fab-8e3c-e4738f50ad70",
            "linked_datasource_id": "29b2698f-6110-4a7c-88f7-58a14e4db6af",
            "datasource_name": "MPT Finops (Test)",
            "linked_datasource_type": "azure_cnr",
            "organization": {
                "id": "FORG-4801-6958-2949",
                "name": "SoftwareOne (Test Environment)",
                "operations_external_id": "ACC-1234-5678",
            },
            "year": 2025,
            "day": 31,
            "month": 5,
            "expenses": "0.0000",
        },
        {
            "events": {
                "created": {"at": "2025-05-31T09:00:11.356732Z"},
                "updated": {"at": "2025-05-31T09:00:11.356739Z"},
            },
            "id": "FDSX-3452-5162-7796",
            "datasource_id": "6964b7a4-9ce4-4975-98d7-b9a2e3b0a48e",
            "linked_datasource_id": "0708f18c-b23a-4652-8fd1-5d95f89226a9",
            "datasource_name": "MPT Finops (Dev)",
            "linked_datasource_type": "azure_cnr",
            "organization": {
                "id": "FORG-4801-6958-2949",
                "name": "SoftwareOne (Test Environment)",
                "operations_external_id": "ACC-1234-5678",
            },
            "year": 2025,
            "day": 31,
            "month": 5,
            "expenses": "0.0000",
        },
    ]


@pytest.fixture()
def daily_expenses():
    return {
        1: Decimal("1957.9254"),
        2: Decimal("3233.8422"),
        3: Decimal("3170.0376"),
        4: Decimal("4982.3398"),
        5: Decimal("3746.7108"),
        6: Decimal("2503.8501"),
        7: Decimal("2518.9622"),
        8: Decimal("1186.67"),
        9: Decimal("4132.4113"),
        10: Decimal("1544.0553"),
        11: Decimal("2981.121"),
        12: Decimal("1289.2675"),
        13: Decimal("2770.6942"),
        14: Decimal("1133.5218"),
        15: Decimal("1133.1845"),
        16: Decimal("4716.4833"),
        17: Decimal("3406.0789"),
        18: Decimal("2654.5862"),
        19: Decimal("3317.5269"),
        20: Decimal("4820.0637"),
        21: Decimal("3542.4266"),
        22: Decimal("3280.8039"),
        23: Decimal("4401.6766"),
        24: Decimal("4175.2924"),
        25: Decimal("2377.7552"),
        26: Decimal("4432.751"),
        27: Decimal("4777.9023"),
        28: Decimal("5126.0458"),
        29: Decimal("5226.0458"),
        30: Decimal("5326.0458"),
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


@pytest.fixture()
def billing_process_instance():
    return AuthorizationProcessor(
        month=6,
        year=2025,
        authorization={
            "id": "AUT-5305-9928",
            "name": "TEST",
            "currency": "USD",
        },
    )


@pytest.fixture()
def authorization_process_result():
    return ProcessResultInfo(
        authorization_id="AUT-5305-9928",
    )


@pytest.fixture()
def create_journal_response():
    return {
        "$meta": {
            "omitted": ["processing"],
        },
        "id": "BJO-9000-4019",
        "name": "June 2025 Charges",
        "externalIds": {
            "vendor": "202506",
        },
        "status": "Draft",
        "vendor": {
            "id": "ACC-3102-8586",
            "type": "Vendor",
            "status": "Active",
            "name": "FinOps for Cloud",
            "icon": "/v1/accounts/accounts/ACC-3102-8586/icon",
        },
        "owner": {
            "id": "SEL-7032-1456",
            "externalId": "US",
            "name": "SoftwareONE Inc.",
            "icon": "/v1/accounts/sellers/SEL-7032-1456/icon",
        },
        "product": {
            "id": "PRD-2426-7318",
            "name": "FinOps for Cloud",
            "externalIds": {
                "operations": "adsasadsa",
            },
            "icon": "/v1/catalog/products/PRD-2426-7318/icon",
            "status": "Published",
        },
        "authorization": {
            "id": "AUT-5305-9928",
            "name": "asdasdsa",
            "currency": "USD",
        },
        "dueDate": "2025-07-01T00:00:00.000Z",
        "price": {
            "currency": "USD",
            "totalPP": 0.00000,
        },
        "upload": {
            "total": 0,
            "split": 0,
            "ready": 0,
            "error": 0,
        },
        "audit": {
            "created": {
                "at": "2025-06-10T17:04:53.802Z",
                "by": {
                    "id": "TKN-5645-5497",
                    "name": "Antonio Di Mariano",
                    "icon": "",
                },
            },
            "updated": {},
        },
    }


@pytest.fixture()
def existing_journal_file_response():
    return {
        "$meta": {
            "pagination": {"offset": 0, "limit": 10, "total": 1},
            "omitted": ["processing", "audit"],
        },
        "data": [
            {
                "id": "BJO-9000-4019",
                "name": "June 2025 Charges",
                "externalIds": {
                    "vendor": "202506",
                },
                "status": "Draft",
                "vendor": {
                    "id": "ACC-3102-8586",
                    "type": "Vendor",
                    "status": "Active",
                    "name": "FinOps for Cloud",
                    "icon": "/v1/accounts/accounts/ACC-3102-8586/icon",
                },
                "owner": {
                    "id": "SEL-7032-1456",
                    "externalId": "US",
                    "name": "SoftwareONE Inc.",
                    "icon": "/v1/accounts/sellers/SEL-7032-1456/icon",
                },
                "product": {
                    "id": "PRD-2426-7318",
                    "name": "FinOps for Cloud",
                    "externalIds": {
                        "operations": "adsasadsa",
                    },
                    "icon": "/v1/catalog/products/PRD-2426-7318/icon",
                    "status": "Published",
                },
                "authorization": {
                    "id": "AUT-5305-9928",
                    "name": "asdasdsa",
                    "currency": "USD",
                },
                "dueDate": "2025-07-01T00:00:00.000Z",
                "price": {
                    "currency": "USD",
                    "totalPP": 0.00000,
                },
                "upload": {
                    "total": 0,
                    "split": 0,
                    "ready": 0,
                    "error": 0,
                },
            },
        ],
    }


@pytest.fixture()
def journal_attachment_response():
    return {
        "$meta": {
            "pagination": {"offset": 0, "limit": 10, "total": 1},
            "omitted": ["processing", "audit"],
        },
        "data": [
            {
                "id": "JOA-5985-1983",
                "name": "charge_file.json",
                "journal": {
                    "id": "BJO-9000-4019",
                    "name": "June 2025 Charges",
                    "dueDate": "2025-07-01T00:00:00.000Z",
                },
                "vendor": {
                    "id": "ACC-3102-8586",
                    "type": "Vendor",
                    "status": "Active",
                    "name": "FinOps for Cloud",
                    "icon": "/v1/accounts/accounts/ACC-3102-8586/icon",
                },
                "type": "Attachment",
                "filename": "charge_file.json",
                "size": 2981,
                "contentType": "application/json",
                "description": "Conversion Rate",
                "isDeleted": False,
            },
        ],
    }


@pytest.fixture()
def agreement_data_with_trial():
    def _agreement_factory(**overrides):
        data = [
            {
                "id": "AGR-4528-5004-9617",
                "status": "Active",
                "listing": {"id": "LST-9168-7963"},
                "authorization": {
                    "id": "AUT-5305-9928",
                    "name": "SoftwareOne FinOps for Cloud (USD)",
                    "currency": "USD",
                },
                "vendor": {
                    "id": "ACC-3805-2089",
                    "type": "Vendor",
                    "status": "Active",
                    "name": "SoftwareOne Vendor",
                    "icon": "/v1/accounts/accounts/ACC-3805-2089/icon",
                },
                "client": {
                    "id": "ACC-5563-4382",
                    "type": "Client",
                    "status": "Active",
                    "name": "Adastraflex 2.0",
                    "icon": "/v1/accounts/accounts/ACC-5563-4382/icon",
                },
                "price": {"PPxY": 0.00000, "PPxM": 0.00000, "currency": "USD"},
                "template": {"id": "TPL-7208-0459-0006", "name": "Purchase"},
                "name": "SoftwareOne FinOps for Cloud for Adastraflex 2.0",
                "parameters": {
                    "ordering": [
                        {
                            "id": "PAR-7208-0459-0004",
                            "externalId": "organizationName",
                            "name": "Organization Name",
                            "type": "SingleLineText",
                            "phase": "Order",
                            "displayValue": "Software One",
                            "value": "Software One",
                        },
                        {
                            "id": "PAR-7208-0459-0005",
                            "externalId": "adminContact",
                            "name": "Administrator",
                            "type": "Contact",
                            "phase": "Order",
                            "displayValue": "JJ Adams jj@softwareone123.com",
                            "value": {
                                "firstName": "JJ",
                                "lastName": "Adams",
                                "email": "jj@softwareone123.com",
                                "phone": None,
                            },
                        },
                        {
                            "id": "PAR-7208-0459-0006",
                            "externalId": "currency",
                            "name": "Currency",
                            "type": "DropDown",
                            "phase": "Order",
                            "displayValue": "EUR",
                            "value": "EUR",
                        },
                    ],
                    "fulfillment": [
                        {
                            "id": "PAR-7208-0459-0007",
                            "externalId": "dueDate",
                            "name": "Due date",
                            "type": "Date",
                            "phase": "Fulfillment",
                        },
                        {
                            "id": "PAR-7208-0459-0008",
                            "externalId": "isNewUser",
                            "name": "Is new user?",
                            "type": "Checkbox",
                            "phase": "Fulfillment",
                        },
                        {
                            "id": "PAR-7208-0459-0009",
                            "externalId": "trialStartDate",
                            "name": "Trial period start date",
                            "type": "Date",
                            "phase": "Fulfillment",
                            "displayValue": "2025-06-01",
                            "value": "2025-06-01",
                        },
                        {
                            "id": "PAR-7208-0459-0010",
                            "externalId": "trialEndDate",
                            "name": "Trial period end date",
                            "type": "Date",
                            "phase": "Fulfillment",
                            "displayValue": "2025-06-15",
                            "value": "2025-06-15",
                        },
                        {
                            "id": "PAR-7208-0459-0011",
                            "externalId": "billedPercentage",
                            "name": "Billed percentage of monthly spend",
                            "type": "SingleLineText",
                            "phase": "Fulfillment",
                            "displayValue": "4",
                            "value": "4",
                        },
                    ],
                },
                "licensee": {"id": "LCE-1815-3571-9260", "name": "Pawels Licensee US"},
                "buyer": {"id": "BUY-6923-7488", "name": "Pawels Buyer"},
                "seller": {
                    "id": "SEL-7282-9889",
                    "externalId": "78ADB9DA-BC69-4CBF-BAA0-CDBC28619EF7",
                    "name": "SoftwareOne, Inc.",
                    "icon": "/v1/accounts/sellers/SEL-7282-9889/icon",
                },
                "product": {
                    "id": "PRD-7208-0459",
                    "name": "SoftwareOne FinOps for Cloud",
                    "externalIds": {},
                    "icon": "/v1/catalog/products/PRD-7208-0459/icon",
                    "status": "Published",
                },
                "externalIds": {"client": "", "vendor": "FORG-1919-6513-6770"},
            }
        ]
        if overrides:
            data[0].update(overrides)
        return data

    return _agreement_factory()


@pytest.fixture()
def agreement_data_no_trial():
    def _agreement_factory(**overrides):
        data = [
            {
                "id": "AGR-4528-5004-9617",
                "status": "Active",
                "listing": {"id": "LST-9168-7963"},
                "authorization": {
                    "id": "AUT-5305-9928",
                    "name": "SoftwareOne FinOps for Cloud (USD)",
                    "currency": "USD",
                },
                "vendor": {
                    "id": "ACC-3805-2089",
                    "type": "Vendor",
                    "status": "Active",
                    "name": "SoftwareOne Vendor",
                    "icon": "/v1/accounts/accounts/ACC-3805-2089/icon",
                },
                "client": {
                    "id": "ACC-5563-4382",
                    "type": "Client",
                    "status": "Active",
                    "name": "Adastraflex 2.0",
                    "icon": "/v1/accounts/accounts/ACC-5563-4382/icon",
                },
                "price": {"PPxY": 0.00000, "PPxM": 0.00000, "currency": "USD"},
                "template": {"id": "TPL-7208-0459-0006", "name": "Purchase"},
                "name": "SoftwareOne FinOps for Cloud for Adastraflex 2.0",
                "parameters": {
                    "ordering": [
                        {
                            "id": "PAR-7208-0459-0004",
                            "externalId": "organizationName",
                            "name": "Organization Name",
                            "type": "SingleLineText",
                            "phase": "Order",
                            "displayValue": "Software One",
                            "value": "Software One",
                        },
                        {
                            "id": "PAR-7208-0459-0005",
                            "externalId": "adminContact",
                            "name": "Administrator",
                            "type": "Contact",
                            "phase": "Order",
                            "displayValue": "JJ Adams jj@softwareone123.com",
                            "value": {
                                "firstName": "JJ",
                                "lastName": "Adams",
                                "email": "jj@softwareone123.com",
                                "phone": None,
                            },
                        },
                        {
                            "id": "PAR-7208-0459-0006",
                            "externalId": "currency",
                            "name": "Currency",
                            "type": "DropDown",
                            "phase": "Order",
                            "displayValue": "EUR",
                            "value": "EUR",
                        },
                    ],
                    "fulfillment": [
                        {
                            "id": "PAR-7208-0459-0007",
                            "externalId": "dueDate",
                            "name": "Due date",
                            "type": "Date",
                            "phase": "Fulfillment",
                        },
                        {
                            "id": "PAR-7208-0459-0008",
                            "externalId": "isNewUser",
                            "name": "Is new user?",
                            "type": "Checkbox",
                            "phase": "Fulfillment",
                        },
                        {
                            "id": "PAR-7208-0459-0011",
                            "externalId": "billedPercentage",
                            "name": "Billed percentage of monthly spend",
                            "type": "SingleLineText",
                            "phase": "Fulfillment",
                            "displayValue": "4",
                            "value": "4",
                        },
                    ],
                },
                "licensee": {"id": "LCE-1815-3571-9260", "name": "Pawels Licensee US"},
                "buyer": {"id": "BUY-6923-7488", "name": "Pawels Buyer"},
                "seller": {
                    "id": "SEL-7282-9889",
                    "externalId": "78ADB9DA-BC69-4CBF-BAA0-CDBC28619EF7",
                    "name": "SoftwareOne, Inc.",
                    "icon": "/v1/accounts/sellers/SEL-7282-9889/icon",
                },
                "product": {
                    "id": "PRD-7208-0459",
                    "name": "SoftwareOne FinOps for Cloud",
                    "externalIds": {},
                    "icon": "/v1/catalog/products/PRD-7208-0459/icon",
                    "status": "Published",
                },
                "externalIds": {"client": "", "vendor": "FORG-1919-6513-6770"},
            }
        ]
        if overrides:
            data[0].update(overrides)
        return data

    return _agreement_factory()


@pytest.fixture()
def agreement_fulfillment():
    return [
        {
            "externalId": "dueDate",
            "id": "PAR-7208-0459-0007",
            "name": "Due date",
            "phase": "Fulfillment",
            "type": "Date",
        },
        {
            "externalId": "isNewUser",
            "id": "PAR-7208-0459-0008",
            "name": "Is new user?",
            "phase": "Fulfillment",
            "type": "Checkbox",
        },
        {
            "displayValue": "2025-06-01",
            "externalId": "trialStartDate",
            "id": "PAR-7208-0459-0009",
            "name": "Trial period start date",
            "phase": "Fulfillment",
            "type": "Date",
            "value": "2025-06-01",
        },
        {
            "displayValue": "2025-06-15",
            "externalId": "trialEndDate",
            "id": "PAR-7208-0459-0010",
            "name": "Trial period end date",
            "phase": "Fulfillment",
            "type": "Date",
            "value": "2025-06-15",
        },
        {
            "displayValue": "4",
            "externalId": "billedPercentage",
            "id": "PAR-7208-0459-0011",
            "name": "Billed percentage of monthly spend",
            "phase": "Fulfillment",
            "type": "SingleLineText",
            "value": "4",
        },
    ]


@pytest.fixture()
def organization_data():
    return {
        "name": "SoftwareOne (Test Environment)",
        "currency": "USD",
        "billing_currency": "EUR",
        "operations_external_id": "ACC-1234-5678",
        "events": {
            "created": {
                "at": "2025-04-03T15:18:02.408803Z",
                "by": {
                    "id": "FUSR-6956-9254",
                    "type": "user",
                    "name": "FrancescoFaraone",
                },
            },
            "updated": {
                "at": "2025-04-22T13:32:00.599322Z",
                "by": {
                    "id": "FUSR-6956-9254",
                    "type": "user",
                    "name": "FrancescoFaraone",
                },
            },
        },
        "id": "FORG-4801-6958-2949",
        "linked_organization_id": "3d0fe384-b1cf-4929-ad5e-1aa544f93dd5",
        "status": "active",
    }


@pytest.fixture()
def catalog_authorizations():
    return {
        "$meta": {"pagination": {"offset": 0, "limit": 10, "total": 1}, "omitted": ["audit"]},
        "data": [
            {
                "id": "AUT-5305-9928",
                "name": "asdasdsa",
                "externalIds": {},
                "currency": "USD",
                "notes": "",
                "product": {
                    "id": "PRD-2426-7318",
                    "name": "FinOps for Cloud",
                    "externalIds": {"operations": "adsasadsa"},
                    "icon": "/v1/catalog/products/PRD-2426-7318/icon",
                    "status": "Published",
                },
                "vendor": {
                    "id": "ACC-3102-8586",
                    "type": "Vendor",
                    "status": "Active",
                    "name": "FinOps for Cloud",
                    "icon": "/v1/accounts/accounts/ACC-3102-8586/icon",
                },
                "owner": {
                    "id": "SEL-7032-1456",
                    "externalId": "US",
                    "name": "SoftwareONE Inc.",
                    "icon": "/v1/accounts/sellers/SEL-7032-1456/icon",
                },
                "statistics": {"subscriptions": 7, "agreements": 12, "sellers": 2, "listings": 2},
                "journal": {"firstInvoiceDate": "2025-02-01T00:00:00.000Z", "frequency": "1m"},
                "eligibility": {"client": True, "partner": False},
            }
        ],
    }


@pytest.fixture()
def catalog_authorization():
    return {
        "id": "AUT-5305-9928",
        "name": "asdasdsa",
        "externalIds": {},
        "currency": "USD",
        "notes": "",
        "product": {
            "id": "PRD-2426-7318",
            "name": "FinOps for Cloud",
            "externalIds": {"operations": "adsasadsa"},
            "icon": "/v1/catalog/products/PRD-2426-7318/icon",
            "status": "Published",
        },
        "vendor": {
            "id": "ACC-3102-8586",
            "type": "Vendor",
            "status": "Active",
            "name": "FinOps for Cloud",
            "icon": "/v1/accounts/accounts/ACC-3102-8586/icon",
        },
        "owner": {
            "id": "SEL-7032-1456",
            "externalId": "US",
            "name": "SoftwareONE Inc.",
            "icon": "/v1/accounts/sellers/SEL-7032-1456/icon",
        },
        "statistics": {"subscriptions": 7, "agreements": 12, "sellers": 2, "listings": 2},
        "journal": {"firstInvoiceDate": "2025-02-01T00:00:00.000Z", "frequency": "1m"},
        "eligibility": {"client": True, "partner": False},
        "audit": {
            "created": {
                "at": "2024-10-23T15:39:19.138Z",
                "by": {"id": "USR-6476-8245", "name": "Francesco Faraone"},
            }
        },
    }


@pytest.fixture()
def agreements():
    return {
        "$meta": {
            "pagination": {"offset": 0, "limit": 1000, "total": 1},
            "omitted": [
                "lines",
                "assets",
                "subscriptions",
                "split",
                "termsAndConditions",
                "certificates",
            ],
        },
        "data": [
            {
                "id": "AGR-4985-4034-6503",
                "status": "Active",
                "listing": {
                    "id": "LST-9168-7963",
                },
                "authorization": {
                    "id": "AUT-5305-9928",
                    "name": "SoftwareOne FinOps for Cloud (USD)",
                    "currency": "USD",
                },
                "vendor": {
                    "id": "ACC-3805-2089",
                    "type": "Vendor",
                    "status": "Active",
                    "name": "SoftwareOne Vendor",
                    "icon": "/v1/accounts/accounts/ACC-3805-2089/icon",
                },
                "client": {
                    "id": "ACC-5809-3083",
                    "type": "Client",
                    "status": "Active",
                    "name": "Area302 (Client)",
                    "icon": "/v1/accounts/accounts/ACC-5809-3083/icon",
                },
                "price": {
                    "PPxY": 0.00000,
                    "PPxM": 0.00000,
                    "currency": "USD",
                },
                "template": {
                    "id": "TPL-7208-0459-0003",
                    "name": "Default",
                },
                "name": "SoftwareOne FinOps for Cloud for Area302 (Client)",
                "parameters": {
                    "ordering": [
                        {
                            "id": "PAR-7208-0459-0004",
                            "externalId": "organizationName",
                            "name": "Organization Name",
                            "type": "SingleLineText",
                            "phase": "Order",
                            "displayValue": "PL Organization",
                            "value": "PL Organization",
                        },
                        {
                            "id": "PAR-7208-0459-0005",
                            "externalId": "adminContact",
                            "name": "Administrator",
                            "type": "Contact",
                            "phase": "Order",
                            "displayValue": "PL NNN pavel.lonkin@softwareone.com",
                            "value": {
                                "firstName": "PL",
                                "lastName": "NNN",
                                "email": "pavel.lonkin@softwareone.com",
                                "phone": None,
                            },
                        },
                        {
                            "id": "PAR-7208-0459-0006",
                            "externalId": "currency",
                            "name": "Currency",
                            "type": "DropDown",
                            "phase": "Order",
                            "displayValue": "EUR",
                            "value": "EUR",
                        },
                    ],
                    "fulfillment": [
                        {
                            "id": "PAR-7208-0459-0007",
                            "externalId": "dueDate",
                            "name": "Due Date",
                            "type": "Date",
                            "phase": "Fulfillment",
                        },
                    ],
                },
                "licensee": {
                    "id": "LCE-3603-9310-4566",
                    "name": "Adobe Licensee 302",
                },
                "buyer": {
                    "id": "BUY-0280-5606",
                    "name": "Rolls-Royce Corporation",
                    "icon": "/v1/accounts/buyers/BUY-0280-5606/icon",
                },
                "seller": {
                    "id": "SEL-7282-9889",
                    "externalId": "78ADB9DA-BC69-4CBF-BAA0-CDBC28619EF7",
                    "name": "SoftwareOne, Inc.",
                    "icon": "/v1/accounts/sellers/SEL-7282-9889/icon",
                },
                "product": {
                    "id": "PRD-7208-0459",
                    "name": "SoftwareOne FinOps for Cloud",
                    "externalIds": {},
                    "icon": "/v1/catalog/products/PRD-7208-0459/icon",
                    "status": "Published",
                },
                "externalIds": {
                    "client": "",
                    "vendor": "FORG-6649-3383-1832",
                },
            }
        ],
    }


@pytest.fixture()
def currency_conversion():
    return {
        "base_currency": "USD",
        "billing_currency": "EUR",
        "exchange_rate": Decimal("0.8636"),
        "exchange_rates": {
            "base_code": "USD",
            "conversion_rates": {
                "AED": 3.6725,
                "AFN": 69.5472,
                "ALL": 85.1093,
                "AMD": 383.3873,
                "ANG": 1.79,
                "AOA": 918.3743,
                "ARS": 1185.5,
                "AUD": 1.5327,
                "AWG": 1.79,
                "AZN": 1.6992,
                "BAM": 1.6892,
                "BBD": 2.0,
                "BDT": 122.1719,
                "BGN": 1.689,
                "BHD": 0.376,
                "BIF": 2971.7492,
                "BMD": 1.0,
                "BND": 1.2792,
                "BOB": 6.9152,
                "BRL": 5.537,
                "BSD": 1.0,
                "BTN": 85.5923,
                "BWP": 13.3716,
                "BYN": 3.2669,
                "BZD": 2.0,
                "CAD": 1.3609,
                "CDF": 2886.4367,
                "CHF": 0.8117,
                "CLP": 933.6466,
                "CNY": 7.1775,
                "COP": 4186.1683,
                "CRC": 506.581,
                "CUP": 24.0,
                "CVE": 95.2338,
                "CZK": 21.3879,
                "DJF": 177.721,
                "DKK": 6.4402,
                "DOP": 59.022,
                "DZD": 130.8973,
                "EGP": 49.7557,
                "ERN": 15.0,
                "ETB": 134.8766,
                "EUR": 0.8636,
                "FJD": 2.2443,
                "FKP": 0.7353,
                "FOK": 6.441,
                "GBP": 0.7353,
                "GEL": 2.7292,
                "GGP": 0.7353,
                "GHS": 10.8065,
                "GIP": 0.7353,
                "GMD": 72.7261,
                "GNF": 8687.5475,
                "GTQ": 7.675,
                "GYD": 209.2835,
                "HKD": 7.8497,
                "HNL": 26.045,
                "HRK": 6.5074,
                "HTG": 130.9916,
                "HUF": 346.2904,
                "IDR": 16225.9113,
                "ILS": 3.5607,
                "IMP": 0.7353,
                "INR": 85.5933,
                "IQD": 1307.6716,
                "IRR": 41954.7543,
                "ISK": 124.3409,
                "JEP": 0.7353,
                "JMD": 159.2592,
                "JOD": 0.709,
                "JPY": 143.5195,
                "KES": 129.0672,
                "KGS": 87.3928,
                "KHR": 4017.1102,
                "KID": 1.5329,
                "KMF": 424.9034,
                "KRW": 1354.9252,
                "KWD": 0.3058,
                "KYD": 0.8333,
                "KZT": 511.6331,
                "LAK": 21653.3424,
                "LBP": 89500.0,
                "LKR": 298.6639,
                "LRD": 199.5512,
                "LSL": 17.7775,
                "LYD": 5.4592,
                "MAD": 9.0986,
                "MDL": 17.2013,
                "MGA": 4499.8917,
                "MKD": 53.8655,
                "MMK": 2095.7236,
                "MNT": 3569.2457,
                "MOP": 8.0852,
                "MRU": 39.6769,
                "MUR": 45.4594,
                "MVR": 15.4172,
                "MWK": 1738.8487,
                "MXN": 18.9026,
                "MYR": 4.2226,
                "MZN": 63.881,
                "NAD": 17.7775,
                "NGN": 1536.0716,
                "NIO": 36.7269,
                "NOK": 9.9437,
                "NPR": 136.9476,
                "NZD": 1.6495,
                "OMR": 0.3845,
                "PAB": 1.0,
                "PEN": 3.6211,
                "PGK": 4.1514,
                "PHP": 55.7289,
                "PKR": 282.2843,
                "PLN": 3.6835,
                "PYG": 8001.9463,
                "QAR": 3.64,
                "RON": 4.345,
                "RSD": 101.2894,
                "RUB": 79.8143,
                "RWF": 1436.0247,
                "SAR": 3.75,
                "SBD": 8.5594,
                "SCR": 14.8355,
                "SDG": 510.8585,
                "SEK": 9.4431,
                "SGD": 1.2792,
                "SHP": 0.7353,
                "SLE": 22.3674,
                "SLL": 22367.3971,
                "SOS": 570.7579,
                "SRD": 37.3233,
                "SSP": 4634.0855,
                "STN": 21.1602,
                "SYP": 12892.7896,
                "SZL": 17.7775,
                "THB": 32.4006,
                "TJS": 10.057,
                "TMT": 3.4978,
                "TND": 2.9285,
                "TOP": 2.3506,
                "TRY": 39.3856,
                "TTD": 6.7715,
                "TVD": 1.5329,
                "TWD": 29.3672,
                "TZS": 2582.2337,
                "UAH": 41.53,
                "UGX": 3594.8408,
                "USD": 1,
                "UYU": 41.2386,
                "UZS": 12703.3397,
                "VES": 101.0822,
                "VND": 26033.7896,
                "VUV": 119.0876,
                "WST": 2.7383,
                "XAF": 566.5378,
                "XCD": 2.7,
                "XCG": 1.79,
                "XDR": 0.7278,
                "XOF": 566.5378,
                "XPF": 103.0648,
                "YER": 243.0015,
                "ZAR": 17.7777,
                "ZMW": 24.8208,
                "ZWL": 6.9749,
            },
            "documentation": "https://www.exchangerate-api.com/docs",
            "result": "success",
            "terms_of_use": "https://www.exchangerate-api.com/terms",
            "time_last_update_unix": 1749772801,
            "time_last_update_utc": "Fri, 13 Jun 2025 00:00:01 +0000",
            "time_next_update_unix": 1749859201,
            "time_next_update_utc": "Sat, 14 Jun 2025 00:00:01 +0000",
        },
    }


@pytest.fixture()
def exchange_rates():
    return {
        "result": "success",
        "documentation": "https://www.exchangerate-api.com/docs",
        "terms_of_use": "https://www.exchangerate-api.com/terms",
        "time_last_update_unix": 1749772801,
        "time_last_update_utc": "Fri, 13 Jun 2025 00:00:01 +0000",
        "time_next_update_unix": 1749859201,
        "time_next_update_utc": "Sat, 14 Jun 2025 00:00:01 +0000",
        "base_code": "USD",
        "conversion_rates": {
            "USD": 1,
            "AED": 3.6725,
            "AFN": 69.5472,
            "ALL": 85.1093,
            "AMD": 383.3873,
            "ANG": 1.7900,
            "AOA": 918.3743,
            "ARS": 1185.5000,
            "AUD": 1.5327,
            "AWG": 1.7900,
            "AZN": 1.6992,
            "BAM": 1.6892,
            "BBD": 2.0000,
            "BDT": 122.1719,
            "BGN": 1.6890,
            "BHD": 0.3760,
            "BIF": 2971.7492,
            "BMD": 1.0000,
            "BND": 1.2792,
            "BOB": 6.9152,
            "BRL": 5.5370,
            "BSD": 1.0000,
            "BTN": 85.5923,
            "BWP": 13.3716,
            "BYN": 3.2669,
            "BZD": 2.0000,
            "CAD": 1.3609,
            "CDF": 2886.4367,
            "CHF": 0.8117,
            "CLP": 933.6466,
            "CNY": 7.1775,
            "COP": 4186.1683,
            "CRC": 506.5810,
            "CUP": 24.0000,
            "CVE": 95.2338,
            "CZK": 21.3879,
            "DJF": 177.7210,
            "DKK": 6.4402,
            "DOP": 59.0220,
            "DZD": 130.8973,
            "EGP": 49.7557,
            "ERN": 15.0000,
            "ETB": 134.8766,
            "EUR": 0.8636,
            "FJD": 2.2443,
            "FKP": 0.7353,
            "FOK": 6.4410,
            "GBP": 0.7353,
            "GEL": 2.7292,
            "GGP": 0.7353,
            "GHS": 10.8065,
            "GIP": 0.7353,
            "GMD": 72.7261,
            "GNF": 8687.5475,
            "GTQ": 7.6750,
            "GYD": 209.2835,
            "HKD": 7.8497,
            "HNL": 26.0450,
            "HRK": 6.5074,
            "HTG": 130.9916,
            "HUF": 346.2904,
            "IDR": 16225.9113,
            "ILS": 3.5607,
            "IMP": 0.7353,
            "INR": 85.5933,
            "IQD": 1307.6716,
            "IRR": 41954.7543,
            "ISK": 124.3409,
            "JEP": 0.7353,
            "JMD": 159.2592,
            "JOD": 0.7090,
            "JPY": 143.5195,
            "KES": 129.0672,
            "KGS": 87.3928,
            "KHR": 4017.1102,
            "KID": 1.5329,
            "KMF": 424.9034,
            "KRW": 1354.9252,
            "KWD": 0.3058,
            "KYD": 0.8333,
            "KZT": 511.6331,
            "LAK": 21653.3424,
            "LBP": 89500.0000,
            "LKR": 298.6639,
            "LRD": 199.5512,
            "LSL": 17.7775,
            "LYD": 5.4592,
            "MAD": 9.0986,
            "MDL": 17.2013,
            "MGA": 4499.8917,
            "MKD": 53.8655,
            "MMK": 2095.7236,
            "MNT": 3569.2457,
            "MOP": 8.0852,
            "MRU": 39.6769,
            "MUR": 45.4594,
            "MVR": 15.4172,
            "MWK": 1738.8487,
            "MXN": 18.9026,
            "MYR": 4.2226,
            "MZN": 63.8810,
            "NAD": 17.7775,
            "NGN": 1536.0716,
            "NIO": 36.7269,
            "NOK": 9.9437,
            "NPR": 136.9476,
            "NZD": 1.6495,
            "OMR": 0.3845,
            "PAB": 1.0000,
            "PEN": 3.6211,
            "PGK": 4.1514,
            "PHP": 55.7289,
            "PKR": 282.2843,
            "PLN": 3.6835,
            "PYG": 8001.9463,
            "QAR": 3.6400,
            "RON": 4.3450,
            "RSD": 101.2894,
            "RUB": 79.8143,
            "RWF": 1436.0247,
            "SAR": 3.7500,
            "SBD": 8.5594,
            "SCR": 14.8355,
            "SDG": 510.8585,
            "SEK": 9.4431,
            "SGD": 1.2792,
            "SHP": 0.7353,
            "SLE": 22.3674,
            "SLL": 22367.3971,
            "SOS": 570.7579,
            "SRD": 37.3233,
            "SSP": 4634.0855,
            "STN": 21.1602,
            "SYP": 12892.7896,
            "SZL": 17.7775,
            "THB": 32.4006,
            "TJS": 10.0570,
            "TMT": 3.4978,
            "TND": 2.9285,
            "TOP": 2.3506,
            "TRY": 39.3856,
            "TTD": 6.7715,
            "TVD": 1.5329,
            "TWD": 29.3672,
            "TZS": 2582.2337,
            "UAH": 41.5300,
            "UGX": 3594.8408,
            "UYU": 41.2386,
            "UZS": 12703.3397,
            "VES": 101.0822,
            "VND": 26033.7896,
            "VUV": 119.0876,
            "WST": 2.7383,
            "XAF": 566.5378,
            "XCD": 2.7000,
            "XCG": 1.7900,
            "XDR": 0.7278,
            "XOF": 566.5378,
            "XPF": 103.0648,
            "YER": 243.0015,
            "ZAR": 17.7777,
            "ZMW": 24.8208,
            "ZWL": 6.9749,
        },
    }


@pytest.fixture()
def org_mock_generator(get_organizations):
    async def _gen():
        for org in get_organizations:
            yield org

    return _gen()


@pytest.fixture()
def org_mock_generator_agr_000(get_organizations):
    get_organizations[0]["operations_external_id"] = "AGR-0000-0000-0000"

    async def _gen():
        for org in get_organizations:
            yield org

    return _gen()


@pytest.fixture()
def agr_mock_generator(agreements):
    async def _gen():
        for agr in agreements["data"]:
            yield agr

    return _gen()


@pytest.fixture()
def agr_mock_generator_with_trial(agreement_data_with_trial):
    async def _gen():
        for agr in agreement_data_with_trial:
            yield agr

    return _gen()


@pytest.fixture()
def exp_mock_generator(expenses):
    async def _gen():
        for exp in expenses:
            yield exp

    return _gen()


@pytest.fixture()
def patch_fetch_organizations(mocker, billing_process_instance, org_mock_generator):
    return mocker.patch.object(
        billing_process_instance.ffc_client,
        "fetch_organizations",
        return_value=org_mock_generator,
    )


@pytest.fixture()
def patch_fetch_agreements(mocker, billing_process_instance, agr_mock_generator):
    return mocker.patch.object(
        billing_process_instance.mpt_client, "fetch_agreements", return_value=agr_mock_generator
    )


@pytest.fixture()
def patch_fetch_organization_expenses(mocker, billing_process_instance, exp_mock_generator):
    return mocker.patch.object(
        billing_process_instance.ffc_client,
        "fetch_organization_expenses",
        return_value=exp_mock_generator,
    )


@pytest.fixture()
def patch_fetch_agreements_with_trial(
    mocker, billing_process_instance, agr_mock_generator_with_trial
):
    return mocker.patch.object(
        billing_process_instance.mpt_client,
        "fetch_agreements",
        return_value=agr_mock_generator_with_trial,
    )


@pytest.fixture()
def patch_fetch_organizations_agr_000(
    mocker, billing_process_instance, agr_mock_generator, org_mock_generator_agr_000
):
    return mocker.patch.object(
        billing_process_instance.ffc_client,
        "fetch_organizations",
        return_value=org_mock_generator_agr_000,
    )


class TestClientAuth(httpx.Auth):
    def auth_flow(self, request: httpx.Request) -> Generator[httpx.Request, httpx.Response, None]:
        request.headers["Authorization"] = "Bearer fake token"
        yield request


class FakeAPIClient(BaseAsyncAPIClient):
    @property
    def base_url(self) -> str:
        return "https://local.local/v1"

    @property
    def auth(self):
        return TestClientAuth()

    def get_pagination_meta(self, response):
        return response["meta"]["pagination"]

    def get_page_data(self, response):
        return response["data"]


@pytest.fixture()
def fake_apiclient():
    return FakeAPIClient(limit=2)


@pytest.fixture()
def process_result_success_payload():
    return [
        ProcessResultInfo(
            authorization_id="AUTH-1234-5678",
            journal_id="BJO-1234-5678",
            result=ProcessResult.JOURNAL_GENERATED,
            message=None,
        ),
    ]


@pytest.fixture()
def process_result_with_warning():
    return [
        ProcessResultInfo(
            authorization_id="AUTH-1234-5678",
            journal_id="BJO-1234-5678",
            result=ProcessResult.JOURNAL_SKIPPED,
            message="Found the journal BJO-8604-8083 with status Review",
        ),
    ]


@pytest.fixture()
def process_result_with_error():
    return [
        ProcessResultInfo(
            authorization_id="AUTH-1234-5678",
            journal_id="BJO-1234-5678",
            result=ProcessResult.ERROR,
            message="Error",
        ),
    ]
