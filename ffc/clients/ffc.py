from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import jwt
from django.conf import settings

from ffc.clients.base import BaseAsyncAPIClient, PaginationSupportMixin


class FFCOpsAuth(httpx.Auth):
    requires_response_body = True

    def __init__(self):
        self.jwt_token = None
        self.generate_jwt_token()

    def generate_jwt_token(self):
        now = datetime.now(UTC)
        self.jwt_token = jwt.encode(
            {
                "sub": settings.EXTENSION_CONFIG["FFC_SUB"],
                "exp": now + timedelta(minutes=5),
                "nbf": now,
                "iat": now,
            },
            settings.EXTENSION_CONFIG["FFC_OPERATIONS_SECRET"],
            algorithm="HS256",
        )

    async def async_auth_flow(
        self, request: httpx.Request
    ) -> AsyncGenerator[httpx.Request, httpx.Response]:
        request.headers["Authorization"] = f"Bearer {self.jwt_token}"
        response = yield request

        if response.status_code == 401:
            self.generate_jwt_token()

            # Retry the original request with the new token
            request.headers["Authorization"] = f"Bearer {self.jwt_token}"
            yield request


class FFCAsyncClient(BaseAsyncAPIClient, PaginationSupportMixin):
    @property
    def base_url(self):
        return settings.EXTENSION_CONFIG["FFC_OPERATIONS_API_BASE_URL"]

    @property
    def auth(self):
        return FFCOpsAuth()

    def get_pagination_meta(self, response):
        return response

    def get_page_data(self, response):
        return response["items"]

    def fetch_organizations(
        self,
        billing_currency: str,
    ) -> AsyncGenerator[dict[str, Any], None]:
        return self.collection_iterator(
            "/organizations", f"eq(billing_currency,{billing_currency})"
        )

    def fetch_organization_expenses(
        self, organization_id: str, year: int, month: int
    ) -> AsyncGenerator[dict[str, Any], None]:
        rql_filter = (
            "and("
            f"eq(organization.id,{organization_id}),"
            f"eq(year,{year}),"
            f"eq(month,{month})"
            ")"
            "&order_by(linked_datasource_id)"
        )
        return self.collection_iterator("/expenses", rql=rql_filter)

    async def fetch_entitlement(
        self,
        organization_id: str,
        datasource_id: str,
        datasource_type: str,
        start_date: datetime,
        end_date: datetime,
    ):
        rql = (
            "and("
            f"eq(datasource_id,{datasource_id}),"  # change to datasource_id
            f"eq(events.redeemed.by.id,{organization_id}),"
            f"eq(linked_datasource_type,{datasource_type}),"
            f"lt(events.redeemed.at,{(end_date + timedelta(days=1)).isoformat()}),"
            f"or(eq(status,active),gte(events.terminated.at,{start_date.isoformat()}))"
            ")"
        )
        response = await self.httpx_client.get(f"/entitlements?{rql}")
        response.raise_for_status()
        data = self.get_page_data(response.json())
        return data[0] if data else None
