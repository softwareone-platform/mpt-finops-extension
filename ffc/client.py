import logging
import os
from datetime import datetime, timedelta, timezone
from functools import wraps
from typing import Any
from urllib.parse import urljoin
from uuid import uuid4

import aiofiles
import httpx
import jwt
import requests
from async_lru import alru_cache
from requests import HTTPError

logger = logging.getLogger(__name__)


class FinOpsError(Exception):
    pass


class FinOpsHttpError(FinOpsError):
    def __init__(self, status_code: int, content: str):
        self.status_code = status_code
        self.content = content
        super().__init__(f"{self.status_code} - {self.content}")


class FinOpsNotFoundError(FinOpsHttpError):
    def __init__(self, content):
        super().__init__(404, content)


def wrap_http_error(func):
    @wraps(func)
    def _wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except HTTPError as e:
            if e.response.status_code == 404:
                raise FinOpsNotFoundError(e.response.json())
            else:
                raise FinOpsHttpError(e.response.status_code, e.response.json())

    return _wrapper


class FinOpsClient:
    def __init__(self, base_url, sub, secret):
        self._sub = sub
        self._secret = secret
        self._api_base_url = base_url

        self._jwt = None

    @wrap_http_error
    def get_employee(self, email):
        headers = self._get_headers()
        response = requests.get(
            urljoin(self._api_base_url, f"/ops/v1/employees/{email}"),
            headers=headers,
        )

        response.raise_for_status()

        return response.json()

    @wrap_http_error
    def create_employee(self, email, name):
        headers = self._get_headers()

        response = requests.post(
            urljoin(self._api_base_url, "/ops/v1/employees"),
            headers=headers,
            json={
                "email": email,
                "display_name": name,
            },
        )

        response.raise_for_status()

        return response.json()

    @wrap_http_error
    def create_organization(
        self,
        name,
        currency,
        billing_currency,
        external_id,
        user_id,
    ):
        headers = self._get_headers()

        response = requests.post(
            urljoin(self._api_base_url, "/ops/v1/organizations"),
            headers=headers,
            json={
                "name": name,
                "currency": currency,
                "billing_currency": billing_currency,
                "operations_external_id": external_id,
                "user_id": user_id,
            },
        )

        response.raise_for_status()

        return response.json()

    @wrap_http_error
    def delete_organization(self, organization_id):
        headers = self._get_headers()

        response = requests.delete(
            urljoin(self._api_base_url, f"/ops/v1/organizations/{organization_id}"),
            headers=headers,
        )

        response.raise_for_status()

    @wrap_http_error
    def get_organizations_by_external_id(self, agreement_id):
        headers = self._get_headers()

        rql_filter = f"eq(operations_external_id,{agreement_id})"
        response = requests.get(
            urljoin(
                self._api_base_url,
                f"/ops/v1/organizations?{rql_filter}&limit=1",
            ),
            headers=headers,
        )

        response.raise_for_status()

        return response.json()["items"]

    def _get_headers(self):
        return {
            "Authorization": f"Bearer {self._get_auth_token()}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-Request-Id": str(uuid4()),
        }

    def _get_auth_token(self):
        if not self._jwt or self._is_token_expired():
            now = datetime.now(tz=timezone.utc)
            self._jwt = jwt.encode(
                {
                    "sub": self._sub,
                    "exp": now + timedelta(minutes=5),
                    "nbf": now,
                    "iat": now,
                },
                self._secret,
                algorithm="HS256",
            )

        return self._jwt

    def _is_token_expired(self):
        try:
            jwt.decode(self._jwt, self._secret, algorithms=["HS256"])
            return False
        except jwt.ExpiredSignatureError:
            return True

class HttpxMTPAPIClient:
    def __init__(self, base_url: str, mtp_token: str):
        self.api_base_url = base_url
        self.client = httpx.AsyncClient(base_url=self.api_base_url)
        self.headers = {"Authorization": f"Bearer {mtp_token}"}
    @alru_cache
    async def fetch_subscription_and_agreement_details(
        self, subscription_search_value
    ):
        endpoint = (
            self.api_base_url
            + f"/public/v1/commerce/subscriptions?eq(externalIds.vendor,"
              f"{subscription_search_value})&select=agreement,agreement.parameters"
        )
        try:
            response = await self.client.get(url=endpoint, headers=self.headers)
            response.raise_for_status()
            data = response.json()
            return data.get("data")
        except httpx.HTTPError as error:
            logger.exception(f"Request to get subscription details: {error}")
            return None


class HttpxFFCAPIClient:
    """
    HTTPX API Client
    """

    def __init__(self, base_url: str, sub, secret):
        self.api_base_url = base_url
        self._sub = sub
        self._secret = secret
        self._jwt = None
        self.client = httpx.AsyncClient(base_url=self.api_base_url)

    async def get_generated_charge_files(self) -> list[dict[str, Any]] | None:
        """
        This method fetches the charges files in the GENERATED Status.
        This status means that the charges files have been generated but
        not yet processed by the billing procedure.
        Raises:
        """
        try:
            headers = self._get_headers()
            rql_filter = "eq(status,generated)"
            endpoint = f"{self.api_base_url}/ops/v1/charges?{rql_filter}"
            response = await self.client.get(headers=headers, url=endpoint)
            response.raise_for_status()
            data = response.json()
            return data.get("items", [])
        except httpx.HTTPError as error:
            logger.exception(f"Request to get charge files failed: {error}")
            return None

    async def download_charges_file(
        self, charge_file_id: str, download_folder: str
    ) -> str | None:
        """
        This method downloads asynchronously downloads a charge file from the FFC_OPERATIONS API
        and stores it as a zip file in a temporary directory.
        Args:
            charge_file_id:  The charge file id.
            download_folder: The temporary directory to store the downloaded zip file.
        """
        initial_url = f"{self.api_base_url}/ops/v1/charges/{charge_file_id}/download"
        headers = self._get_headers()
        try:
            response = await self.client.get(initial_url, headers=headers)
            if response.status_code != 307:
                logger.error(
                    f"Unexpected status code {response.status_code} for {charge_file_id}"
                )
                return None
            redirect_url = response.headers[
                "Location"
            ]  # extract the download url location from the headers
            url_response = await self.client.get(
                redirect_url
            )  # the URL has a short-lived sas token
            if url_response.status_code != 200:
                logger.error(
                    f"Failed to download  {charge_file_id}, status: {url_response.status_code}"
                )
                return None
            file_path = os.path.join(download_folder, f"{charge_file_id}.zip")
            return await self._stream_response_to_file(url_response, file_path)
        except Exception as error:
            logger.exception(f"Error downloading {charge_file_id}: {error}")
            return None

    def _get_headers(self):
        """
        This method builds the required headers
        for the authenticated request.
        """
        return {
            "Authorization": f"Bearer {self._get_auth_token()}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-Request-Id": str(uuid4()),
        }

    def _get_auth_token(self):
        """
        This method builds the required JWT
        """
        if not self._jwt or self._is_token_expired():
            now = datetime.now(tz=timezone.utc)
            self._jwt = jwt.encode(
                {
                    "sub": self._sub,
                    "exp": now + timedelta(minutes=5),
                    "nbf": now,
                    "iat": now,
                },
                self._secret,
                algorithm="HS256",
            )

        return self._jwt

    def _is_token_expired(self):
        try:
            jwt.decode(self._jwt, self._secret, algorithms=["HS256"])
            return False
        except jwt.ExpiredSignatureError:
            return True

    @staticmethod
    async def _stream_response_to_file(
        response: httpx.Response, file_path, chunk_size=1024
    ):
        """
        This function reads the response in chunks and writes it to a file asynchronously.
        """
        async with aiofiles.open(file_path, "wb") as file:
            async for chunk in response.aiter_bytes(chunk_size=chunk_size):
                await file.write(chunk)
        logger.info(f"Charge File Downloaded and saved: {file_path}")
        return file_path

    async def close(self):
        """Close the client connection."""
        await self.client.aclose()


_FFC_CLIENT = None
_HTTPX_FFC_API_CLIENT = None
_HTTPX_MTP_API_CLIENT = None


def get_httpx_ffc_api_client():
    """
    This returns an instance of the HttpxFFCAPIClient class.
    """
    from django.conf import settings

    global _HTTPX_FFC_API_CLIENT
    if not _HTTPX_FFC_API_CLIENT:
        _HTTPX_FFC_API_CLIENT = HttpxFFCAPIClient(
            base_url=settings.EXTENSION_CONFIG["FFC_OPERATIONS_API_BASE_URL"],
            sub=settings.EXTENSION_CONFIG["FFC_SUB"],
            secret=settings.EXTENSION_CONFIG["FFC_OPERATIONS_SECRET"],
        )

    return _HTTPX_FFC_API_CLIENT

def get_httpx_mtp_api_client():
    """
    This returns an instance of the HttpxMTPAPIClient class.
    """
    from django.conf import settings

    global _HTTPX_MTP_API_CLIENT
    if not _HTTPX_MTP_API_CLIENT:
        _HTTPX_MTP_API_CLIENT = HttpxMTPAPIClient(
            base_url=settings.EXTENSION_CONFIG["MPT_API_BASE_URL"],
            mtp_token=settings.EXTENSION_CONFIG["MPT_API_TOKEN"]
        )

    return _HTTPX_MTP_API_CLIENT

def get_ffc_client():
    """
    Returns an instance of the `FinOpsClient`.

    Returns:
        FinOpsClient: An instance of the `FinOpsClient`.
    """
    from django.conf import settings

    global _FFC_CLIENT
    if not _FFC_CLIENT:
        _FFC_CLIENT = FinOpsClient(
            settings.EXTENSION_CONFIG["FFC_OPERATIONS_API_BASE_URL"],
            settings.EXTENSION_CONFIG["FFC_SUB"],
            settings.EXTENSION_CONFIG["FFC_OPERATIONS_SECRET"],
        )

    return _FFC_CLIENT
