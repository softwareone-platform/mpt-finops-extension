import logging

import pytest
from adaptive_cards import card_types as ct
from django.conf import settings
from pytest_httpx import HTTPXMock
from pytest_mock import MockerFixture

from ffc.flows.order import OrderContext
from ffc.notifications import (
    NotificationDetails,
    NotifyCategories,
    dateformat,
    mpt_notify,
    notify_unhandled_exception_in_teams,
    send_error,
    send_exception,
    send_info,
    send_mpt_notification,
    send_notification,
    send_warning,
)


def test_mpt_notify(mocker, mpt_client):
    mocked_template = mocker.MagicMock()
    mocked_template.render.return_value = "rendered-template"
    mocked_jinja_env = mocker.MagicMock()
    mocked_jinja_env.get_template.return_value = mocked_template
    mocker.patch("ffc.notifications.env", mocked_jinja_env)
    mock_notify = mocker.patch("ffc.notifications.notify", autospec=True)

    mpt_notify(
        mpt_client,
        "account_id",
        "buyer_id",
        "email-subject",
        "template_name",
        {"test": "context"},
    )

    mocked_jinja_env.get_template.assert_called_once_with("template_name.html")
    mocked_template.render.assert_called_once_with({"test": "context"})
    mock_notify.assert_called_once_with(
        mpt_client,
        NotifyCategories.ORDERS.value,
        "account_id",
        "buyer_id",
        "email-subject",
        "rendered-template",
    )


def test_mpt_notify_exception(mocker, mpt_client, caplog):
    mocked_template = mocker.MagicMock()
    mocked_template.render.return_value = "rendered-template"
    mocked_jinja_env = mocker.MagicMock()
    mocked_jinja_env.get_template.return_value = mocked_template
    mocker.patch("ffc.notifications.env", mocked_jinja_env)
    mocker.patch(
        "ffc.notifications.notify",
        autospec=True,
        side_effect=Exception("error"),
    )

    with caplog.at_level(logging.ERROR):
        mpt_notify(
            mpt_client,
            "account_id",
            "buyer_id",
            "email-subject",
            "template_name",
            {"test": "context"},
        )

    assert (
        "Cannot send MPT API notification:"
        f" Category: '{NotifyCategories.ORDERS.value}',"
        " Account ID: 'account_id',"
        " Buyer ID: 'buyer_id',"
        " Subject: 'email-subject',"
        " Message: 'rendered-template'"
    ) in caplog.text


def test_dateformat():
    assert dateformat("2024-05-16T10:54:42.831Z") == "16 May 2024"
    assert dateformat("") == ""
    assert dateformat(None) == ""


def test_notify_unhandled_exception_in_teams(mocker):
    mock_run = mocker.patch("ffc.notifications.asyncio.run")
    mock_send_exc_coro = mocker.MagicMock()
    mocked_send_exc = mocker.MagicMock(return_value=mock_send_exc_coro)

    mocker.patch("ffc.notifications.send_exception", mocked_send_exc)
    notify_unhandled_exception_in_teams(
        "validation",
        "ORD-0000",
        "exception-traceback",
    )

    mocked_send_exc.assert_called_once_with(
        "Order validation unhandled exception!",
        "An unhandled exception has been raised while performing validation "
        "of the order **ORD-0000**:\n\n"
        "```exception-traceback```",
    )
    mock_run.assert_called_once_with(mock_send_exc_coro)


def test_send_mpt_notification(mocker, mpt_client, order_factory):
    """Test that MPT notification is sent correctly expected subject for order in
    querying status."""
    mock_mpt_notify = mocker.patch("ffc.notifications.mpt_notify", spec=True)
    mock_get_rendered_template = mocker.patch(
        "ffc.notifications.get_rendered_template", return_value="rendered-template"
    )
    context = OrderContext.from_order(order_factory())

    send_mpt_notification(mpt_client, context)

    mock_mpt_notify.assert_called_once_with(
        mpt_client,
        "ACC-9121-8944",
        "BUY-3731-7971",
        "Order status update ORD-0792-5000-2253-4210 for A buyer",
        "notification",
        {
            "activation_template": "<p>rendered-template</p>\n",
            "api_base_url": "https://localhost",
            "order": context.order,
            "portal_base_url": "https://portal.s1.local",
        },
    )
    mock_get_rendered_template.assert_called_once()


@pytest.mark.parametrize(
    ("function", "color", "icon"),
    [
        (send_info, ct.Colors.ACCENT, "\U0001f44d"),
        (send_warning, ct.Colors.WARNING, "\u2622"),
        (send_error, ct.Colors.ATTENTION, "\U0001f4a3"),
        (send_exception, ct.Colors.ATTENTION, "\U0001f525"),
    ],
)
async def test_send_others(mocker, function, color, icon):
    mocked_send_notification = mocker.patch(
        "ffc.notifications.send_notification",
    )

    await function("title", "text", details=None, open_url=None)

    mocked_send_notification.assert_awaited_once_with(
        f"{icon} title",
        "text",
        title_color=color,
        details=None,
        open_url=None,
    )


async def test_send_notification_full(httpx_mock: HTTPXMock, mocker: MockerFixture):
    httpx_mock.add_response(
        method="POST",
        url=settings.EXTENSION_CONFIG["MSTEAMS_NOTIFICATIONS_WEBHOOKS_URL"],
        status_code=202,
        match_json={
            "type": "message",
            "attachments": [
                {
                    "contentType": "application/vnd.microsoft.card.adaptive",
                    "content": {
                        "type": "AdaptiveCard",
                        "version": "1.4",
                        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                        "body": [
                            {
                                "text": "Title",
                                "type": "TextBlock",
                                "color": "dark",
                                "size": "large",
                                "weight": "bolder",
                            },
                            {
                                "text": "Text",
                                "type": "TextBlock",
                                "color": "default",
                                "size": "small",
                                "wrap": True,
                            },
                            {
                                "type": "ColumnSet",
                                "columns": [
                                    {
                                        "type": "Column",
                                        "items": [
                                            {
                                                "text": "Header 1",
                                                "type": "TextBlock",
                                                "weight": "bolder",
                                                "wrap": True,
                                            },
                                            {
                                                "text": "Row 1 Col 1",
                                                "type": "TextBlock",
                                                "color": "default",
                                                "wrap": True,
                                            },
                                            {
                                                "text": "Row 2 Col 1",
                                                "type": "TextBlock",
                                                "color": "accent",
                                                "wrap": True,
                                            },
                                        ],
                                        "width": "auto",
                                    },
                                    {
                                        "type": "Column",
                                        "items": [
                                            {
                                                "text": "Header 2",
                                                "type": "TextBlock",
                                                "weight": "bolder",
                                                "wrap": True,
                                            },
                                            {
                                                "text": "Row 1 Col 2",
                                                "type": "TextBlock",
                                                "color": "default",
                                                "wrap": True,
                                            },
                                            {
                                                "text": "Row 2 Col 2",
                                                "type": "TextBlock",
                                                "color": "accent",
                                                "wrap": True,
                                            },
                                        ],
                                        "width": "auto",
                                    },
                                ],
                            },
                            {
                                "title": "Open",
                                "mode": "primary",
                                "url": "https://example.com",
                                "type": "Action.OpenUrl",
                            },
                        ],
                        "msteams": {"width": "Full"},
                    },
                }
            ],
        },
    )

    await send_notification(
        "Title",
        "Text",
        title_color=ct.Colors.DARK,
        open_url="https://example.com",
        details=NotificationDetails(
            header=("Header 1", "Header 2"),
            rows=[("Row 1 Col 1", "Row 1 Col 2"), ("Row 2 Col 1", "Row 2 Col 2")],
        ),
    )


async def test_send_notification_simple(httpx_mock: HTTPXMock, mocker: MockerFixture):
    httpx_mock.add_response(
        method="POST",
        url=settings.EXTENSION_CONFIG["MSTEAMS_NOTIFICATIONS_WEBHOOKS_URL"],
        status_code=202,
        match_json={
            "type": "message",
            "attachments": [
                {
                    "contentType": "application/vnd.microsoft.card.adaptive",
                    "content": {
                        "type": "AdaptiveCard",
                        "version": "1.4",
                        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                        "body": [
                            {
                                "text": "Title",
                                "type": "TextBlock",
                                "color": "dark",
                                "size": "large",
                                "weight": "bolder",
                            },
                            {
                                "text": "Text",
                                "type": "TextBlock",
                                "color": "default",
                                "size": "small",
                                "wrap": True,
                            },
                        ],
                        "msteams": {"width": "Full"},
                    },
                }
            ],
        },
    )

    await send_notification(
        "Title",
        "Text",
        title_color=ct.Colors.DARK,
    )


async def test_send_notification_error(
    caplog: pytest.LogCaptureFixture,
    httpx_mock: HTTPXMock,
    mocker: MockerFixture,
):
    httpx_mock.add_response(
        method="POST",
        url=settings.EXTENSION_CONFIG["MSTEAMS_NOTIFICATIONS_WEBHOOKS_URL"],
        status_code=500,
        content=b"Internal Server Error",
    )

    with caplog.at_level("ERROR"):
        await send_notification(
            "Title",
            "Text",
            title_color=ct.Colors.DARK,
        )
    assert ("Failed to send notification to MSTeams: 500 - Internal Server Error") in caplog.text
