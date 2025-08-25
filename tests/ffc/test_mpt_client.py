import re
from datetime import datetime, timezone
from io import BytesIO

import httpx
import pytest

from ffc.clients.mpt import MPTAsyncClient, fmtd


@pytest.fixture()
def mtp_client_settings(settings):
    settings.MPT_API_BASE_URL = "https://local.local"
    settings.MPT_API_TOKEN = "fake_token"
    settings.MPT_PRODUCTS_IDS = ["PRD-1111-1111", "PRD-1111-2222", "PRD-1111-3333"]

    return settings


@pytest.fixture()
def mocked_mpt_client(mtp_client_settings):
    return MPTAsyncClient()


@pytest.mark.asyncio()
async def test_fetch_authorization(
    httpx_mock, mocked_mpt_client, catalog_authorization, mtp_client_settings
):
    auth_id = "AUT-5305-9928"
    httpx_mock.add_response(
        method="GET",
        url=re.compile(r"https://local\.local/v1/catalog/authorizations"),
        json=catalog_authorization,
    )
    response = await mocked_mpt_client.fetch_authorization(authorization_id=auth_id)
    assert response == catalog_authorization
    [req] = httpx_mock.get_requests()
    assert req.url == httpx.URL(f"https://local.local/v1/catalog/authorizations/{auth_id}")
    assert req.headers["Authorization"] == "Bearer fake_token"


@pytest.mark.asyncio()
async def test_fetch_authorization_404_raises(httpx_mock, mocked_mpt_client):
    auth_id = "NOT_FOUND"
    httpx_mock.add_response(
        method="GET",
        url=f"https://local.local/v1/catalog/authorizations/{auth_id}",
        status_code=404,
    )

    with pytest.raises(httpx.HTTPStatusError):
        await mocked_mpt_client.fetch_authorization(authorization_id=auth_id)


@pytest.mark.asyncio()
async def test_fetch_authorizations(
    httpx_mock, mocked_mpt_client, mtp_client_settings, catalog_authorizations
):
    httpx_mock.add_response(
        method="GET",
        url="https://local.local/v1/catalog/authorizations?eq(product.id,PRD-1111-1111)&limit=50&offset=0",
        json=catalog_authorizations,
    )
    results = []
    async for authorization in mocked_mpt_client.fetch_authorizations():
        results.append(authorization)
    assert results == catalog_authorizations["data"]
    [req] = httpx_mock.get_requests()
    assert req.url == httpx.URL(
        "https://local.local/v1/catalog/authorizations?eq(product.id,PRD-1111-1111)&limit=50&offset=0"
    )
    assert req.headers["Authorization"] == "Bearer fake_token"


@pytest.mark.asyncio()
async def test_fetch_authorizations_404_raises(httpx_mock, mocked_mpt_client):
    httpx_mock.add_response(
        method="GET",
        url="https://local.local/v1/catalog/authorizations?eq(product.id,PRD-1111-1111)&limit=50&offset=0",
        status_code=404,
    )
    with pytest.raises(httpx.HTTPStatusError):  # noqa: PT012
        results = []
        async for authorization in mocked_mpt_client.fetch_authorizations():
            results.append(authorization)
    [req] = httpx_mock.get_requests()
    assert req.url == httpx.URL(
        "https://local.local/v1/catalog/authorizations?eq(product.id,PRD-1111-1111)&limit=50&offset=0"
    )
    assert req.headers["Authorization"] == "Bearer fake_token"


@pytest.mark.asyncio()
async def test_fetch_agreements(httpx_mock, mocked_mpt_client, agreements):
    httpx_mock.add_response(
        method="GET",
        url="https://local.local/v1/commerce/agreements?eq(externalIds.vendor,FORG-6649-3383-1832)&select=parameters&limit=50&offset=0",
        json=agreements,
    )
    results = []
    async for agreement in mocked_mpt_client.fetch_agreements(
        organization_id="FORG-6649-3383-1832"
    ):
        results.append(agreement)
    assert results == agreements["data"]
    [req] = httpx_mock.get_requests()
    assert req.url == httpx.URL(
        "https://local.local/v1/commerce/agreements?eq(externalIds.vendor,FORG-6649-3383-1832)&select=parameters&limit=50&offset=0"
    )
    assert req.headers["Authorization"] == "Bearer fake_token"


@pytest.mark.asyncio()
async def test_fetch_agreements_404_raises(httpx_mock, mocked_mpt_client):
    httpx_mock.add_response(
        method="GET",
        url="https://local.local/v1/commerce/agreements?eq(externalIds.vendor,FORG-6649-3383-1832)&select=parameters&limit=50&offset=0",
        status_code=404,
    )
    with pytest.raises(httpx.HTTPStatusError):  # noqa: PT012
        results = []
        async for agreement in mocked_mpt_client.fetch_agreements(
            organization_id="FORG-6649-3383-1832"
        ):
            results.append(agreement)
    [req] = httpx_mock.get_requests()
    assert req.url == httpx.URL(
        "https://local.local/v1/commerce/agreements?eq(externalIds.vendor,FORG-6649-3383-1832)&select=parameters&limit=50&offset=0"
    )
    assert req.headers["Authorization"] == "Bearer fake_token"


@pytest.mark.asyncio()
async def test_get_journal(httpx_mock, mocked_mpt_client, existing_journal_file_response):
    authorization_id = "AUT-5305-9928"
    external_id = "FORG-6649-3383-1832"

    httpx_mock.add_response(
        method="GET",
        url=f"https://local.local/v1/billing/journals?and(eq(authorization.id,{authorization_id}),"
        f"eq(externalIds.vendor,{external_id}),"
        "ne(status,Deleted)"
        ")",
        json=existing_journal_file_response,
    )
    response = await mocked_mpt_client.get_journal(
        authorization_id=authorization_id, external_id=external_id
    )
    assert response == existing_journal_file_response["data"][0]
    [req] = httpx_mock.get_requests()
    assert req.url == httpx.URL(
        f"https://local.local/v1/billing/journals?and(eq(authorization.id,{authorization_id}),"
        f"eq(externalIds.vendor,{external_id}),"
        "ne(status,Deleted)"
        ")"
    )
    assert req.headers["Authorization"] == "Bearer fake_token"


@pytest.mark.asyncio()
async def test_get_journal_404_raises(httpx_mock, mocked_mpt_client):
    authorization_id = "AUT-5305-9928"
    external_id = "FORG-6649-3383-1832"
    httpx_mock.add_response(
        method="GET",
        url=f"https://local.local/v1/billing/journals?and(eq(authorization.id,{authorization_id}),"
        f"eq(externalIds.vendor,{external_id}),"
        "ne(status,Deleted)"
        ")",
        status_code=404,
    )
    with pytest.raises(httpx.HTTPStatusError):
        await mocked_mpt_client.get_journal(
            authorization_id=authorization_id, external_id=external_id
        )
    [req] = httpx_mock.get_requests()
    assert req.url == httpx.URL(
        f"https://local.local/v1/billing/journals?and(eq(authorization.id,{authorization_id}),"
        f"eq(externalIds.vendor,{external_id}),"
        "ne(status,Deleted)"
        ")"
    )
    assert req.headers["Authorization"] == "Bearer fake_token"


@pytest.mark.asyncio()
async def test_count_active_agreements(httpx_mock, mocked_mpt_client, agreements):
    authorization_id = "AUT-5305-9928"
    start_date = datetime(2025, 1, 1, tzinfo=timezone.utc)
    end_date = datetime(2025, 8, 21, 23, 59, tzinfo=timezone.utc)
    rql = (
        "and("
        f"eq(authorization.id,{authorization_id}),"
        "or("
        f"and(eq(status,'Active'),le(audit.active.at,{fmtd(end_date)})),"
        f"and(eq(status,'Terminated'),le(audit.terminated.at,{fmtd(end_date)}),ge(audit.terminated.at,{fmtd(start_date)}))"
        ")"
        ")"
    )

    httpx_mock.add_response(
        method="GET",
        url=f"https://local.local/v1/commerce/agreements?{rql}&limit=0",
        status_code=200,
        json=agreements,
    )
    response = await mocked_mpt_client.count_active_agreements(
        authorization_id=authorization_id, start_date=start_date, end_date=end_date
    )
    assert response == 1
    [req] = httpx_mock.get_requests()
    assert req.url == httpx.URL(f"https://local.local/v1/commerce/agreements?{rql}&limit=0")
    assert req.headers["Authorization"] == "Bearer fake_token"


@pytest.mark.asyncio()
async def test_count_active_agreements_404_raises(httpx_mock, mocked_mpt_client, agreements):
    authorization_id = "AUT-5305-9928"
    start_date = datetime(2025, 1, 1, tzinfo=timezone.utc)
    end_date = datetime(2025, 8, 21, 23, 59, tzinfo=timezone.utc)
    rql = (
        "and("
        f"eq(authorization.id,{authorization_id}),"
        "or("
        f"and(eq(status,'Active'),le(audit.active.at,{fmtd(end_date)})),"
        f"and(eq(status,'Terminated'),le(audit.terminated.at,{fmtd(end_date)}),ge(audit.terminated.at,{fmtd(start_date)}))"
        ")"
        ")"
    )

    httpx_mock.add_response(
        method="GET",
        url=f"https://local.local/v1/commerce/agreements?{rql}&limit=0",
        status_code=404,
    )
    with pytest.raises(httpx.HTTPStatusError):
        await mocked_mpt_client.count_active_agreements(
            authorization_id=authorization_id, start_date=start_date, end_date=end_date
        )
    [req] = httpx_mock.get_requests()
    assert req.url == httpx.URL(f"https://local.local/v1/commerce/agreements?{rql}&limit=0")
    assert req.headers["Authorization"] == "Bearer fake_token"


@pytest.mark.asyncio()
async def test_count_active_agreements_zero_count(httpx_mock, mocked_mpt_client, agreements):
    authorization_id = "AUT-5305-9928"
    start_date = datetime(2025, 1, 1, tzinfo=timezone.utc)
    end_date = datetime(2025, 8, 21, 23, 59, tzinfo=timezone.utc)
    rql = (
        "and("
        f"eq(authorization.id,{authorization_id}),"
        "or("
        f"and(eq(status,'Active'),le(audit.active.at,{fmtd(end_date)})),"
        f"and(eq(status,'Terminated'),le(audit.terminated.at,{fmtd(end_date)}),ge(audit.terminated.at,{fmtd(start_date)}))"
        ")"
        ")"
    )

    httpx_mock.add_response(
        method="GET",
        url=f"https://local.local/v1/commerce/agreements?{rql}&limit=0",
        status_code=200,
        json={
            "$meta": {
                "pagination": {"offset": 0, "limit": 1000, "total": 0},
                "omitted": [
                    "lines",
                    "assets",
                    "subscriptions",
                    "split",
                    "termsAndConditions",
                    "certificates",
                ],
            },
            "data": [],
        },
    )
    response = await mocked_mpt_client.count_active_agreements(
        authorization_id=authorization_id, start_date=start_date, end_date=end_date
    )
    assert response == 0
    [req] = httpx_mock.get_requests()
    assert req.url == httpx.URL(f"https://local.local/v1/commerce/agreements?{rql}&limit=0")
    assert req.headers["Authorization"] == "Bearer fake_token"


@pytest.mark.asyncio()
async def test_get_journal_by_id(httpx_mock, mocked_mpt_client, existing_journal_file_response):
    journal_id = "BJO-9000-4019"

    httpx_mock.add_response(
        method="GET",
        url=f"https://local.local/v1/billing/journals/{journal_id}",
        json=existing_journal_file_response["data"][0],
    )
    response = await mocked_mpt_client.get_journal_by_id(journal_id=journal_id)
    assert response == existing_journal_file_response["data"][0]
    [req] = httpx_mock.get_requests()
    assert req.url == httpx.URL(f"https://local.local/v1/billing/journals/{journal_id}")
    assert req.headers["Authorization"] == "Bearer fake_token"


@pytest.mark.asyncio()
async def test_get_journal_by_id_404_raises(httpx_mock, mocked_mpt_client):
    journal_id = "BJO-9000-4019"

    httpx_mock.add_response(
        method="GET", url=f"https://local.local/v1/billing/journals/{journal_id}", status_code=404
    )
    with pytest.raises(httpx.HTTPStatusError):
        await mocked_mpt_client.get_journal_by_id(journal_id=journal_id)

    [req] = httpx_mock.get_requests()
    assert req.url == httpx.URL(f"https://local.local/v1/billing/journals/{journal_id}")
    assert req.headers["Authorization"] == "Bearer fake_token"


@pytest.mark.asyncio()
async def test_submit_journal(httpx_mock, mocked_mpt_client, journal_attachment_response):
    journal_id = "BJO-9000-4019"

    httpx_mock.add_response(
        method="POST",
        url=f"https://local.local/v1/billing/journals/{journal_id}/submit",
        status_code=201,
        json=journal_attachment_response,
    )
    await mocked_mpt_client.submit_journal(journal_id=journal_id)
    [req] = httpx_mock.get_requests()
    assert req.url == httpx.URL(f"https://local.local/v1/billing/journals/{journal_id}/submit")
    assert req.headers["Authorization"] == "Bearer fake_token"
    assert req.method == "POST"


@pytest.mark.asyncio()
async def test_submit_journal_404_raises(
    httpx_mock, mocked_mpt_client, journal_attachment_response
):
    journal_id = "BJO-9000-4019"

    httpx_mock.add_response(
        method="POST",
        url=f"https://local.local/v1/billing/journals/{journal_id}/submit",
        status_code=404,
        json=journal_attachment_response,
    )
    with pytest.raises(httpx.HTTPStatusError):
        await mocked_mpt_client.submit_journal(journal_id=journal_id)
    [req] = httpx_mock.get_requests()
    assert req.url == httpx.URL(f"https://local.local/v1/billing/journals/{journal_id}/submit")
    assert req.headers["Authorization"] == "Bearer fake_token"
    assert req.method == "POST"


@pytest.mark.asyncio()
async def test_create_journal(httpx_mock, mocked_mpt_client, create_journal_response):
    external_id = "BJO-9999-9999"
    authorization_id = "AUT-5305-9928"
    httpx_mock.add_response(
        method="POST",
        url="https://local.local/v1/billing/journals",
        status_code=201,
        json=create_journal_response,
    )
    await mocked_mpt_client.create_journal(
        authorization_id=authorization_id,
        external_id=external_id,
        name="test",
        due_date=datetime.now(),
    )
    [req] = httpx_mock.get_requests()
    assert req.url == httpx.URL("https://local.local/v1/billing/journals")
    assert req.headers["Authorization"] == "Bearer fake_token"
    assert req.method == "POST"


@pytest.mark.asyncio()
async def test_create_journal_404_raises(httpx_mock, mocked_mpt_client, create_journal_response):
    external_id = "BJO-9999-9999"
    authorization_id = "AUT-5305-9928"
    httpx_mock.add_response(
        method="POST", url="https://local.local/v1/billing/journals", status_code=404
    )
    with pytest.raises(httpx.HTTPStatusError):
        await mocked_mpt_client.create_journal(
            authorization_id=authorization_id,
            external_id=external_id,
            name="test",
            due_date=datetime.now(),
        )
    [req] = httpx_mock.get_requests()
    assert req.url == httpx.URL("https://local.local/v1/billing/journals")
    assert req.headers["Authorization"] == "Bearer fake_token"
    assert req.method == "POST"


@pytest.mark.asyncio()
async def test_upload_charges(httpx_mock, mocked_mpt_client, create_journal_response):
    journal_id = "BJO-9999-9999"
    charges_file = BytesIO(b'{"charge": 123}\n{"charge": 456}\n')
    charges_file.name = "charges.jsonl"
    httpx_mock.add_response(
        method="POST",
        url=f"https://local.local/v1/billing/journals/{journal_id}/upload",
        status_code=201,
    )
    await mocked_mpt_client.upload_charges(journal_id=journal_id, charges_file=charges_file)
    [req] = httpx_mock.get_requests()
    assert req.url == httpx.URL(f"https://local.local/v1/billing/journals/{journal_id}/upload")
    assert req.headers["Authorization"] == "Bearer fake_token"
    assert req.method == "POST"
    assert b"charges.jsonl" in req.content
    assert b'{"charge": 123}' in req.content


@pytest.mark.asyncio()
async def test_upload_charges_404_raises(httpx_mock, mocked_mpt_client, create_journal_response):
    journal_id = "BJO-9999-9999"
    charges_file = BytesIO(b'{"charge": 123}\n{"charge": 456}\n')
    charges_file.name = "charges.jsonl"
    httpx_mock.add_response(
        method="POST",
        url=f"https://local.local/v1/billing/journals/{journal_id}/upload",
        status_code=404,
    )
    with pytest.raises(httpx.HTTPStatusError):
        await mocked_mpt_client.upload_charges(journal_id=journal_id, charges_file=charges_file)
    [req] = httpx_mock.get_requests()
    assert req.url == httpx.URL(f"https://local.local/v1/billing/journals/{journal_id}/upload")
    assert req.headers["Authorization"] == "Bearer fake_token"
    assert req.method == "POST"


@pytest.mark.asyncio()
async def test_fetch_journal_attachments(
    httpx_mock, mocked_mpt_client, journal_attachment_response
):
    journal_id = "BJO-9000-4019"
    file_prefix = "test_attachment"
    httpx_mock.add_response(
        method="GET",
        url=f"https://local.local/v1/billing/journals/{journal_id}/attachments?like(name,{file_prefix}*)",
        json=journal_attachment_response,
    )
    response = await mocked_mpt_client.fetch_journal_attachment(
        journal_id=journal_id, file_prefix=file_prefix
    )
    assert response == journal_attachment_response["data"][0]
    [req] = httpx_mock.get_requests()
    assert req.url == httpx.URL(
        f"https://local.local/v1/billing/journals/{journal_id}/attachments?like(name,{file_prefix}*)"
    )
    assert req.headers["Authorization"] == "Bearer fake_token"


@pytest.mark.asyncio()
async def test_fetch_journal_attachments_return_none(
    httpx_mock, mocked_mpt_client, journal_attachment_response
):
    journal_id = "BJO-9000-4019"
    file_prefix = "test_attachment"
    httpx_mock.add_response(
        method="GET",
        url=f"https://local.local/v1/billing/journals/{journal_id}/attachments?like(name,{file_prefix}*)",
        json={
            "$meta": {
                "pagination": {"offset": 0, "limit": 10, "total": 1},
                "omitted": ["processing", "audit"],
            },
            "data": [],
        },
    )
    response = await mocked_mpt_client.fetch_journal_attachment(
        journal_id=journal_id, file_prefix=file_prefix
    )
    assert response is None
    [req] = httpx_mock.get_requests()
    assert req.url == httpx.URL(
        f"https://local.local/v1/billing/journals/{journal_id}/attachments?like(name,{file_prefix}*)"
    )
    assert req.headers["Authorization"] == "Bearer fake_token"


@pytest.mark.asyncio()
async def test_fetch_journal_attachments_404_raises(
    httpx_mock, mocked_mpt_client, journal_attachment_response
):
    journal_id = "BJO-9000-4019"
    file_prefix = "test_attachment"
    httpx_mock.add_response(
        method="GET",
        url=f"https://local.local/v1/billing/journals/{journal_id}/attachments?like(name,{file_prefix}*)",
        status_code=404,
    )
    with pytest.raises(httpx.HTTPStatusError):
        await mocked_mpt_client.fetch_journal_attachment(
            journal_id=journal_id, file_prefix=file_prefix
        )
    [req] = httpx_mock.get_requests()
    assert req.url == httpx.URL(
        f"https://local.local/v1/billing/journals/{journal_id}/attachments?like(name,{file_prefix}*)"
    )
    assert req.headers["Authorization"] == "Bearer fake_token"


@pytest.mark.asyncio()
async def test_delete_journal_attachment(
    httpx_mock, mocked_mpt_client, journal_attachment_response
):
    journal_id = "BJO-9000-4019"
    attachment_id = "JOA-5985-1983"
    httpx_mock.add_response(
        method="DELETE",
        url=f"https://local.local/v1/billing/journals/{journal_id}/attachments/{attachment_id}",
        status_code=204,
    )
    await mocked_mpt_client.delete_journal_attachment(
        journal_id=journal_id, attachment_id=attachment_id
    )
    [req] = httpx_mock.get_requests()
    assert req.url == httpx.URL(
        f"https://local.local/v1/billing/journals/{journal_id}/attachments/{attachment_id}"
    )
    assert req.headers["Authorization"] == "Bearer fake_token"


@pytest.mark.asyncio()
async def test_delete_journal_attachment_404_raises(
    httpx_mock, mocked_mpt_client, journal_attachment_response
):
    journal_id = "BJO-9000-4019"
    attachment_id = "JOA-5985-1983"
    httpx_mock.add_response(
        method="DELETE",
        url=f"https://local.local/v1/billing/journals/{journal_id}/attachments/{attachment_id}",
        status_code=404,
    )
    with pytest.raises(httpx.HTTPStatusError):
        await mocked_mpt_client.delete_journal_attachment(
            journal_id=journal_id, attachment_id=attachment_id
        )
    [req] = httpx_mock.get_requests()
    assert req.url == httpx.URL(
        f"https://local.local/v1/billing/journals/{journal_id}/attachments/{attachment_id}"
    )
    assert req.headers["Authorization"] == "Bearer fake_token"


@pytest.mark.asyncio()
async def test_create_journal_attachment(httpx_mock, mocked_mpt_client, exchange_rates):
    journal_id = "BJO-9000-4019"
    filename = "test_filename-2025-08-21"
    httpx_mock.add_response(
        method="POST",
        url=f"https://local.local/v1/billing/journals/{journal_id}/attachments",
        status_code=201,
    )
    await mocked_mpt_client.create_journal_attachment(
        journal_id=journal_id, filename=filename, json_data=exchange_rates
    )
    [req] = httpx_mock.get_requests()
    assert req.method == "POST"
    assert req.url == httpx.URL(f"https://local.local/v1/billing/journals/{journal_id}/attachments")
    assert req.headers["Authorization"] == "Bearer fake_token"

    ctype = req.headers["Content-Type"]
    assert ctype.startswith("multipart/form-data; boundary=")
    boundary = ctype.split("boundary=")[1]
    assert boundary.startswith("----")

    body = req.content
    assert f'filename="{filename}.json"'.encode() in body
    assert (
        b'{"name": "' + filename.encode() + b'", "description": "Currency conversion rates"}'
        in body
    )
    assert f"--{boundary}--\r\n".encode() in body


@pytest.mark.asyncio()
async def test_create_journal_attachment_404_raises(httpx_mock, mocked_mpt_client, exchange_rates):
    journal_id = "BJO-9000-4019"
    filename = "test_filename-2025-08-21"
    httpx_mock.add_response(
        method="POST",
        url=f"https://local.local/v1/billing/journals/{journal_id}/attachments",
        status_code=404,
    )
    with pytest.raises(httpx.HTTPStatusError):
        await mocked_mpt_client.create_journal_attachment(
            journal_id=journal_id, filename=filename, json_data=exchange_rates
        )
    [req] = httpx_mock.get_requests()
    assert req.method == "POST"
    assert req.url == httpx.URL(f"https://local.local/v1/billing/journals/{journal_id}/attachments")
    assert req.headers["Authorization"] == "Bearer fake_token"
