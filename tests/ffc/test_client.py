from datetime import datetime, timedelta, timezone

import jwt
import pytest
import responses
from freezegun import freeze_time
from responses import matchers

from ffc.client import FinOpsHttpError, FinOpsNotFoundError, get_ffc_client


@pytest.fixture()
def ffc_client_settings(settings):
    settings.EXTENSION_CONFIG = {
        "FFC_OPERATIONS_API_BASE_URL": "https://local.local",
        "FFC_SUB": "FKT-1234",
        "FFC_OPERATIONS_SECRET": "1234",
    }

    return settings


@pytest.fixture()
def mock_jwt_encoder(ffc_client_settings):
    def wrapper(now):
        return jwt.encode(
            {
                "sub": ffc_client_settings.EXTENSION_CONFIG["FFC_SUB"],
                "exp": now + timedelta(minutes=5),
                "nbf": now,
                "iat": now,
            },
            ffc_client_settings.EXTENSION_CONFIG["FFC_OPERATIONS_SECRET"],
            algorithm="HS256",
        )

    return wrapper


def test_finops_http_error():
    error = FinOpsHttpError(400, "Nothing")

    assert str(error) == "400 - Nothing"


def test_finops_not_found_error():
    error = FinOpsNotFoundError("Nothing")

    assert str(error) == "404 - Nothing"


@freeze_time("2025-01-01")
@responses.activate
def test_get_employee(mocker, mock_jwt_encoder, ffc_client_settings):
    mocker.patch(
        "ffc.client.uuid4",
        return_value="uuid-1",
    )

    now = datetime.now(tz=timezone.utc)
    token = mock_jwt_encoder(now)

    responses.get(
        "https://local.local/ops/v1/employees/test@example.com",
        status=200,
        json={"id": "test-employee"},
        match=[
            matchers.header_matcher(
                {
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                    "X-Request-Id": "uuid-1",
                },
            )
        ],
    )

    client = get_ffc_client()
    employee = client.get_employee("test@example.com")

    assert employee == {"id": "test-employee"}


@freeze_time("2025-01-01")
@responses.activate
def test_get_employee_not_found(mocker, mock_jwt_encoder, ffc_client_settings):
    mocker.patch(
        "ffc.client.uuid4",
        return_value="uuid-1",
    )

    now = datetime.now(tz=timezone.utc)
    token = mock_jwt_encoder(now)

    responses.get(
        "https://local.local/ops/v1/employees/test@example.com",
        status=404,
        json={"error": "test-error"},
        match=[
            matchers.header_matcher(
                {
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                    "X-Request-Id": "uuid-1",
                },
            )
        ],
    )

    client = get_ffc_client()
    with pytest.raises(FinOpsNotFoundError) as e:
        client.get_employee("test@example.com")

    assert str(e.value) == "404 - {'error': 'test-error'}"


@freeze_time("2025-01-01")
@responses.activate
def test_create_employee(mocker, mock_jwt_encoder, ffc_client_settings):
    mocker.patch(
        "ffc.client.uuid4",
        return_value="uuid-1",
    )

    now = datetime.now(tz=timezone.utc)
    token = mock_jwt_encoder(now)

    responses.post(
        "https://local.local/ops/v1/employees",
        status=200,
        json={"id": "test-employee"},
        match=[
            matchers.header_matcher(
                {
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                    "X-Request-Id": "uuid-1",
                },
            ),
            matchers.json_params_matcher(
                {
                    "email": "test@example.com",
                    "display_name": "Test Test",
                }
            ),
        ],
    )

    client = get_ffc_client()
    employee = client.create_employee("test@example.com", "Test Test")

    assert employee == {"id": "test-employee"}


@freeze_time("2025-01-01")
@responses.activate
def test_create_organization(mocker, mock_jwt_encoder, ffc_client_settings):
    mocker.patch(
        "ffc.client.uuid4",
        return_value="uuid-1",
    )

    now = datetime.now(tz=timezone.utc)
    token = mock_jwt_encoder(now)

    responses.post(
        "https://local.local/ops/v1/organizations",
        status=200,
        json={"id": "test-organization"},
        match=[
            matchers.header_matcher(
                {
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                    "X-Request-Id": "uuid-1",
                },
            ),
            matchers.json_params_matcher(
                {
                    "name": "Organization Name",
                    "currency": "EUR",
                    "billing_currency": "USD",
                    "operations_external_id": "AGR-1234-1234",
                    "user_id": "user-id",
                }
            ),
        ],
    )

    client = get_ffc_client()
    organization = client.create_organization(
        "Organization Name",
        "EUR",
        "USD",
        "AGR-1234-1234",
        "user-id",
    )

    assert organization == {"id": "test-organization"}


@freeze_time("2025-01-01")
@responses.activate
def test_get_organization(mocker, mock_jwt_encoder, ffc_client_settings):
    mocker.patch(
        "ffc.client.uuid4",
        return_value="uuid-1",
    )
    agreement_id = "AGR-1234-1234"

    now = datetime.now(tz=timezone.utc)
    token = mock_jwt_encoder(now)

    responses.get(
        f"https://local.local/ops/v1/organizations?eq(operations_external_id,{agreement_id})&limit=1",
        status=200,
        json={"items": [{"id": "test-organization"}]},
        match=[
            matchers.header_matcher(
                {
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                    "X-Request-Id": "uuid-1",
                },
            ),
        ],
    )

    client = get_ffc_client()
    organizations = client.get_organizations_by_external_id(agreement_id)

    assert organizations == [{"id": "test-organization"}]
