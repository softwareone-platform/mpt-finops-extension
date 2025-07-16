import json
import secrets
from collections.abc import AsyncGenerator, Generator
from datetime import datetime
from typing import Any

import httpx
from django.conf import settings

from ffc.clients.base import BaseAsyncAPIClient, PaginationSupportMixin


def fmtd(d: datetime):
    return d.strftime("%Y-%m-%dT%H:%M:%SZ")


class MPTClientAuth(httpx.Auth):
    def auth_flow(self, request: httpx.Request) -> Generator[httpx.Request, httpx.Response, None]:
        request.headers["Authorization"] = f"Bearer {settings.MPT_API_TOKEN}"
        yield request


class MPTAsyncClient(BaseAsyncAPIClient, PaginationSupportMixin):
    @property
    def base_url(self):
        return f"{settings.MPT_API_BASE_URL}/v1"

    @property
    def auth(self):
        return MPTClientAuth()

    def get_pagination_meta(self, response):
        return response["$meta"]["pagination"]

    def get_page_data(self, response):
        return response["data"]

    async def fetch_authorization(
        self,
        authorization_id: str,
    ) -> dict[str, Any]:
        response = await self.httpx_client.get(f"/catalog/authorizations/{authorization_id}")
        response.raise_for_status()
        return response.json()

    def fetch_authorizations(
        self,
    ) -> AsyncGenerator[dict[str, Any]]:
        return self.collection_iterator(
            "/catalog/authorizations",
            rql=f"eq(product.id,{settings.MPT_PRODUCTS_IDS[0]})"
        )

    def fetch_agreements(
        self, organization_id: str
    ) -> AsyncGenerator[dict[str, Any], None]:
        rql = (
            f"eq(externalIds.vendor,{organization_id})"
            "&select=parameters"
        )
        return self.collection_iterator("/commerce/agreements", rql)

    async def count_active_agreements(
        self,
        authorization_id: str,
        start_date: datetime,
        end_date: datetime,
    ):
        rql = (
            "or("
            f"and(eq(authorization.id,{authorization_id}),eq(status,Active),le(audit.active.at,{fmtd(end_date)})),"
            f"and(eq(status,Terminated),le(audit.terminated.at,{fmtd(end_date)}),ge(audit.terminated.at,{fmtd(start_date)}))"
            ")"
        )

        response = await self.httpx_client.get(
            f"/commerce/agreements?{rql}&limit=0",
        )
        response.raise_for_status()
        pagination_meta = self.get_pagination_meta(response.json())
        return pagination_meta["total"]

    async def get_journal(self, authorization_id: str, external_id: str) -> dict[str, Any]:
        rql = (
            "and("
            f"eq(authorization.id,{authorization_id}),"
            f"eq(externalIds.vendor,{external_id}),"
            "ne(status,Deleted)"
            ")"
        )
        response = await self.httpx_client.get(f"/billing/journals?{rql}")
        response.raise_for_status()
        data = self.get_page_data(response.json())
        return data[0] if data else None

    async def get_journal_by_id(self, journal_id: str) -> dict[str, Any]:
        response = await self.httpx_client.get(f"/billing/journals/{journal_id}")
        response.raise_for_status()
        return response.json()

    async def submit_journal(self, journal_id: str) -> None:
        response = await self.httpx_client.post(f"/billing/journals/{journal_id}/submit")
        response.raise_for_status()

    async def create_journal(
        self, authorization_id: str, external_id: str, name: str, due_date: datetime
    ) -> dict[str, Any]:
        response = await self.httpx_client.post(
            "/billing/journals",
            json={
                "authorization": {"id": authorization_id},
                "externalIds": {"vendor": external_id},
                "name": name,
                "dueDate": due_date.isoformat(),
            },
        )
        response.raise_for_status()
        return response.json()

    async def upload_charges(self, journal_id: str, charges_file: Any) -> None:
        response = await self.httpx_client.post(
            f"/billing/journals/{journal_id}/upload",
            files={
                "file": (charges_file.name, charges_file, "application/jsonl"),
            },
        )
        response.raise_for_status()

    async def fetch_journal_attachment(
        self, journal_id: str, file_prefix: str
    ) -> dict[str, Any] | None:
        response = await self.httpx_client.get(
            f"/billing/journals/{journal_id}/attachments?like(name,{file_prefix}*)"
        )
        response.raise_for_status()
        data = self.get_page_data(response.json())
        return data[0] if data else None

    async def delete_journal_attachment(self, journal_id: str, attachment_id: str) -> None:
        response = await self.httpx_client.delete(
            f"/billing/journals/{journal_id}/attachments/{attachment_id}"
        )
        response.raise_for_status()

    async def create_journal_attachment(self, journal_id: str, filename: str, json_data: str):
        boundary = f"----{secrets.token_hex(8)}"
        # Data parts
        attachment_content = json.dumps(
            {"name": filename, "description": "Currency conversion rates"}
        )
        body = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="{filename}.json"\r\n'
            "Content-Type: application/json\r\n"
            "\r\n"
            f"{json_data}\r\n"
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="attachment"\r\n'
            "Content-Type: application/json\r\n"
            "\r\n"
            f"{attachment_content}\r\n"
            f"--{boundary}--\r\n"
        ).encode()

        response = await self.httpx_client.post(
            f"/billing/journals/{journal_id}/attachments",
            content=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )
        response.raise_for_status()
