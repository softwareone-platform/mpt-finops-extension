from abc import ABC, abstractmethod
from functools import cached_property

import httpx
from httpx_retries import Retry, RetryTransport


class PaginationSupportMixin(ABC):
    @abstractmethod
    def get_pagination_meta(self, response):
        raise NotImplementedError("base_url property must be implemented in subclasses")

    @abstractmethod
    def get_page_data(self, response):
        raise NotImplementedError("base_url property must be implemented in subclasses")


class BaseAsyncAPIClient(ABC):

    def __init__(self, limit: int = 50):
        self.limit = limit

    @property
    @abstractmethod
    def base_url(self):
        raise NotImplementedError("base_url property must be implemented in subclasses")

    @property
    @abstractmethod
    def auth(self):
        raise NotImplementedError("base_url property must be implemented in subclasses")

    @cached_property
    def httpx_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self.base_url,
            auth=self.auth,
            timeout=httpx.Timeout(connect=5.0, read=180.0, write=5.0, pool=5.0),
            transport=RetryTransport(retry=Retry(total=5, backoff_factor=0.5)),
        )

    async def collection_iterator(self, endpoint, rql=""):
        offset = 0
        data = None
        while True:
            ep = f"{endpoint}?{rql}&limit={self.limit}&offset={offset}"
            page_response = await self.httpx_client.get(ep)
            page_response.raise_for_status()
            data = page_response.json()

            items = self.get_page_data(data)

            for item in items:
                yield item

            pagination_meta = self.get_pagination_meta(data)
            total = pagination_meta["total"]
            if total <= self.limit + offset:
                break

            offset += self.limit

    async def close(self):
        await self.httpx_client.aclose()
