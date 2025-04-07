import logging

from swo.mpt.client.mpt import (
    complete_order,
    get_product_template_or_default,
    query_order,
    update_agreement,
)
from swo.mpt.extensions.flows.pipeline import Step

from ffc.flows.error import (
    ERR_ADMIN_CONTACT,
    ERR_CURRENCY,
    ERR_ORGANIZATION_NAME,
)
from ffc.flows.order import MPT_ORDER_STATUS_COMPLETED, MPT_ORDER_STATUS_QUERYING
from ffc.notifications import send_email_notification
from ffc.parameters import (
    PARAM_ADMIN_CONTACT,
    PARAM_CURRENCY,
    PARAM_ORGANIZATION_NAME,
    get_ordering_parameter,
    set_ordering_parameter_error,
)

logger = logging.getLogger(__name__)


class SetupAgreementExternalId(Step):
    """
    Update existing agreement vendor id with created FFC Organization Id
    """

    def __call__(self, client, context, next_step):
        organization = context.organization
        agreement_id = context.order["agreement"]["id"]

        update_agreement(
            client,
            context.order["agreement"]["id"],
            externalIds={"vendor": organization["id"]},
        )
        logger.info(
            f"{context}: Updating agreement {agreement_id} external id to {organization['id']}",
        )

        next_step(client, context)


class CompleteOrder(Step):
    def __init__(self, template_name):
        self.template_name = template_name

    def __call__(self, client, context, next_step):
        template = get_product_template_or_default(
            client,
            context.product_id,
            MPT_ORDER_STATUS_COMPLETED,
            self.template_name,
        )
        agreement = context.order["agreement"]
        context.order = complete_order(
            client,
            context.order["id"],
            template,
            parameters=context.order["parameters"],
        )
        context.order["agreement"] = agreement
        send_email_notification(client, context.order)
        logger.info(f"{context}: order has been completed successfully")
        next_step(client, context)


class CheckOrderParameters(Step):
    """
    Check if all required parameters are submitted, if not
    query order
    """

    def __call__(self, client, context, next_step):
        errors = {
            PARAM_ORGANIZATION_NAME: ERR_ORGANIZATION_NAME,
            PARAM_CURRENCY: ERR_CURRENCY,
            PARAM_ADMIN_CONTACT: ERR_ADMIN_CONTACT,
        }
        order = context.order
        empty_parameters = []

        for param_name in [
            PARAM_ORGANIZATION_NAME,
            PARAM_CURRENCY,
            PARAM_ADMIN_CONTACT,
        ]:
            parameter = get_ordering_parameter(order, param_name)
            if not parameter.get("value"):
                order = set_ordering_parameter_error(
                    order, param_name, errors[param_name]
                )
                empty_parameters.append(param_name)

        if empty_parameters:
            template = get_product_template_or_default(
                client,
                context.product_id,
                MPT_ORDER_STATUS_QUERYING,
            )
            agreement = order["agreement"]
            order = query_order(client, order["id"], template=template)
            order["agreement"] = agreement
            context.order = order
            logger.info(
                f"{context}: parameters {', '.join(empty_parameters)} are empty, move to querying",
            )
            send_email_notification(client, order)
            return

        next_step(client, context)
