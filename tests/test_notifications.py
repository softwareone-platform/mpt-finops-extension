import pytest
from adaptive_cards import card_types as ct
from django.conf import settings
from pytest_httpx import HTTPXMock
from pytest_mock import MockerFixture

from ffc.notifications import (
    ColumnHeader,
    NotificationDetails,
    dateformat,
    notify_unhandled_exception_in_teams,
    send_error,
    send_exception,
    send_info,
    send_notification,
    send_warning,
)


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
                                "items": [
                                    {
                                        "type": "ColumnSet",
                                        "columns": [
                                            {
                                                "type": "Column",
                                                "items": [
                                                    {
                                                        "text": "Header 1",
                                                        "type": "TextBlock",
                                                        "color": "accent",
                                                        "weight": "bolder",
                                                        "wrap": True,
                                                    }
                                                ],
                                                "width": "auto",
                                            },
                                            {
                                                "type": "Column",
                                                "items": [
                                                    {
                                                        "text": "Header 2",
                                                        "type": "TextBlock",
                                                        "color": "accent",
                                                        "weight": "bolder",
                                                        "wrap": True,
                                                    }
                                                ],
                                                "width": "auto",
                                            },
                                        ],
                                    },
                                    {
                                        "spacing": "small",
                                        "type": "ColumnSet",
                                        "columns": [
                                            {
                                                "type": "Column",
                                                "items": [
                                                    {
                                                        "text": "Row 1 Col 1",
                                                        "type": "TextBlock",
                                                        "color": "default",
                                                        "wrap": True,
                                                    }
                                                ],
                                                "width": "auto",
                                            },
                                            {
                                                "type": "Column",
                                                "items": [
                                                    {
                                                        "text": "Row 1 Col 2",
                                                        "type": "TextBlock",
                                                        "color": "default",
                                                        "wrap": True,
                                                    }
                                                ],
                                                "width": "auto",
                                            },
                                        ],
                                    },
                                    {
                                        "spacing": "small",
                                        "type": "ColumnSet",
                                        "columns": [
                                            {
                                                "type": "Column",
                                                "items": [
                                                    {
                                                        "text": "Row 2 Col 1",
                                                        "type": "TextBlock",
                                                        "color": "default",
                                                        "wrap": True,
                                                    }
                                                ],
                                                "width": "auto",
                                            },
                                            {
                                                "type": "Column",
                                                "items": [
                                                    {
                                                        "text": "Row 2 Col 2",
                                                        "type": "TextBlock",
                                                        "color": "default",
                                                        "wrap": True,
                                                    }
                                                ],
                                                "width": "auto",
                                            },
                                        ],
                                    },
                                ],
                                "type": "Container",
                            },
                        ],
                        "actions": [
                            {
                                "title": "Open",
                                "mode": "primary",
                                "url": "https://example.com",
                                "type": "Action.OpenUrl",
                            }
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
            header=("Header 1", ColumnHeader("Header 2")),
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
                        "actions": [],
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
