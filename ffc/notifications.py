import asyncio
import functools
import logging
import os
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any

import httpx
from adaptive_cards import card_types as ct
from adaptive_cards.actions import ActionOpenUrl
from adaptive_cards.card import AdaptiveCard
from adaptive_cards.card_types import MSTeams, MSTeamsCardWidth
from adaptive_cards.containers import Column, ColumnSet, Container
from adaptive_cards.elements import TextBlock
from django.conf import settings
from jinja2 import Environment, FileSystemLoader, select_autoescape
from markdown_it import MarkdownIt
from mpt_extension_sdk.mpt_http.base import MPTClient
from mpt_extension_sdk.mpt_http.mpt import (
    get_rendered_template,
    notify,
)

from ffc.flows.order import OrderContext
from ffc.parameters import PARAM_CONTACT, get_ordering_parameter

logger = logging.getLogger(__name__)
NotifyCategories = Enum("NotifyCategories", settings.MPT_NOTIFY_CATEGORIES)  # type: ignore[misc]


def dateformat(date_string):
    return datetime.fromisoformat(date_string).strftime("%-d %B %Y") if date_string else ""


env = Environment(
    loader=FileSystemLoader(
        os.path.join(
            os.path.abspath(os.path.dirname(__file__)),
            "templates",
        ),
    ),
    autoescape=select_autoescape(),
)

env.filters["dateformat"] = dateformat


def mpt_notify(
    mpt_client,
    account_id: str,
    buyer_id: str,
    subject: str,
    template_name: str,
    context: dict,
) -> None:
    """
    Sends a notification through the MPT API using a specified template and context.

    Parameters:
    account_id: str
        The identifier for the account associated with the notification.
    buyer_id: str
        The identifier for the buyer to whom the notification is sent.
    subject: str
        The subject of the notification email.
    template_name: str
        The name of the email template to be used, excluding the file extension.
    context: dict
        The context data to render the given email template.

    Returns:
    None

    Raises:
    Exception
        Logs the exception if there is an issue during the notification process,
        including the category, subject, and the rendered message.
    """
    template = env.get_template(f"{template_name}.html")
    rendered_template = template.render(context)

    try:
        notify(
            mpt_client,
            NotifyCategories.ORDERS.value,
            account_id,
            buyer_id,
            subject,
            rendered_template,
        )
    except Exception:
        logger.exception(
            f"Cannot send MPT API notification:"
            f" Category: '{NotifyCategories.ORDERS.value}',"
            f" Account ID: '{account_id}',"
            f" Buyer ID: '{buyer_id}',"
            f" Subject: '{subject}',"
            f" Message: '{rendered_template}'"
        )


def get_notifications_recipient(order):  # pragma: no cover
    return (get_ordering_parameter(order, PARAM_CONTACT).get("value", {}) or {}).get("email") or (
        order["agreement"]["buyer"].get("contact", {}) or {}
    ).get("email")


def md2html(template):  # pragma: no cover
    return MarkdownIt("commonmark", {"breaks": True, "html": True}).render(template)


def send_mpt_notification(client: MPTClient, order_context: type[OrderContext]) -> None:
    """
    Send an MPT notification to the customer according to the
    current order status.
    It embeds the current order template into the body.
    """
    template_context = {
        "order": order_context.order,
        "activation_template": md2html(get_rendered_template(client, order_context.order_id)),
        "api_base_url": settings.MPT_API_BASE_URL,
        "portal_base_url": settings.MPT_PORTAL_BASE_URL,
    }
    buyer_name = order_context.order["agreement"]["buyer"]["name"]
    subject = f"Order status update {order_context.order_id} for {buyer_name}"
    if order_context.order["status"] == "Querying":
        subject = f"This order need your attention {order_context.order_id} for {buyer_name}"
    mpt_notify(
        client,
        order_context.order["agreement"]["client"]["id"],
        order_context.order["agreement"]["buyer"]["id"],
        subject,
        "notification",
        template_context,
    )


@functools.cache
def notify_unhandled_exception_in_teams(process, order_id, traceback):  # pragma: no cover
    asyncio.run(
        send_exception(
            f"Order {process} unhandled exception!",
            f"An unhandled exception has been raised while performing {process} "
            f"of the order **{order_id}**:\n\n"
            f"```{traceback}```",
        )
    )


@dataclass
class ColumnHeader:
    text: str
    width: str = "auto"
    horizontal_alignment: ct.HorizontalAlignment | None = None


class NotificationDetails:
    def __init__(self, header: tuple[str | ColumnHeader, ...], rows: list[tuple[str, ...]]):
        if not all(len(t) == len(header) for t in rows):
            raise ValueError("All rows must have the same number of columns as the header.")
        self.header = header
        self.rows = rows

    @staticmethod
    def _get_header_text_and_width(col: str | ColumnHeader) -> tuple[str, str]:
        if isinstance(col, ColumnHeader):
            return col.text, col.width
        return str(col), "auto"

    def to_container(self) -> Container:
        items = []

        # Header row
        header_columns = []
        for col in self.header:
            text, width = self._get_header_text_and_width(col)
            alignment = (
                col.horizontal_alignment.value
                if isinstance(col, ColumnHeader) and col.horizontal_alignment
                else None
            )
            header_columns.append(
                Column(
                    width=width,
                    items=[
                        TextBlock(
                            text=text,
                            horizontal_alignment=alignment,
                            weight=ct.FontWeight.BOLDER,
                            wrap=True,
                            color=ct.Colors.ACCENT,
                        )
                    ],
                )
            )
        items.append(ColumnSet(columns=header_columns))

        # Data rows
        for _idx, row in enumerate(self.rows):
            row_columns = []
            for col_idx, value in enumerate(row):
                col = self.header[col_idx]
                _, width = self._get_header_text_and_width(col)
                alignment = (
                    col.horizontal_alignment.value
                    if isinstance(col, ColumnHeader) and col.horizontal_alignment
                    else None
                )
                row_columns.append(
                    Column(
                        width=width,
                        items=[
                            TextBlock(
                                text=value,
                                horizontal_alignment=alignment,
                                wrap=True,
                                color=ct.Colors.DEFAULT,
                            )
                        ],
                    )
                )
            items.append(
                ColumnSet(
                    columns=row_columns,
                    spacing=ct.Spacing.SMALL,
                )
            )

        return Container(items=items)


async def send_notification(
    title: str,
    text: str,
    title_color: ct.Colors = ct.Colors.DEFAULT,
    details: NotificationDetails | None = None,
    open_url: str | None = None,
) -> None:
    if not settings.EXTENSION_CONFIG.get("MSTEAMS_NOTIFICATIONS_WEBHOOKS_URL"):  # pragma: no cover
        logger.warning("MSTeams notifications are disabled.")
        return

    card_items: list[Any] = [
        TextBlock(
            text=title,
            size=ct.FontSize.LARGE,
            weight=ct.FontWeight.BOLDER,
            color=title_color,
        ),
        TextBlock(
            text=text,
            wrap=True,
            size=ct.FontSize.SMALL,
            color=ct.Colors.DEFAULT,
        ),
    ]
    if details:
        card_items.append(details.to_container())

    card_actions = []
    if open_url:
        card_actions.append(ActionOpenUrl(title="Open", url=open_url))

    card = (
        AdaptiveCard.new().version("1.4").add_items(card_items).add_actions(card_actions).create()
    )

    card.msteams = MSTeams(width=MSTeamsCardWidth.FULL)
    message = {
        "type": "message",
        "attachments": [
            {
                "contentType": "application/vnd.microsoft.card.adaptive",
                "content": card.to_dict(),
            }
        ],
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(
            settings.EXTENSION_CONFIG["MSTEAMS_NOTIFICATIONS_WEBHOOKS_URL"],
            json=message,
            headers={"Content-Type": "application/json"},
        )
        if response.status_code != 202:
            logger.error(
                f"Failed to send notification to MSTeams: {response.status_code} - {response.text}"
            )


async def send_info(
    title: str,
    text: str,
    details: NotificationDetails | None = None,
    open_url: str | None = None,
) -> None:
    await send_notification(
        f"\U0001f44d {title}",
        text,
        title_color=ct.Colors.ACCENT,
        details=details,
        open_url=open_url,
    )


async def send_warning(
    title: str,
    text: str,
    details: NotificationDetails | None = None,
    open_url: str | None = None,
) -> None:
    await send_notification(
        f"\u2622 {title}",
        text,
        title_color=ct.Colors.WARNING,
        details=details,
        open_url=open_url,
    )


async def send_error(
    title: str,
    text: str,
    details: NotificationDetails | None = None,
    open_url: str | None = None,
) -> None:
    await send_notification(
        f"\U0001f4a3 {title}",
        text,
        title_color=ct.Colors.ATTENTION,
        details=details,
        open_url=open_url,
    )


async def send_exception(
    title: str,
    text: str,
    details: NotificationDetails | None = None,
    open_url: str | None = None,
) -> None:
    await send_notification(
        f"\U0001f525 {title}",
        text,
        title_color=ct.Colors.ATTENTION,
        details=details,
        open_url=open_url,
    )
