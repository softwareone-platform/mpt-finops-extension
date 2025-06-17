import logging
from unittest.mock import AsyncMock, patch

import pytest

from ffc.process_billing import BillingProcess


# test get_or_create_journal_file
@pytest.mark.asyncio()
async def test_journal_exists(existing_journal_file,billing_process_instance):
    with patch.object(BillingProcess, 'mtp_client', new_callable=AsyncMock) as mtp_mock:
        mtp_mock.get_journal_file = AsyncMock(return_value=existing_journal_file)
        result = await billing_process_instance.get_or_create_journal_file(
            authorization_id="AUTH-123-1234",
            month=6,
            year=2025,
        )
        assert result == existing_journal_file


@pytest.mark.asyncio()
async def test_journal_must_be_created(return_create_journal,billing_process_instance):
    with patch.object(BillingProcess, 'mtp_client', new_callable=AsyncMock) as mtp_mock:
        mtp_mock.get_journal_file.return_value = []
        mtp_mock.create_journal = AsyncMock(return_value=return_create_journal)

        result = await billing_process_instance.get_or_create_journal_file(
            authorization_id="AUTH-123-1234",
            month=6,
            year=2025,
        )
        assert result == return_create_journal


@pytest.mark.asyncio()
async def test_journal_create_returns_none(billing_process_instance):
    with patch.object(BillingProcess, 'mtp_client', new_callable=AsyncMock) as mtp_mock:
        mtp_mock.get_journal_file = AsyncMock(return_value=[])
        mtp_mock.create_journal.return_value = None

        result = await billing_process_instance.get_or_create_journal_file(
            authorization_id="AUTH-123-1234",
            month=6,
            year=2025,
        )
        assert result is None

# test check_if_an_attachment_exists
@pytest.mark.asyncio()
async def test_check_if_an_attachment_exists(billing_process_instance,return_journal_attachment):
    with patch.object(BillingProcess, 'mtp_client', new_callable=AsyncMock) as mtp_mock:
        mtp_mock.fetch_journal_attachments = AsyncMock(return_value=return_journal_attachment)
        mtp_mock.delete_journal_attachment = AsyncMock(return_value={})

        result = await billing_process_instance.check_attachment_duplicate_and_delete(
           journal_id="BJO-9000-4019",
           filename="sample"
        )
        assert result is True

@pytest.mark.asyncio()
async def test_check_attachment_duplicate_and_delete_does_not_exist(billing_process_instance):
    with patch.object(BillingProcess, 'mtp_client', new_callable=AsyncMock) as mtp_mock:
        mtp_mock.fetch_journal_attachments = AsyncMock(return_value=[])
        mtp_mock.delete_journal_attachment = AsyncMock(return_value={})

        result = await billing_process_instance.check_attachment_duplicate_and_delete(
            journal_id="BJO-9000-4019",
            filename="sample"
        )
        assert result is True

@pytest.mark.asyncio()
async def test_check_attachment_duplicate_and_delete_error(billing_process_instance):
    with patch.object(BillingProcess, 'mtp_client', new_callable=AsyncMock) as mtp_mock:
        mtp_mock.fetch_journal_attachments = AsyncMock(return_value=None)
        mtp_mock.delete_journal_attachment = AsyncMock(return_value={})

        result = await billing_process_instance.check_attachment_duplicate_and_delete(
            journal_id="BJO-9000-4019",
            filename="sample"
        )
        assert result is None

# get_journal_id_for_the_authorization
@pytest.mark.asyncio()
async def test_get_journal_id_for_the_authorization_with_no_existing_journal(billing_process_instance,return_create_journal):
    with patch.object(BillingProcess, 'mtp_client', new_callable=AsyncMock) as mtp_mock:
        mtp_mock.get_journal_file = AsyncMock(return_value=[])
        mtp_mock.create_journal = AsyncMock(return_value=return_create_journal)
        mtp_mock.get_or_create_journal_file = AsyncMock(return_value=return_create_journal)
        result = await billing_process_instance.get_journal_id_for_the_authorization(
            authorization_id="AUT-5305-9928"
        )
        assert result == "BJO-9000-4019"


# get_journal_id_for_the_authorization
@pytest.mark.asyncio()
async def test_get_journal_id_for_the_authorization_with_existing_journal(billing_process_instance,return_create_journal):
    with patch.object(BillingProcess, 'mtp_client', new_callable=AsyncMock) as mtp_mock:
        mtp_mock.get_journal_file = AsyncMock(return_value=return_create_journal)
        mtp_mock.get_or_create_journal_file = AsyncMock(return_value=return_create_journal)
        result = await billing_process_instance.get_journal_id_for_the_authorization(
            authorization_id="AUT-5305-9928"
        )
        assert result == "BJO-9000-4019"

@pytest.mark.asyncio()
async def test_get_journal_id_for_the_authorization_with_error_journal(billing_process_instance):
    with patch.object(BillingProcess, 'mtp_client', new_callable=AsyncMock) as mtp_mock:
        mtp_mock.get_journal_file = AsyncMock(return_value=None)
        mtp_mock.get_or_create_journal_file = AsyncMock(return_value=None)
        result = await billing_process_instance.get_journal_id_for_the_authorization(
            authorization_id="AUT-5305-9928"
        )
        assert result is None



# check_if_rate_conversion_is_required
@pytest.mark.asyncio()
async def test_check_if_rate_conversion_is_required(billing_process_instance,get_organization, get_agreement_details,get_exchange_rate,return_journal_attachment,return_create_journal):
    get_agreement_details[0]["authorization"]["currency"] = "EUR"
    with patch.object(BillingProcess, 'exchange_rate_client', new_callable=AsyncMock) as exchange_rate_client_mock:
        with patch.object(BillingProcess, 'mtp_client', new_callable=AsyncMock) as mtp_mock:
            exchange_rate_client_mock.fetch_exchange_rate = AsyncMock(return_value=get_exchange_rate)
            mtp_mock.fetch_journal_attachments = AsyncMock(return_value=return_journal_attachment)
            mtp_mock.delete_journal_attachment = AsyncMock(return_value={})
            mtp_mock.create_journal_attachment = AsyncMock(return_value=return_create_journal)
            result = await billing_process_instance.check_if_rate_conversion_is_required(
                organization=get_organization,
                agreement=get_agreement_details,
                journal_file_id="BJO-9000-4019",

            )
            assert result is None # to be improved once the code will be merged.

@pytest.mark.asyncio()
async def test_check_if_rate_conversion_is_required(billing_process_instance,get_organization, get_agreement_details,caplog):
    get_organization["billing_currency"] = "EUR"
    with caplog.at_level(logging.ERROR):
        with patch.object(BillingProcess, 'exchange_rate_client', new_callable=AsyncMock) as exchange_rate_client_mock:
            exchange_rate_client_mock.fetch_exchange_rate = AsyncMock(return_value=None)
            with pytest.raises(RuntimeError):
                await billing_process_instance.check_if_rate_conversion_is_required(
                    organization=get_organization,
                    journal_file_id="BJO-9000-4019",

                )
            assert "An error occurred while fetching exchange rate for USD" in caplog.messages[0]
