import httpx
import pytest

from ffc.clients.base import BaseAsyncAPIClient, PaginationSupportMixin


@pytest.mark.asyncio()
async def test_collection_iterator_paginates(httpx_mock, fake_apiclient):
    endpoint = "/catalog/authorizations"
    rql = "eq(mytestfield,'value')"

    httpx_mock.add_response(
        method="GET",
        url=f"https://local.local/v1/catalog/authorizations?{rql}&limit=2&offset=0",
        json={
            "data": [
                {"id": "AUT-1111-1111", "name": "test_1"},
                {"id": "AUT-2222-2222", "name": "test_2"},
            ],
            "meta": {"pagination": {"offset": 0, "limit": 2, "total": 3}, "omitted": ["audit"]},
        },
        status_code=200,
    )
    httpx_mock.add_response(
        method="GET",
        url=f"https://local.local/v1/catalog/authorizations?{rql}&limit=2&offset=2",
        json={
            "data": [
                {"id": "AUT-3333-3333", "name": "test_3"},
            ],
            "meta": {"pagination": {"offset": 2, "limit": 2, "total": 3}, "omitted": ["audit"]},
        },
        status_code=200,
    )

    items = []
    async for item in fake_apiclient.collection_iterator(endpoint, rql=rql):
        items.append(item)

    assert [item["id"] for item in items] == ["AUT-1111-1111", "AUT-2222-2222", "AUT-3333-3333"]

    reqs = httpx_mock.get_requests()
    assert [r.method for r in reqs] == ["GET", "GET"]
    assert [str(r.url) for r in reqs] == [
        f"https://local.local/v1/catalog/authorizations?{rql}&limit=2&offset=0",
        f"https://local.local/v1/catalog/authorizations?{rql}&limit=2&offset=2",
    ]
    for r in reqs:
        assert r.headers["Authorization"] == "Bearer fake token"

    await fake_apiclient.close()
    assert fake_apiclient.httpx_client.is_closed


@pytest.mark.asyncio()
async def test_collection_iterator_paginates_404(httpx_mock, fake_apiclient):
    endpoint = "/catalog/authorizations"
    rql = "eq(mytestfield,'value')"

    httpx_mock.add_response(
        method="GET",
        url=f"https://local.local/v1/catalog/authorizations?{rql}&limit=2&offset=0",
        status_code=404,
    )

    with pytest.raises(httpx.HTTPStatusError):
        await anext(fake_apiclient.collection_iterator(endpoint, rql=rql))
    [req] = httpx_mock.get_requests()
    assert req.method == "GET"
    assert str(req.url) == f"https://local.local/v1/catalog/authorizations?{rql}&limit=2&offset=0"
    assert req.headers["Authorization"] == "Bearer fake token"

    await fake_apiclient.close()
    assert fake_apiclient.httpx_client.is_closed


def test_cannot_instantiate_paginationsupportmixin_directly():
    with pytest.raises(TypeError):
        _ = PaginationSupportMixin()


def test_abstract_baseapiclient_methods_raise_notimplemented():
    class TestClass(BaseAsyncAPIClient):
        def base_url(self):
            return super().base_url()

        def auth(self):
            return super().auth()

    tmp = TestClass()

    with pytest.raises(NotImplementedError):
        tmp.base_url()

    with pytest.raises(NotImplementedError):
        tmp.auth()


def test_abstract_paginationsupportmixin_methods_raise_notimplemented():
    class TestClass(PaginationSupportMixin):
        def get_pagination_meta(self, response):
            return super().get_pagination_meta(response)

        def get_page_data(self, response):
            return super().get_page_data(response)

    tmp = TestClass()

    with pytest.raises(NotImplementedError):
        tmp.get_pagination_meta({"meta": {}})

    with pytest.raises(NotImplementedError):
        tmp.get_page_data({"data": []})
