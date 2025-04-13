import logging
from functools import cache

from django.conf import settings
from swo.mpt.client.errors import wrap_http_error, ERR_EXT_UNHANDLED_EXCEPTION

logger = logging.getLogger(__name__)


def _has_more_pages(page):
    if not page:
        return True
    pagination = page["$meta"]["pagination"]
    return pagination["total"] > pagination["limit"] + pagination["offset"]


def _paginated(mpt_client, url):
    items = []
    page = None
    limit = 10
    offset = 0
    while _has_more_pages(page):
        response = mpt_client.get(f"{url}&limit={limit}&offset={offset}")
        response.raise_for_status()
        page = response.json()
        items.extend(page["data"])
        offset += limit

    return items


@wrap_http_error
def get_agreement(mpt_client, agreement_id):
    response = mpt_client.get(
        f"/commerce/agreements/{agreement_id}?select=seller,buyer,listing,product,subscriptions"
    )
    response.raise_for_status()
    return response.json()


@wrap_http_error
def get_rendered_template(mpt_client, order_id):
    response = mpt_client.get(
        f"/commerce/orders/{order_id}/template",
    )
    response.raise_for_status()
    return response.json()


@wrap_http_error
def update_order(mpt_client, order_id, **kwargs):
    response = mpt_client.put(
        f"/commerce/orders/{order_id}",
        json=kwargs,
    )
    response.raise_for_status()
    return response.json()


@wrap_http_error
def query_order(mpt_client, order_id, **kwargs):
    response = mpt_client.post(
        f"/commerce/orders/{order_id}/query",
        json=kwargs,
    )
    response.raise_for_status()
    return response.json()


@wrap_http_error
def fail_order(mpt_client, order_id, reason, **kwargs):
    response = mpt_client.post(
        f"/commerce/orders/{order_id}/fail",
        json={
            "statusNotes": ERR_EXT_UNHANDLED_EXCEPTION.to_dict(error=reason),
            **kwargs,
        },
    )
    response.raise_for_status()
    return response.json()


@wrap_http_error
def complete_order(mpt_client, order_id, template, **kwargs):
    response = mpt_client.post(
        f"/commerce/orders/{order_id}/complete",
        json={"template": template, **kwargs},
    )
    response.raise_for_status()
    return response.json()


@wrap_http_error
def create_subscription(mpt_client, order_id, subscription):
    response = mpt_client.post(
        f"/commerce/orders/{order_id}/subscriptions",
        json=subscription,
    )
    response.raise_for_status()
    return response.json()


@cache
@wrap_http_error
def get_webhook(mpt_client, webhook_id):
    response = mpt_client.get(f"/notifications/webhooks/{webhook_id}?select=criteria")
    response.raise_for_status()

    return response.json()


@wrap_http_error
def get_product_template_or_default(mpt_client, product_id, status, name=None):
    name_or_default_filter = "eq(default,true)"
    if name:
        name_or_default_filter = f"or({name_or_default_filter},eq(name,{name}))"
    rql_filter = f"and(eq(type,Order{status}),{name_or_default_filter})"
    url = f"/catalog/products/{product_id}/templates?{rql_filter}&order=default&limit=1"
    response = mpt_client.get(url)
    response.raise_for_status()
    templates = response.json()
    return templates["data"][0]


@wrap_http_error
def update_agreement(mpt_client, agreement_id, **kwargs):
    response = mpt_client.put(
        f"/commerce/agreements/{agreement_id}",
        json=kwargs,
    )
    response.raise_for_status()
    return response.json()
