import logging

from mpt_extension_sdk.flows.pipeline import Step
from mpt_extension_sdk.mpt_http.mpt import update_order

from ffc.client import FinOpsNotFoundError, get_ffc_client
from ffc.parameters import (
    PARAM_ADMIN_CONTACT,
    PARAM_CURRENCY,
    PARAM_ORGANIZATION_NAME,
    get_ordering_parameter,
    set_is_new_user,
)

logger = logging.getLogger(__name__)

DELETED_ORGANIZATION = "deleted"


class CreateEmployee(Step):
    """
    Create employee in FinOps for Cloud if it doesn't exist
    """

    def __call__(self, client, context, next_step):
        order = context.order
        ffc_client = get_ffc_client()

        administrator = get_ordering_parameter(order, PARAM_ADMIN_CONTACT)["value"]

        try:
            employee = ffc_client.get_employee(administrator["email"])
            context.order = set_is_new_user(context.order, True)
            update_order(client, context.order["id"], parameters=context.order["parameters"])
            logger.info(f"{context}: employee exists {employee['id']}")
        except FinOpsNotFoundError:
            employee = ffc_client.create_employee(
                administrator["email"],
                f"{administrator['firstName']} {administrator['lastName']}",
            )
            logger.info(f"{context}: employee created {employee['id']}")

        context.employee = employee
        next_step(client, context)


class CreateOrganization(Step):
    """
    Create organization with employee as an admin
    """

    def __call__(self, client, context, next_step):
        ffc_client = get_ffc_client()
        order = context.order
        agreement_id = order["agreement"]["id"]

        organizations = ffc_client.get_organizations_by_external_id(
            agreement_id,
        )
        organization = organizations and organizations[0]
        if not organization:
            organization = ffc_client.create_organization(
                get_ordering_parameter(order, PARAM_ORGANIZATION_NAME)["value"],
                get_ordering_parameter(order, PARAM_CURRENCY)["value"],
                order["authorization"]["currency"],
                agreement_id,
                context.employee["id"],
            )
            logger.info(f"{context}: organization created {organization['id']}")
        else:
            logger.info(
                f"{context}: organization for {agreement_id} was created {organization['id']}. Skip"
            )
        context.organization = organization

        next_step(client, context)


class DeleteOrganization(Step):
    """
    Delete given organization
    """

    def __call__(self, client, context, next_step):
        ffc_client = get_ffc_client()
        order = context.order
        agreement_id = order["agreement"]["id"]

        organizations = ffc_client.get_organizations_by_external_id(agreement_id=agreement_id)
        organization = organizations and organizations[0]

        if organization and organization["status"] != DELETED_ORGANIZATION:
            ffc_client.delete_organization(organization["id"])
            logger.info(f"{context}: organization deleted {organization['id']}")

            context.organization = organization
        else:
            logger.info(
                f"{context}: organization is already deleted or not found for {agreement_id}. Skip"
            )

        next_step(client, context)
