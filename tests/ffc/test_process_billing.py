import json
import logging
import tempfile
from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from ffc.billing.dataclasses import AuthorizationProcessResult, CurrencyConversionInfo, Refund
from ffc.billing.exceptions import ExchangeRatesClientError, JournalStatusError
from ffc.process_billing import generate_refunds, get_agreement_data

# - test evaluate_journal_status()


@pytest.mark.asyncio()
async def test_evaluate_journal_status_draft(existing_journal_file, billing_process_instance):
    """if a journal exists, it should return it as it is"""
    billing_process_instance.mpt_client = AsyncMock()
    billing_process_instance.mpt_client.get_journal = AsyncMock(
        return_value=existing_journal_file[0]
    )
    result = await billing_process_instance.evaluate_journal_status(
        journal_external_id="202505",
    )
    assert result == existing_journal_file[0]


@pytest.mark.asyncio()
async def test_evaluate_journal_status_validated(
    existing_journal_file, billing_process_instance, caplog
):
    """if a journal exists and its status is Validate, it should return the journal as it is"""
    billing_process_instance.mpt_client = AsyncMock()
    existing_journal_file[0]["status"] = "Validated"
    billing_process_instance.mpt_client.get_journal = AsyncMock(
        return_value=existing_journal_file[0]
    )
    with caplog.at_level(logging.INFO):
        result = await billing_process_instance.evaluate_journal_status(
            journal_external_id="202505",
        )
        assert result is existing_journal_file[0]
    assert "[AUT-5305-9928] Found already validated journal: BJO-9000-4019" in caplog.messages[0]


@pytest.mark.asyncio()
async def test_evaluate_journal_different_from_draft_and_not_validated(
    existing_journal_file, billing_process_instance, caplog
):
    """if a journal exists and its status is != from Validated or Draft,
    it should raise a JournalStatusError"""
    billing_process_instance.mpt_client = AsyncMock()
    existing_journal_file[0]["status"] = "Another Status"
    billing_process_instance.mpt_client.get_journal = AsyncMock(
        return_value=existing_journal_file[0]
    )
    with caplog.at_level(logging.WARNING):
        with pytest.raises(JournalStatusError):
            await billing_process_instance.evaluate_journal_status(
                journal_external_id="202505",
            )
    assert (
        "[AUT-5305-9928] Found the journal BJO-9000-4019 with status Another Status"
        in caplog.messages[0]
    )


@pytest.mark.asyncio()
async def test_evaluate_journal_passing_none(billing_process_instance, caplog):
    """if the journal does not exist, it should return None"""
    billing_process_instance.mpt_client = AsyncMock()
    billing_process_instance.mpt_client.get_journal = AsyncMock(return_value=None)
    with caplog.at_level(logging.WARNING):
        response = await billing_process_instance.evaluate_journal_status(
            journal_external_id="202505",
        )
        assert response is None
    assert "[AUT-5305-9928] No journal found for external ID: 202505" in caplog.messages[0]


# ----------------------------------------------------------------------------------
# - Test is_journal_validated
@pytest.mark.asyncio()
async def test_is_journal_validated_success(
    billing_process_instance, existing_journal_file, caplog
):
    """if the given journal's status  is VALIDATED, it should return True"""
    billing_process_instance.mpt_client = AsyncMock()
    existing_journal_file[0]["status"] = "Validated"
    billing_process_instance.mpt_client.get_journal_by_id = AsyncMock(
        return_value=existing_journal_file[0]
    )
    result = await billing_process_instance.is_journal_status_validated(
        journal_id=existing_journal_file[0]["id"]
    )
    assert result is True


@pytest.mark.asyncio()
async def test_is_journal_validated_fail_and_retry(
    mocker, billing_process_instance, existing_journal_file, caplog
):
    """if the given journal's status  is not VALIDATED,
    the function should retry for a number of 5 attempts and fails if no response is received"""
    billing_process_instance.mpt_client = AsyncMock()
    billing_process_instance.mpt_client.get_journal_by_id = AsyncMock(
        return_value=existing_journal_file[0]
    )
    mocker.patch("asyncio.sleep", return_value=None)  # bypass real function's delay
    result = await billing_process_instance.is_journal_status_validated(
        journal_id=existing_journal_file[0]["id"]
    )
    assert result is False
    assert billing_process_instance.mpt_client.get_journal_by_id.call_count == 5


# ----------------------------------------------------------------------------------
# - Test write_charges_file()
@pytest.mark.asyncio()
async def test_write_charges_file_success_no_trial_start_trial_end(
    billing_process_instance,
    patch_fetch_organizations,
    patch_fetch_agreements,
    patch_fetch_organization_expenses,
    caplog,
):
    """if no trial_start and trial_end are provided, the functions still returns True"""
    billing_process_instance.generate_datasource_charges = AsyncMock(
        return_value=['{"id": 1, "name": "test_1"}\n', '{"id": 2, "name": "test_2"}\n']
    )
    result = await billing_process_instance.write_charges_file(
        filepath=f"{tempfile.gettempdir()}/test_generate_charges_file.json",
    )
    assert result is True


@pytest.mark.asyncio()
async def test_write_charges_file_success(
    billing_process_instance,
    caplog,
    patch_fetch_agreements_with_trial,
    patch_fetch_organizations,
    patch_fetch_organization_expenses,
):
    """the successful case"""
    billing_process_instance.generate_datasource_charges = AsyncMock(
        return_value=['{"id": 1, "name": "test_1"}\n', '{"id": 2, "name": "test_2"}\n']
    )
    result = await billing_process_instance.write_charges_file(
        filepath=f"{tempfile.gettempdir()}/test_generate_charges_file.json",
    )
    assert result is True


@pytest.mark.asyncio()
async def test_write_charges_file_empty_file(
    billing_process_instance,
    patch_fetch_organizations,
    patch_fetch_agreements,
    patch_fetch_organization_expenses,
    caplog,
):
    """if an empty file is provided, it should return False, no files were written"""
    billing_process_instance.generate_datasource_charges = AsyncMock(return_value={})
    result = await billing_process_instance.write_charges_file(
        filepath=f"{tempfile.gettempdir()}/test_generate_charges_file.json",
    )
    assert result is False


@pytest.mark.asyncio()
async def test_write_charges_file_agr_000(
    billing_process_instance,
    patch_fetch_organizations_agr_000,
    patch_fetch_organization_expenses,
    patch_fetch_agreements,
    caplog,
):
    """if an agr_000 is provided, it should return False because no files will be written"""
    with caplog.at_level(logging.INFO):
        billing_process_instance.generate_datasource_charges = AsyncMock(
            return_value=['{"id": 1, "name": "test_1"}\n', '{"id": 2, "name": "test_2"}\n']
        )
        result = await billing_process_instance.write_charges_file(
            filepath=f"{tempfile.gettempdir()}/test_generate_charges_file.json",
        )
        assert (
            "[AUT-5305-9928] Skip organization FORG-4801-6958-2949 - "
            "SoftwareOne (Test Environment) because of ID AGR-0000-0000-0000"
            in caplog.messages[1]
        )
        assert result is False


@pytest.mark.asyncio()
async def test_write_charges_file_many_agreements(
    mocker,
    billing_process_instance,
    patch_fetch_organizations,
    get_agreement_details,
    patch_fetch_organization_expenses,
    caplog,
):
    """if many agreements are provided for a given org,
    they will be skipped and no file will be written"""
    get_agreement_details[0]["authorization"]["id"] = "AUT-5305-9928"
    get_agreement_details.append(get_agreement_details[0])

    async def agr_mock_generator():
        for agr in get_agreement_details:
            yield agr

    with caplog.at_level(logging.INFO):
        mocker.patch.object(
            billing_process_instance.mpt_client,
            "fetch_agreements",
            return_value=agr_mock_generator(),
        )

    with caplog.at_level(logging.INFO):
        billing_process_instance.generate_datasource_charges = AsyncMock(
            return_value=['{"id": 1, "name": "test_1"}\n', '{"id": 2, "name": "test_2"}\n']
        )
        result = await billing_process_instance.write_charges_file(
            filepath=f"{tempfile.gettempdir()}/test_generate_charges_file.json",
        )
        assert (
            "[AUT-5305-9928] Found 2 while we were expecting "
            "1 for the organization FORG-4801-6958-2949"
            in caplog.messages[1]
        )
        assert result is False


@pytest.mark.asyncio()
async def test_write_charges_file_different_auth_id(
    mocker,
    billing_process_instance,
    patch_fetch_organizations,
    get_agreement_details,
    patch_fetch_organization_expenses,
    caplog,
):
    """if the authorization's ID of a given agreement is different from the one defined, those
    agreements will be skipped and no file will be written"""
    get_agreement_details[0]["authorization"]["id"] = "AUT-5305-9955"

    async def agr_mock_generator():
        for agr in get_agreement_details:
            yield agr

    with caplog.at_level(logging.INFO):
        mocker.patch.object(
            billing_process_instance.mpt_client,
            "fetch_agreements",
            return_value=agr_mock_generator(),
        )
        billing_process_instance.generate_datasource_charges = AsyncMock(
            return_value=['{"id": 1, "name": "test_1"}\n', '{"id": 2, "name": "test_2"}\n']
        )
        result = await billing_process_instance.write_charges_file(
            filepath=f"{tempfile.gettempdir()}/test_generate_charges_file.json",
        )
        assert (
            "[AUT-5305-9928] Skipping organization "
            "FORG-4801-6958-2949 because it belongs "
            "to an agreement with different authorization: AUT-5305-9955"
            in caplog.messages[1]
        )
        assert result is False


# ----------------------------------------------------------------------------------
# - Test attach_exchange_rates()


@pytest.mark.asyncio()
async def test_attach_exchange_rates_with_existing_attachment(
    billing_process_instance, return_journal_attachment, return_create_journal, get_exchange_rate
):
    """if a journal already has an attachment, it will be deleted and a new one will be attached."""
    billing_process_instance.mpt_client = AsyncMock()

    billing_process_instance.mpt_client.fetch_journal_attachment = AsyncMock(
        return_value=return_journal_attachment[0]
    )
    billing_process_instance.mpt_client.delete_journal_attachment = AsyncMock(return_value={})
    billing_process_instance.mpt_client.create_journal_attachment = AsyncMock(
        return_value=return_journal_attachment
    )

    result = await billing_process_instance.attach_exchange_rates(
        journal_id="BJO-9000-4019", currency="EUR", exchange_rates=get_exchange_rate
    )
    assert result == return_journal_attachment


@pytest.mark.asyncio()
async def test_attach_exchange_rates_with_no_existing_attachment(
    billing_process_instance, return_journal_attachment, return_create_journal, get_exchange_rate
):
    """if a journal has no attachment, it will be created and attached."""
    billing_process_instance.mpt_client = AsyncMock()

    billing_process_instance.mpt_client.fetch_journal_attachment = AsyncMock(return_value=[])
    billing_process_instance.mpt_client.create_journal_attachment = AsyncMock(
        return_value=return_journal_attachment
    )

    result = await billing_process_instance.attach_exchange_rates(
        journal_id="BJO-9000-4019", currency="EUR", exchange_rates=get_exchange_rate
    )
    assert result == return_journal_attachment


# -------------------------------------------------------------------------------------
# - Test complete_journal_process()
@pytest.mark.asyncio()
async def test_complete_journal_process_success(
    billing_process_instance,
    return_create_journal,
    return_journal_attachment,
    caplog,
    get_exchange_rate,
):
    """if a Journal is created successfully, the exchanges_rate_json will be attached and if the
    status of the journal is Validated, the journal will be submitted. None is returned"""
    return_create_journal["status"] = "Validated"
    billing_process_instance.mpt_client = AsyncMock()
    billing_process_instance.mpt_client.create_journal = AsyncMock(
        return_value=return_create_journal
    )
    billing_process_instance.mpt_client.get_journal_by_id = AsyncMock(
        return_value=return_create_journal
    )
    billing_process_instance.mpt_client.upload_charges = AsyncMock(return_value=None)
    billing_process_instance.mpt_client.submit_journal = AsyncMock(return_value=True)
    billing_process_instance.exchange_rates = get_exchange_rate
    billing_process_instance.mpt_client.attach_exchange_rates = AsyncMock(return_value=None)
    with caplog.at_level(logging.INFO):
        response = await billing_process_instance.complete_journal_process(
            filepath=f"{tempfile.gettempdir()}/test_generate_charges_file.json",
            journal=None,
            journal_external_id="BJO-9000-4019",
        )
        assert response is None
    assert "[AUT-5305-9928] new journal created: BJO-9000-4019" in caplog.messages[0]
    assert "[AUT-5305-9928] submitting the journal BJO-9000-4019." in caplog.messages[1]


@pytest.mark.asyncio()
async def test_complete_journal_process_fail(
    billing_process_instance,
    return_create_journal,
    return_journal_attachment,
    get_exchange_rate,
    caplog,
):
    """if a Journal is created successfully,
    the exchanges_rate_json will be attached. If the journal's status
    is not validated, it won't be submitted. None is returned"""
    billing_process_instance.mpt_client = AsyncMock()
    billing_process_instance.mpt_client.create_journal = AsyncMock(
        return_value=return_create_journal
    )
    billing_process_instance.mpt_client.get_journal_by_id = AsyncMock()
    billing_process_instance.mpt_client.upload_charges = AsyncMock(return_value=None)
    billing_process_instance.is_journal_status_validated = AsyncMock(return_value=False)
    billing_process_instance.mpt_client.submit_journal = AsyncMock(return_value=True)
    billing_process_instance.mpt_client.attach_exchange_rates = AsyncMock(return_value=None)
    billing_process_instance.mpt_client.is_journal_validated = AsyncMock(return_value=True)
    billing_process_instance.exchange_rates = get_exchange_rate
    billing_process_instance.attach_exchange_rates = AsyncMock(
        return_value=return_journal_attachment
    )
    with caplog.at_level(logging.INFO):
        response = await billing_process_instance.complete_journal_process(
            filepath=f"{tempfile.gettempdir()}/test_generate_charges_file.json",
            journal=return_create_journal,
            journal_external_id="BJO-9000-4019",
        )
        assert response is None
    assert (
        "[AUT-5305-9928] cannot submit the journal BJO-9000-4019 it doesn't get validated"
        in caplog.messages[0]
    )


# --------------------------------------------------------------------------------------------
# - Test get_agreement_data()


@pytest.mark.asyncio()
def test_get_agreement_data(get_agreement_with_trial):
    """Providing an agreement, a tuple with trial_start,
    trial_end and billing_percentage will be returned"""
    trial_start, trial_end, billing_percentage = get_agreement_data(get_agreement_with_trial[0])
    assert isinstance(trial_start, date)
    assert isinstance(trial_end, date)
    assert isinstance(billing_percentage, Decimal)


@pytest.mark.asyncio()
def test_get_agreement_no_agreement():
    """If no agreement is provided, the trial_start and trial_end date will be None"""
    trial_start, trial_end, billing_percentage = get_agreement_data(None)
    assert trial_start is None
    assert trial_end is None
    assert isinstance(billing_percentage, Decimal)


# ------------------------------------------------------------------------
# - Test generate_datasource_charges()


@pytest.mark.asyncio()
async def test_generate_datasource_charges_empty_daily_expenses(
    billing_process_instance, get_organization
):
    """if no daily_expenses are provided, there will be no charges for the given datasource"""
    response = await billing_process_instance.generate_datasource_charges(
        organization=get_organization,
        linked_datasource_id="34654563456",
        linked_datasource_type="AWS",
        datasource_id="1234",
        datasource_name="Test",
        daily_expenses={},
        billing_percentage=Decimal("4"),
        trial_start=None,
        trial_end=None,
    )
    assert isinstance(response[0], str)
    assert (
        response[0]
        == '{"externalIds": {"vendor": "34654563456", "invoice": "-", '
           '"reference": "1234"}, "search": {"subscription": '
           '{"criteria": "subscription.externalIds.vendor", "value": "FORG-4801-6958-2949"}, '
           '"item": {"criteria": "item.externalIds.vendor", "value": ""}}, '
           '"period": {"start": "2025-06-01", "end": "2025-06-30"}, '
           '"price": {"unitPP": "0.0000", "PPx1": "0.0000"}, '
           '"quantity": 1, "description": {"value1": "Test", '
           '"value2": "No charges available for this datasource."}, "segment": "COM"}\n'
    )
    assert (
        json.loads(response[0]).get("description").get("value2")
        == "No charges available for this datasource."
    )


@pytest.mark.asyncio()
async def test_generate_datasource_charges_with_daily_expenses(
    billing_process_instance,
    get_organization,
    get_daily_expenses,
    get_exchange_rate,
    get_entitlement,
    caplog,
):
    """if there are daily_expenses, charges will be generated for the given datasource"""
    billing_process_instance.exchange_rate_client = AsyncMock()
    billing_process_instance.ffc_client = AsyncMock()
    billing_process_instance.ffc_client.fetch_entitlement = AsyncMock(return_value=get_entitlement)
    billing_process_instance.exchange_rate_client.fetch_exchange_rates = AsyncMock(
        return_value=get_exchange_rate
    )
    with caplog.at_level(logging.INFO):
        response = await billing_process_instance.generate_datasource_charges(
            organization=get_organization,
            linked_datasource_id="34654563456",
            linked_datasource_type="AWS",
            datasource_id="34654563488",
            datasource_name="Test",
            daily_expenses=get_daily_expenses,
            billing_percentage=Decimal("4"),
            trial_start=date(2025, 6, 1),
            trial_end=date(2025, 6, 30),
        )
    assert isinstance(response[0], str)
    assert (
        response[0]
        == '{"externalIds": {"vendor": "34654563456-01", '
           '"invoice": "-", "reference": "34654563488"}, '
           '"search": {"subscription": {"criteria": "subscription.externalIds.vendor", '
           '"value": "FORG-4801-6958-2949"}, '
           '"item": {"criteria": "item.externalIds.vendor", "value": ""}}, '
           '"period": {"start": "2025-06-01", "end": "2025-06-30"}, '
           '"price": {"unitPP": "183.9829", "PPx1": "183.9829"}, '
           '"quantity": 1, "description": {"value1": "Test", "value2": ""}, '
           '"segment": "COM"}\n'
    )
    assert (
        response[1]
        == '{"externalIds": {"vendor": "34654563456-02", '
           '"invoice": "-", "reference": "34654563488"}, '
           '"search": {"subscription": {"criteria": "subscription.externalIds.vendor", '
           '"value": "FORG-4801-6958-2949"}, '
           '"item": {"criteria": "item.externalIds.vendor", "value": ""}}, '
           '"period": {"start": "2025-06-01", "end": "2025-06-30"}, '
           '"price": {"unitPP": "-67.6346", "PPx1": "-67.6346"}, '
           '"quantity": 1, "description": '
           '{"value1": "Test", '
           '"value2": "Refund due to trial period (from 01 Jun 2025 to 30 Jun 2025)"}, '
           '"segment": "COM"}\n'
    )
    assert (
        "[AUT-5305-9928] : organization_id='FORG-4801-6958-2949' "
        "linked_datasource_id='34654563456' datasource_name='Test' - "
        "amount=Decimal('5326.0458') billing_percentage=Decimal('4') "
        "price_in_source_currency=Decimal('213.041832') "
        "exchange_rate=Decimal('0.8636') price_in_target_currency=Decimal('183.98289848')"
        in caplog.messages[0]
    )


@pytest.mark.asyncio()
async def test_generate_datasource_charges_with_price_in_source_currency_eq_0(
    billing_process_instance,
    get_organization,
    get_daily_expenses,
    get_exchange_rate,
    get_entitlement,
    caplog,
):
    """if there are daily_expenses, but no charges, a line will be added to
    the monthly charge file with 0"""
    billing_process_instance.exchange_rate_client = AsyncMock()
    billing_process_instance.ffc_client = AsyncMock()
    billing_process_instance.ffc_client.fetch_entitlement = AsyncMock(return_value=get_entitlement)
    billing_process_instance.exchange_rate_client.fetch_exchange_rates = AsyncMock(
        return_value=get_exchange_rate
    )
    with caplog.at_level(logging.INFO):
        response = await billing_process_instance.generate_datasource_charges(
            organization=get_organization,
            linked_datasource_id="34654563456",
            linked_datasource_type="AWS",
            datasource_id="34654563488",
            datasource_name="Test",
            daily_expenses=get_daily_expenses,
            billing_percentage=Decimal("0"),
            trial_start=date(2025, 6, 1),
            trial_end=date(2025, 6, 30),
        )
    assert isinstance(response[0], str)
    assert (
        response[0]
        == '{"externalIds": {"vendor": "34654563456-01", "invoice": "-", '
           '"reference": "34654563488"}, '
           '"search": {"subscription": {"criteria": "subscription.externalIds.vendor", '
           '"value": "FORG-4801-6958-2949"}, '
           '"item": {"criteria": "item.externalIds.vendor", "value": ""}}, '
           '"period": {"start": "2025-06-01", "end": "2025-06-30"}, '
           '"price": {"unitPP": "0.0000", "PPx1": "0.0000"}, "quantity": 1,'
           ' "description": {"value1": "Test", "value2": ""}, "segment": "COM"}\n'
    )
    assert json.loads(response[0]).get("price").get("unitPP") == "0.0000"


@pytest.mark.asyncio()
async def test_generate_datasource_charges_with_no_entitlement(
    billing_process_instance,
    get_organization,
    get_daily_expenses,
    get_exchange_rate,
    get_entitlement,
    caplog,
):
    """if there are no entitlements, the function still writes the existing charges for the
    given datasource"""
    billing_process_instance.exchange_rate_client = AsyncMock()
    billing_process_instance.ffc_client = AsyncMock()
    billing_process_instance.ffc_client.fetch_entitlement = AsyncMock(return_value=None)
    billing_process_instance.exchange_rate_client.fetch_exchange_rates = AsyncMock(
        return_value=get_exchange_rate
    )
    with caplog.at_level(logging.INFO):
        response = await billing_process_instance.generate_datasource_charges(
            organization=get_organization,
            linked_datasource_id="34654563456",
            linked_datasource_type="AWS",
            datasource_id="34654563488",
            datasource_name="Test",
            daily_expenses=get_daily_expenses,
            billing_percentage=Decimal("4"),
            trial_start=date(2025, 6, 1),
            trial_end=date(2025, 6, 15),
        )
    assert isinstance(response[0], str)
    assert (
        response[0]
        == '{"externalIds": {"vendor": "34654563456-01", "invoice": "-", '
           '"reference": "34654563488"}, '
           '"search": {"subscription": {"criteria": "subscription.externalIds.vendor", '
           '"value": "FORG-4801-6958-2949"}, '
           '"item": {"criteria": "item.externalIds.vendor", "value": ""}}, '
           '"period": {"start": "2025-06-01", "end": "2025-06-30"}, '
           '"price": {"unitPP": "183.9829", "PPx1": "183.9829"}, '
           '"quantity": 1, "description": {"value1": "Test", "value2": ""}, "segment": "COM"}\n'
    )
    assert (
        response[1]
        == '{"externalIds": {"vendor": "34654563456-02", "invoice": "-", '
           '"reference": "34654563488"}, '
        '"search": {"subscription": {"criteria": "subscription.externalIds.vendor", '
        '"value": "FORG-4801-6958-2949"}, '
           '"item": {"criteria": "item.externalIds.vendor", "value": ""}},'
        ' "period": {"start": "2025-06-01", "end": "2025-06-15"}, '
        '"price": {"unitPP": "-67.6346", "PPx1": "-67.6346"}, '
        '"quantity": 1, '
           '"description": {"value1": "Test", '
           '"value2": "Refund due to trial period (from 01 Jun 2025 to 15 Jun 2025)"},'
           ' "segment": "COM"}\n'
    )


# ------------------------------------------------------------------------------------
# Test


@pytest.mark.asyncio()
async def test_get_currency_conversion_info_needed(
    billing_process_instance,
    get_organization,
    get_exchange_rate,
    caplog,
    get_currency_conversion_info,
):
    """if the billing currency is different from the base currency, the function
    will fetch the exchange rates for the conversion"""
    billing_process_instance.exchange_rate_client = AsyncMock()
    billing_process_instance.exchange_rate_client.fetch_exchange_rates = AsyncMock(
        return_value=get_exchange_rate
    )
    with caplog.at_level(logging.INFO):
        result = await billing_process_instance.get_currency_conversion_info(
            organization=get_organization,
        )
        assert isinstance(result, CurrencyConversionInfo)
        assert result.__dict__ == get_currency_conversion_info


@pytest.mark.asyncio()
async def test_get_currency_conversion_info_no_needed(
    billing_process_instance, get_organization, get_exchange_rate, caplog
):
    """if the billing currency is the same as the base currency, no conversion is needed."""
    get_organization["billing_currency"] = "USD"

    billing_process_instance.exchange_rate_client = AsyncMock()
    billing_process_instance.exchange_rate_client.fetch_exchange_rates = AsyncMock(
        return_value=get_exchange_rate
    )
    with caplog.at_level(logging.INFO):
        result = await billing_process_instance.get_currency_conversion_info(
            organization=get_organization,
        )
        assert isinstance(result, CurrencyConversionInfo)
    assert (
        "[AUT-5305-9928] organization FORG-4801-6958-2949 - SoftwareOne (Test Environment) "
        "doesn't need currency conversion"
        in caplog.messages[0]
    )


@pytest.mark.asyncio()
async def test_check_if_rate_conversion_client_error(
    billing_process_instance, get_organization, caplog
):
    """if an error occurs fetching the conversion info, an error message will be printed."""
    get_organization["billing_currency"] = "EUR"
    billing_process_instance.exchange_rate_client.fetch_exchange_rates = AsyncMock(return_value={})

    with caplog.at_level(logging.ERROR):
        with pytest.raises(ExchangeRatesClientError):
            await billing_process_instance.get_currency_conversion_info(
                organization=get_organization
            )
    assert (
        "[AUT-5305-9928] An error occurred while fetching exchange rates for USD"
        in caplog.messages[0]
    )


# -----------------------------------------------------------------------------------
# - Test generate_refunds()
@pytest.mark.asyncio()
def test_generate_refunds_success(get_daily_expenses):
    """if there are a  trial and an entitlements active, a refund will be generated.
    Trials get priority over entitlements if the periods overlap."""
    response = generate_refunds(
        daily_expenses=get_daily_expenses,
        entitlement_id="FENT-2502-5308-4600",
        entitlement_start_date="2025-06-01T08:22:44.126636Z",
        entitlement_termination_date="2025-06-10T08:22:44.126636Z",
        trial_start_date=date(2025, 6, 1),
        trial_end_date=date(2025, 6, 15),
        billing_start_date=datetime(2025, 6, 1, tzinfo=timezone.utc),
        billing_end_date=datetime(2025, 6, 30, tzinfo=timezone.utc),
    )
    assert isinstance(response, list)
    assert isinstance(response[0], Refund)
    assert response[0].description == "Refund due to trial period (from 01 Jun 2025 to 15 Jun 2025)"
    assert response[0].start_date == date(2025, 6, 1)
    assert response[0].end_date == date(2025, 6, 15)


@pytest.mark.asyncio()
def test_generate_refunds_success_trial_and_entitlements(get_daily_expenses):
    """if there are a  trial and an entitlements active, a refund will be generated.
    Trials get priority over entitlements if the periods overlap."""
    response = generate_refunds(
        daily_expenses=get_daily_expenses,
        entitlement_id="FENT-2502-5308-4600",
        entitlement_start_date="2025-06-01T08:22:44.126636Z",
        entitlement_termination_date="2025-06-30T08:22:44.126636Z",
        trial_start_date=date(2025, 6, 1),
        trial_end_date=date(2025, 6, 15),
        billing_start_date=datetime(2025, 6, 1, tzinfo=timezone.utc),
        billing_end_date=datetime(2025, 6, 30, tzinfo=timezone.utc),
    )
    assert isinstance(response, list)
    assert isinstance(response[0], Refund)
    assert response[0].description == "Refund due to trial period (from 01 Jun 2025 to 15 Jun 2025)"
    assert response[0].start_date == date(2025, 6, 1)
    assert response[0].end_date == date(2025, 6, 15)
    assert response[1].description == "Refund due to active entitlement FENT-2502-5308-4600"
    assert response[1].start_date == date(2025, 6, 16)
    assert response[1].end_date == date(2025, 6, 29)


def test_generate_refunds_no_trial_days(get_daily_expenses):
    """if only an entitlement is active, there will be a refund for that period."""
    response = generate_refunds(
        daily_expenses=get_daily_expenses,
        entitlement_id="FENT-2502-5308-4600",
        entitlement_start_date="2025-06-01T08:22:44.126636Z",
        entitlement_termination_date="2025-06-30T08:22:44.126636Z",
        trial_start_date=None,
        trial_end_date=None,
        billing_start_date=datetime(2025, 6, 1, tzinfo=timezone.utc),
        billing_end_date=datetime(2025, 6, 30, tzinfo=timezone.utc),
    )
    assert isinstance(response, list)
    assert isinstance(response[0], Refund)
    assert response[0].description == "Refund due to active entitlement FENT-2502-5308-4600"
    assert response[0].start_date == date(2025, 6, 1)
    assert response[0].end_date == date(2025, 6, 29)


def test_generate_refunds_no_trial_days_no_entitlement_days(get_daily_expenses):
    """if there are no trials and no entitlements active, there will be no refund."""
    response = generate_refunds(
        daily_expenses=get_daily_expenses,
        entitlement_id="FENT-2502-5308-4600",
        entitlement_start_date="",
        entitlement_termination_date="",
        trial_start_date=None,
        trial_end_date=None,
        billing_start_date=datetime(2025, 6, 1, tzinfo=timezone.utc),
        billing_end_date=datetime(2025, 6, 30, tzinfo=timezone.utc),
    )
    assert isinstance(response, list)
    assert len(response) == 0


def test_generate_refunds_no_entitlement_end_date(get_daily_expenses):
    """if there is only a trial period and the entitlement_termination_date is missing,
    the billing date will be used as value for calculating the refund. The Trials get priority over
    entitlements."""
    response = generate_refunds(
        daily_expenses=get_daily_expenses,
        entitlement_id="FENT-2502-5308-4600",
        entitlement_start_date="2025-06-01T08:22:44.126636Z",
        entitlement_termination_date="",
        trial_start_date=date(2025, 6, 1),
        trial_end_date=date(2025, 6, 15),
        billing_start_date=datetime(2025, 6, 1, tzinfo=timezone.utc),
        billing_end_date=datetime(2025, 6, 30, tzinfo=timezone.utc),
    )
    assert isinstance(response, list)
    assert isinstance(response[0], Refund)
    assert response[0].description == "Refund due to trial period (from 01 Jun 2025 to 15 Jun 2025)"
    assert response[0].start_date == date(2025, 6, 1)
    assert response[0].end_date == date(2025, 6, 15)
    assert response[1].description == "Refund due to active entitlement FENT-2502-5308-4600"
    assert response[1].start_date == date(2025, 6, 16)
    assert response[1].end_date == date(2025, 6, 29)


# ----------------------------------------------------------------------
# - Test process()
@pytest.mark.asyncio()
async def test_process_no_count_active_agreements(billing_process_instance, caplog):
    """if an error occur getting the total number of active agreements,
    an error message will be logged.
    and the error will be added to the list of errors"""
    billing_process_instance.mpt_client = AsyncMock()
    billing_process_instance.mpt_client.count_active_agreements = AsyncMock(return_value=0)
    with caplog.at_level(logging.INFO):
        response = await billing_process_instance.process()
        assert isinstance(response, AuthorizationProcessResult)
        assert response.authorization_id == "AUT-5305-9928"
        assert response.errors[0] == "No active agreement for authorization AUT-5305-9928"


@pytest.mark.asyncio()
async def test_process_success(billing_process_instance, existing_journal_file):
    """if the process completed successfully, all the function are called once."""
    billing_process_instance.mpt_client = AsyncMock()
    billing_process_instance.mpt_client.count_active_agreements = AsyncMock(return_value=2)
    billing_process_instance.write_charges_file = AsyncMock(return_value=True)
    billing_process_instance.mpt_client.get_journal = AsyncMock(
        return_value=existing_journal_file[0]
    )
    billing_process_instance.complete_journal_process = AsyncMock(return_value=None)
    await billing_process_instance.process()
    assert billing_process_instance.complete_journal_process.call_count == 1
    assert billing_process_instance.mpt_client.get_journal.call_count == 1
    assert billing_process_instance.mpt_client.count_active_agreements.call_count == 1
    assert billing_process_instance.write_charges_file.call_count == 1


@pytest.mark.asyncio()
async def test_process_no_charges_written(billing_process_instance, existing_journal_file):
    """if no charges files are written, the complete_journal_process won't be called."""
    billing_process_instance.mpt_client = AsyncMock()
    billing_process_instance.mpt_client.count_active_agreements = AsyncMock(return_value=2)
    billing_process_instance.write_charges_file = AsyncMock(return_value=False)
    billing_process_instance.mpt_client.get_journal = AsyncMock(
        return_value=existing_journal_file[0]
    )
    billing_process_instance.complete_journal_process = AsyncMock(return_value=None)
    await billing_process_instance.process()
    assert billing_process_instance.complete_journal_process.call_count == 0
    assert billing_process_instance.mpt_client.get_journal.call_count == 1
    assert billing_process_instance.mpt_client.count_active_agreements.call_count == 1
    assert billing_process_instance.write_charges_file.call_count == 1


@pytest.mark.asyncio()
async def test_process_failure_http_status_error(billing_process_instance, caplog):
    """if an Exception occurs, an ERROR message will be logger"""
    billing_process_instance.mpt_client = AsyncMock()
    mock_json = {"error": "Invalid request"}
    mock_content = b'{"error": "Invalid request"}'
    mock_response = AsyncMock()
    mock_response.status_code = 400
    mock_response.content = mock_content
    mock_response.headers = {"Content-Type": "application/json"}
    mock_response.json.return_value = mock_json
    mock_request = AsyncMock()
    error = httpx.HTTPStatusError("Bad Request", request=mock_request, response=mock_response)

    billing_process_instance.mpt_client.count_active_agreements.side_effect = error
    with caplog.at_level(logging.ERROR):
        await billing_process_instance.process()
    assert "[AUT-5305-9928] 400 " in caplog.messages[0]


@pytest.mark.asyncio()
async def test_process_failure_http_status_error_no_json(billing_process_instance, caplog):
    """if an Exception occurs, an ERROR message will be logger"""
    billing_process_instance.mpt_client = AsyncMock()
    mock_content = b'{"error": "Invalid request"}'
    mock_response = AsyncMock()
    mock_response.status_code = 400
    mock_response.content = mock_content
    mock_response.headers = {"Content-Type": "application/text"}
    mock_request = AsyncMock()
    error = httpx.HTTPStatusError("Bad Request", request=mock_request, response=mock_response)

    billing_process_instance.mpt_client.count_active_agreements.side_effect = error
    with caplog.at_level(logging.ERROR):
        await billing_process_instance.process()
    assert "[AUT-5305-9928] 400 " in caplog.messages[0]


@pytest.mark.asyncio()
async def test_process_exception(billing_process_instance, caplog):
    """if an Exception occurs, an ERROR message will be logger"""
    billing_process_instance.mpt_client = AsyncMock()
    billing_process_instance.mpt_client.count_active_agreements.side_effect = Exception(
        "No good Reasons"
    )
    with caplog.at_level(logging.ERROR):
        await billing_process_instance.process()
    assert "[AUT-5305-9928] An error occurred: No good Reasons" in caplog.messages[0]


# ------------------------------------------------------------------------------------
# - Test maybe_call()
@pytest.mark.asyncio()
async def test_maybe_call_dry_run_true(billing_process_instance):
    """if dry_run is True, the async function should NOT be executed."""
    mock_func = AsyncMock(return_value="should not be called")
    billing_process_instance.dry_run = True

    result = await billing_process_instance.maybe_call(mock_func, 1, key="value")

    mock_func.assert_not_awaited()
    assert result is None


@pytest.mark.asyncio()
async def test_maybe_call_dry_run_false(billing_process_instance):
    """if dry_run is False, the async function should be executed."""
    mock_func = AsyncMock(return_value="called")

    result = await billing_process_instance.maybe_call(mock_func, 1, key="value")

    mock_func.assert_awaited_once_with(1, key="value")
    assert result == "called"


# -----------------------------------------------------------------------------------
# - Test acquire_semaphore()


@pytest.mark.asyncio()
async def test_acquire_semaphore_acquires_and_releases(billing_process_instance):
    """the semaphore should be acquired and released once for each call"""
    semaphore = AsyncMock()
    billing_process_instance.semaphore = semaphore

    async def inner():
        semaphore.acquire.assert_awaited_once()
        semaphore.release.assert_not_awaited()

    async with billing_process_instance.acquire_semaphore():
        await inner()

    semaphore.release.assert_awaited_once()


# -----------------------------------------------------------------------------------
# - Test build_filepath()
@pytest.mark.parametrize("dry_run", [True, False])
def test_build_filepath_formats_correctly(dry_run, billing_process_instance):
    """a file path should be generated differently based on the value of dry_run"""
    billing_process_instance.dry_run = dry_run

    result = billing_process_instance.build_filepath()
    expected_filename = "charges_AUT-5305-9928_2025_06.jsonl"

    if dry_run:
        assert result == expected_filename
    else:
        assert result.endswith(expected_filename)
        assert result.startswith(tempfile.gettempdir())


# -----------------------------------------------------------------------------------
# - Test process_billing()


@pytest.mark.asyncio()
@patch("ffc.process_billing.MPTAsyncClient")
@patch("ffc.process_billing.AuthorizationProcessor")
@patch("ffc.process_billing.settings")
async def test_process_billing_with_single_authorization(
    mock_settings, mock_processor_cls, mock_client_cls
):
    """if the process_billing() is started with an authorization,
    it fetches the authorization's payload
    and process the related charges and the
    AuthorizationProcessor.process() will be called once"""
    mock_settings.MPT_PRODUCTS_IDS = ["product_1"]

    mock_authorization = {"id": "AUTH1"}
    mock_client = mock_client_cls.return_value
    mock_client.fetch_authorization = AsyncMock(return_value=mock_authorization)

    mock_processor = mock_processor_cls.return_value
    mock_processor.process = AsyncMock()

    from ffc.process_billing import process_billing

    await process_billing(2025, 7, "AUTH1", dry_run=True)

    mock_client.fetch_authorization.assert_awaited_once_with("AUTH1")
    mock_processor_cls.assert_called_once_with(2025, 7, mock_authorization, True)
    mock_processor.process.assert_awaited_once()


@pytest.mark.asyncio()
@patch("ffc.process_billing.MPTAsyncClient")
@patch("ffc.process_billing.AuthorizationProcessor")
@patch("ffc.process_billing.settings")
async def test_process_billing_with_multiple_authorizations(
    mock_settings, mock_processor_cls, mock_mpt_client_cls
):
    """if the process_billing() is started without a given authorization's ID,
    all the authorizations
    will be fetched and for each of them a task for calling the process()
    will be executed"""
    mock_settings.MPT_PRODUCTS_IDS = ["product_1"]
    mock_settings.EXTENSION_CONFIG = {"FFC_BILLING_PROCESS_MAX_CONCURRENCY": "2"}

    async def async_gen():
        yield {"id": "AUTH1"}
        yield {"id": "AUTH2"}

    mock_mpt_client = MagicMock()
    mock_mpt_client.fetch_authorizations = MagicMock(return_value=async_gen())
    mock_mpt_client.close = AsyncMock()
    mock_mpt_client_cls.return_value = mock_mpt_client

    mock_processor = mock_processor_cls.return_value
    mock_processor.process = AsyncMock()

    from ffc.process_billing import process_billing

    await process_billing(2025, 7)

    assert mock_processor_cls.call_count == 2
    mock_processor.process.assert_awaited()
    mock_mpt_client.fetch_authorizations.assert_called_once()
    mock_mpt_client.close.assert_awaited_once()


# -----------------------------------------------------------------------------------
