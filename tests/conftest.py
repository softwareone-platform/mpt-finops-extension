import copy
from datetime import UTC, datetime

import jwt
import pytest
import responses
from swo.mpt.extensions.runtime.djapp.conf import get_for_product

from ffc.process_billing import AuthorizationProcessor


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
        authorization={}
    )


@pytest.fixture()
def return_create_journal():
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
def existing_journal_file():
    return [
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
    ]


@pytest.fixture()
def return_journal_attachment():
    return [
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
    ]


@pytest.fixture()
def get_organization():
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
def get_agreement_details():
    return [
        {
            "id": "AGR-4985-4034-6503",
            "status": "Active",
            "listing": {
                "id": "LST-9168-7963",
            },
            "authorization": {
                "id": "AUT-3727-1184",
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
        },
    ]


@pytest.fixture()
def get_exchange_rate():
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
