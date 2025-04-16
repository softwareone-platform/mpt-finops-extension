import logging

from swo.mpt.extensions.flows.pipeline import Step

from ffc.client import FinOpsNotFoundError, get_ffc_client
from ffc.parameters import (
    PARAM_ADMIN_CONTACT,
    PARAM_CURRENCY,
    PARAM_ORGANIZATION_NAME,
    get_ordering_parameter,
)

logger = logging.getLogger(__name__)


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
