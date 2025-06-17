import calendar
import functools
import json
import logging
from collections import defaultdict
from datetime import UTC, datetime, timedelta, timezone
from functools import wraps
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urljoin
from uuid import uuid4

import aiofiles
import httpx
import jwt
import requests
from dateutil.relativedelta import relativedelta
from requests import HTTPError

logger = logging.getLogger(__name__)

exchange_rates_cache = defaultdict(dict)

def cache_exchange_rate(cache):
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(self, currency: str):
            if currency in cache:
                return cache[currency]
            result = await func(self, currency)
            if result is not None:
                cache[currency] = result
            return result
        return wrapper
    return decorator


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


class ExchangeRateClient:
    def __init__(self, base_url: str, api_key: str):
        self.api_base_url = base_url
        self.api_key = api_key
        self.client = httpx.AsyncClient(base_url=self.api_base_url)

    @cache_exchange_rate(exchange_rates_cache)
    async def fetch_exchange_rate(self, currency: str):
        """
        This method will fetch an exchange rate from
        https://app.exchangerate-api.com/
        """

        endpoint = self.api_base_url + f"{self.api_key}/latest/{currency}"
        try:
            response = await self.client.get(
                url=endpoint,
            )
            response.raise_for_status()
            data = response.json()
            return data
        except httpx.HTTPError as error:
            logger.exception(f"Exchange request failed: {error}")
            return None


class HttpxMTPAPIClient:
    def __init__(self, base_url: str, mtp_token: str):
        self.api_base_url = base_url
        self.client = httpx.AsyncClient(base_url=self.api_base_url)
        self.headers = {"Authorization": f"Bearer {mtp_token}"}

    async def fetch_authorizations(
        self, product_id: str, authorization_id: str | None = None
    ) -> list[dict[str, Any]] | None:
        rql_filter = f"eq(product_id,{product_id})"
        if authorization_id is not None:
            rql_filter += (
                f"and(eq(authorization_id,{authorization_id})eq(product_id,{product_id}))"
            )
        endpoint = self.api_base_url + f"/public/v1/catalog/authorizations?{rql_filter}"
        return await self._send_request(method="GET", endpoint=endpoint)

    async def fetch_agreement_details_by_authorization(self, authorization_id: str, organization_id: str) -> list[dict[str, Any]] | None:
        endpoint = (
            self.api_base_url + f"/public/v1/commerce/agreements?and(eq(authorization.id,"
            f"{authorization_id}),eq(externalIds.vendor,{organization_id})&select=parameters"
        )
        return await self._send_request(method="GET", endpoint=endpoint)

    async def get_journal_file(self, authorization_id: str, external_vendor_id: str):
        endpoint = (
            self.api_base_url + f"/public/v1/billing/journals?and(eq(authorization.id,"
            f"{authorization_id}),eq(externalIds.vendor,{external_vendor_id}))"
        )
        return await self._send_request(method="GET", endpoint=endpoint)

    async def create_journal(self, authorization_id: str, month: int, year: int) -> dict[str, Any]:
        """

        This method will create a new journal.
        Args
            authorization_id (str): The authorization ID
            month (int): The month
            year (int): The year
        Returns: dict[str, Any]
        https://softwareone.atlassian.net/wiki/spaces/mpt/pages/5952733474/Journal+Object#Example

        """
        endpoint = self.api_base_url + "/public/v1/billing/journals"
        month_name = calendar.month_name[month]

        billing_period = datetime(year, month, 1, tzinfo=UTC)
        due_date = billing_period + relativedelta(months=1)

        payload = {
            "name": f"{month_name} {year} Charges",
            "authorization": {"id": authorization_id},
            "dueDate": due_date.isoformat(),
            "externalIds": {"vendor": f"{year}{month}"},
        }

        return await self._send_request(
            method="POST", endpoint=endpoint, payload=payload, extract_data=False
        )

    async def delete_journal_attachment(self, journal_id: str, attachment_id: str):
        endpoint = self.api_base_url + f"/public/v1/billing/journals/{journal_id}/attachments/{attachment_id}"
        return await self._send_request(method="DELETE", endpoint=endpoint, extract_data=False)

    async def upload_journal(
        self, journal_id: str, file_path: str, description: str
    ) -> dict[str, Any] | None:
        """
        This method will upload the given journal.
        Args:
            journal_id (str): The journal ID to upload.
            file_path (str): The path to the file to upload.
            description (str): The description of the journal.

        Returns: dict[str, Any] or None if an error occurred.
        """
        endpoint = self.api_base_url + f"/public/v1/billing/journals/{journal_id}/upload"
        try:
            file = Path(file_path)
            if not file.is_file():
                logger.error(f"File path not found: {file}")
                return None

            attachment_json = {
                "name": file.name,  # EUR_202504
                "description": description,
                "filename": file.name,
                "size": 0,
            }

            async with aiofiles.open(file, "rb") as f:
                file_binary = await f.read()
            files = {
                "file": (file.name, file_binary, "application/jsonl"),
                "attachment": (None, json.dumps(attachment_json), "application/jsonl"),
            }

            response = await self._send_request(
                method="POST",
                endpoint=endpoint,
                headers={
                    "Content-Type": f"multipart/form-data;boundary=boundary{str(uuid4())}"
                },
                files=files,
                payload=None,
                extract_data=False,
            )

            if response:
                logger.info("File uploaded successfully.")
                return response
            logger.error("Upload failed: No response or error.")
            return None
        except Exception:
            logger.exception("Exception occurred during file upload.")
            return None

    async def submit_journal(self, journal_id: str):
        """
        Submit a Journal for review by SWO.
        Journals can be submitted when they are in the Ready status.
        As a result, the status will change to Review.
        Reference:
        https://softwareone.atlassian.net/wiki/spaces/mpt/pages/5930124021/Billing+module.+API#Endpoints
        """
        endpoint = self.api_base_url + f"/public/v1/billing/journals/{journal_id}/submit"

        return await self._send_request(
            method="POST", endpoint=endpoint, payload=None, extract_data=False
        )

    async def fetch_journal_attachments(
        self, journal_id: str, filename: str
    ) -> list[dict[str, Any]]:
        endpoint = (
            self.api_base_url
            + f"/public/v1/billing/journals/{journal_id}/attachments?eq(name,{filename})"
        )
        return await self._send_request(method="GET", endpoint=endpoint)

    async def delete_journal_attachments(self, journal_id: str, attachment_id: str) -> None:
        endpoint = (
            self.api_base_url
            + f"/public/v1/billing/journals/{journal_id}/attachments/{attachment_id}"
        )
        return await self._send_request(
            method="DELETE", endpoint=endpoint, payload=None, extract_data=False
        )

    async def create_journal_attachment(
        self, journal_id: str, filename: str, exchanges_rates_file_path: Path
    ):
        endpoint = self.api_base_url + f"/public/v1/billing/journals/{journal_id}/attachments"
        try:
            file = Path(exchanges_rates_file_path)
            if not file.is_file():
                logger.error(f"File path not found: {file}")
                return None

            attachment_json = {
                "name": filename,  # EUR_202504
                "description": "Conversion Rate",
                "filename": file.name,
                "size": 0,
            }
            file_binary = json.dumps(exchanges_rates_file_path, indent=2).encode("utf-8")
            files = {
                "file": (file.name, file_binary, "application/json"),
                "attachment": (None, json.dumps(attachment_json), "application/json"),
            }

            response = await self._send_request(
                method="POST",
                endpoint=endpoint,
                headers={
                    "Content-Type": f"multipart/form-data;boundary=boundary{str(uuid4())}"
                },
                files=files,
                payload=None,
                extract_data=False,
            )

            if response:
                logger.info("Journal File Attachment completed successfully.")
                return response
            logger.error("Journal Attachment failed: No response or error.")
            return None
        except Exception:
            logger.exception("Exception occurred during file attachment.")
            return None

    async def _send_request(
        self,
        method: Literal["GET", "POST", "DELETE"],
        endpoint: str,
        headers: dict[str, str] | None = None,
        payload: dict[str, Any] | None = None,
        files: dict[str, Any] | None = None,
        extract_data: bool = True,
    ) -> list[dict[str, Any]] | dict[str, Any] | None:
        """
        This method is responsible for sending the given request.
        It also supports the upload of files.
        """
        try:
            requests_args = {
                "method": method,
                "url": endpoint,
                "headers": {**self.headers, **(headers or {})},
            }
            if files:
                requests_args["files"] = files
                if payload:
                    requests_args["data"] = payload
            elif payload and method == "POST":
                requests_args["json"] = payload

            response = await self.client.request(**requests_args)
            response.raise_for_status()
            try:
                data = response.json()
                return data.get("data") if extract_data else data
            except json.decoder.JSONDecodeError:
                logger.exception("JSON decode error")
                return None
        except httpx.HTTPError as error:
            logger.exception(f"{method} request failed: {error}")
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

    async def fetch_organizations_by_billing_currency(
        self, billing_currency: str, limit: int | None = 50, offset: int | None = 0
    ) -> dict[str, Any] | None:
        """
        This method fetches organizations filtered by billing currency.
        billing_currency: str, e.g. "EUR",
        limit: int, optional,
        offset: int, optional,
        """

        rql_filter = f"eq(billing_currency,{billing_currency})"
        endpoint = (
            f"{self.api_base_url}/ops/v1/organizations?{rql_filter}&limit={limit}&offset={offset}"
        )
        return await self._send_request(endpoint=endpoint)

    async def fetch_expenses(
        self,
        organization_id: str,
        month: int,
        year: int,
        limit: int | None = 50,
        offset: int | None = 0,
    ) -> dict[str, Any] | None:
        rql_filter = f"and(eq(organization.id,{organization_id}),eq(month,{month}),eq(year,{year})"
        endpoint = f"{self.api_base_url}/ops/v1/expenses?{rql_filter}&limit={limit}&offset={offset}"
        return await self._send_request(endpoint=endpoint)

    async def _send_request(self, endpoint: str) -> dict[str, Any] | None:
        try:
            headers = self._get_headers()
            response = await self.client.get(headers=headers, url=endpoint)
            response.raise_for_status()
            data = response.json()
            return data.get("items", [])
        except httpx.HTTPError as error:
            logger.exception(f"Request failed: {error}")
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


_FFC_CLIENT = None
_HTTPX_MTP_API_CLIENT = None
_HTTPX_FFC_API_CLIENT = None
_HTTPX_EXCHANGE_RATE_API_CLIENT = None


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
            mtp_token=settings.EXTENSION_CONFIG["MPT_API_TOKEN"],
        )

    return _HTTPX_MTP_API_CLIENT


def get_httpx_exchange_rate_client():
    """
    This returns an instance of the ExchangeRateClient class.
    """
    from django.conf import settings

    global _HTTPX_EXCHANGE_RATE_API_CLIENT
    if not _HTTPX_EXCHANGE_RATE_API_CLIENT:
        _HTTPX_EXCHANGE_RATE_API_CLIENT = ExchangeRateClient(
            base_url=settings.EXTENSION_CONFIG["MPT_API_BASE_URL"],
            api_key=settings.EXTENSION_CONFIG["MPT_API_TOKEN"],
        )

    return _HTTPX_EXCHANGE_RATE_API_CLIENT
