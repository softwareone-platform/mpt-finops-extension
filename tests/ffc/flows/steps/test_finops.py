from ffc.client import FinOpsNotFoundError
from ffc.flows.order import OrderContext
from ffc.flows.steps.finops import (
    CreateEmployee,
    CreateOrganization,
    DeleteOrganization,
)
from ffc.parameters import (
    PARAM_ADMIN_CONTACT,
    PARAM_CURRENCY,
    PARAM_ORGANIZATION_NAME,
    get_ordering_parameter,
)


def test_create_employee_exists(
    mocker,
    mocked_next_step,
    mpt_client,
    processing_purchase_order,
    ffc_employee,
):
    mocked_ffc_client = mocker.MagicMock()
    mocked_ffc_client.get_employee.return_value = ffc_employee
    mocker.patch(
        "ffc.flows.steps.finops.get_ffc_client", return_value=mocked_ffc_client
    )

    ctx = OrderContext(order=processing_purchase_order)
    step = CreateEmployee()

    step(mpt_client, ctx, mocked_next_step)

    assert ctx.employee == ffc_employee
    mocked_next_step.assert_called_once()
    administrator = get_ordering_parameter(
        processing_purchase_order,
        PARAM_ADMIN_CONTACT,
    )["value"]
    mocked_ffc_client.get_employee.assert_called_once_with(administrator["email"])


def test_create_employee(
    mocker,
    mocked_next_step,
    mpt_client,
    processing_purchase_order,
    ffc_employee,
):
    mocked_ffc_client = mocker.MagicMock()
    mocked_ffc_client.get_employee.side_effect = FinOpsNotFoundError("not-found")
    mocked_ffc_client.create_employee.return_value = ffc_employee
    mocker.patch(
        "ffc.flows.steps.finops.get_ffc_client", return_value=mocked_ffc_client
    )

    ctx = OrderContext(order=processing_purchase_order)
    step = CreateEmployee()

    step(mpt_client, ctx, mocked_next_step)

    assert ctx.employee == ffc_employee
    mocked_next_step.assert_called_once()
    administrator = get_ordering_parameter(
        processing_purchase_order,
        PARAM_ADMIN_CONTACT,
    )["value"]
    mocked_ffc_client.create_employee.assert_called_once_with(
        administrator["email"],
        f"{administrator['firstName']} {administrator['lastName']}",
    )


def test_create_organization(
    mocker,
    mocked_next_step,
    mpt_client,
    processing_purchase_order,
    ffc_employee,
    ffc_organization,
):
    mocked_ffc_client = mocker.MagicMock()
    mocked_ffc_client.create_organization.return_value = ffc_organization
    mocked_ffc_client.get_organizations_by_external_id.return_value = []
    mocker.patch(
        "ffc.flows.steps.finops.get_ffc_client", return_value=mocked_ffc_client
    )

    ctx = OrderContext(order=processing_purchase_order)
    ctx.employee = ffc_employee
    step = CreateOrganization()

    step(mpt_client, ctx, mocked_next_step)

    assert ctx.organization == ffc_organization
    mocked_next_step.assert_called_once()
    organization_name = get_ordering_parameter(
        processing_purchase_order,
        PARAM_ORGANIZATION_NAME,
    )["value"]
    currency = get_ordering_parameter(
        processing_purchase_order,
        PARAM_CURRENCY,
    )["value"]

    mocked_ffc_client.create_organization.assert_called_once_with(
        organization_name,
        currency,
        processing_purchase_order["authorization"]["currency"],
        processing_purchase_order["agreement"]["id"],
        ffc_employee["id"],
    )


def test_create_organization_exists(
    mocker,
    mocked_next_step,
    mpt_client,
    processing_purchase_order,
    ffc_employee,
    ffc_organization,
):
    mocked_ffc_client = mocker.MagicMock()
    mocked_ffc_client.get_organizations_by_external_id.return_value = [ffc_organization]
    mocker.patch(
        "ffc.flows.steps.finops.get_ffc_client", return_value=mocked_ffc_client
    )

    ctx = OrderContext(order=processing_purchase_order)
    ctx.employee = ffc_employee
    step = CreateOrganization()

    step(mpt_client, ctx, mocked_next_step)

    assert ctx.organization == ffc_organization
    mocked_next_step.assert_called_once()
    mocked_ffc_client.get_organizations_by_external_id.assert_called_once_with(
        processing_purchase_order["agreement"]["id"],
    )
    mocked_ffc_client.create_organization.assert_not_called()


def test_delete_organization(
    mocker,
    mocked_next_step,
    mpt_client,
    processing_termination_order,
    ffc_organization,
):
    mocked_ffc_client = mocker.MagicMock()
    mocked_ffc_client.delete_organization.return_value = None
    mocked_ffc_client.get_organizations_by_external_id.return_value = [ffc_organization]
    mocker.patch("ffc.flows.steps.finops.get_ffc_client", return_value=mocked_ffc_client)

    ctx = OrderContext(order=processing_termination_order)
    step = DeleteOrganization()
    step(mpt_client, ctx, mocked_next_step)

    assert ctx.organization == ffc_organization
    mocked_next_step.assert_called_once()
    mocked_ffc_client.get_organizations_by_external_id.assert_called_once_with(
        agreement_id=processing_termination_order["agreement"]["id"],
    )
    mocked_ffc_client.delete_organization.assert_called_once_with(ffc_organization["id"])


def test_delete_organization_deleted_or_not_found(
    mocker,
    mocked_next_step,
    mpt_client,
    processing_termination_order,
    ffc_organization,
):
    ffc_organization["status"] = "deleted"
    mocked_ffc_client = mocker.MagicMock()
    mocked_ffc_client.get_organizations_by_external_id.return_value = [ffc_organization]
    mocker.patch("ffc.flows.steps.finops.get_ffc_client", return_value=mocked_ffc_client)

    ctx = OrderContext(order=processing_termination_order)
    step = DeleteOrganization()

    step(mpt_client, ctx, mocked_next_step)

    assert ctx.organization is None
    mocked_next_step.assert_called_once()
    mocked_ffc_client.get_organizations_by_external_id.assert_called_once_with(
        agreement_id=processing_termination_order["agreement"]["id"],
    )
    mocked_ffc_client.delete_organization.assert_not_called()

    mocked_ffc_client.get_organizations_by_external_id.return_value = []
    mocker.patch("ffc.flows.steps.finops.get_ffc_client", return_value=mocked_ffc_client)

    step(mpt_client, ctx, mocked_next_step)

    mocked_ffc_client.delete_organization.assert_not_called()
    assert ctx.organization is None
