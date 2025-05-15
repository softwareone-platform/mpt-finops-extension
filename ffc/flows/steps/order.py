import logging

from mpt_extension_sdk.flows.pipeline import Step
from mpt_extension_sdk.mpt_http.mpt import (
    complete_order,
    get_product_template_or_default,
    query_order,
    update_agreement,
    update_order,
)

from ffc.flows.error import (
    ERR_ADMIN_CONTACT,
    ERR_CURRENCY,
    ERR_ORGANIZATION_NAME,
)
from ffc.flows.order import (
    MPT_ORDER_STATUS_COMPLETED,
    MPT_ORDER_STATUS_PROCESSING,
    MPT_ORDER_STATUS_QUERYING,
    PURCHASE_EXISTING_TEMPLATE_NAME,
    set_template,
)
from ffc.flows.steps.utils import reset_order_error, switch_order_to_failed
from ffc.notifications import send_email_notification
from ffc.parameters import (
    PARAM_ADMIN_CONTACT,
    PARAM_CURRENCY,
    PARAM_IS_NEW_USER,
    PARAM_ORGANIZATION_NAME,
    get_due_date,
    get_fulfillment_parameter,
    get_ordering_parameter,
    reset_ordering_parameters_error,
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
    """
    Completes the order using pass template name or default
    """

    def __init__(self, template_name):
        self.template_name = template_name

    def get_template_name(self, client, context):
        return self.template_name

    def __call__(self, client, context, next_step):
        template = get_product_template_or_default(
            client,
            context.product_id,
            MPT_ORDER_STATUS_COMPLETED,
            self.get_template_name(client, context),
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


class CompletePurchaseOrder(CompleteOrder):
    def get_template_name(self, client, context):
        """
        Returns special template if user has purchased another account for FinOps
        by default returns usual purchase template
        """
        order = context.order

        is_new_user_param = get_fulfillment_parameter(order, PARAM_IS_NEW_USER)

        if is_new_user_param.get("value") == ["Yes"]:
            return PURCHASE_EXISTING_TEMPLATE_NAME

        return super().get_template_name(client, context)


class CheckOrderParameters(Step):
    """
    Check if all required parameters are submitted
    If not sets `validation_succeeded` to False
    """

    def __call__(self, client, context, next_step):
        errors = {
            PARAM_ORGANIZATION_NAME: ERR_ORGANIZATION_NAME,
            PARAM_CURRENCY: ERR_CURRENCY,
            PARAM_ADMIN_CONTACT: ERR_ADMIN_CONTACT,
        }
        order = context.order

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
                context.validation_succeeded = False

        next_step(client, context)


class QueryIfInvalid(Step):
    """
    Check if `validation_succeeded` context parameter is True
    If not - query order
    """

    def __call__(self, client, context, next_step):
        order = context.order
        if not context.validation_succeeded:
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
                f"{context}: ordering parameters are invalid, move to querying",
            )
            send_email_notification(client, order)
            return

        next_step(client, context)


class ResetOrderErrors(Step):
    """
    Reset order errors and parameter errors. Is used before processing
    to not to show errors during procesing or after validation is succeseed
    """

    def __call__(self, client, context, next_step):
        context.order = reset_order_error(context.order)
        context.order = reset_ordering_parameters_error(context.order)

        next_step(client, context)


class StartOrderProcessing(Step):
    """
    Set the template for the processing status
    """

    def __init__(self, template_name):
        self.template_name = template_name

    def __call__(self, client, context, next_step):
        template = get_product_template_or_default(
            client,
            context.order["agreement"]["product"]["id"],
            MPT_ORDER_STATUS_PROCESSING,
            self.template_name,
        )
        current_template_id = context.order.get("template", {}).get("id")
        if template["id"] != current_template_id:
            context.order = set_template(context.order, template)
            update_order(
                client, context.order["id"], template=context.order["template"]
            )
            logger.info(
                f"{context}: processing template set to {self.template_name} "
                f"({template['id']})"
            )
        logger.info(f"{context}: processing template is ok, continue")

        if not get_due_date(context.order):
            send_email_notification(client, context.order)

        next_step(client, context)


class FailOrder(Step):
    """
    Fail the order with an error
    """

    def __init__(self, error):
        self.error = error

    def __call__(self, client, context, next_step):
        switch_order_to_failed(
            client,
            context.order,
            self.error.to_dict(order_type=context.order["type"]),
        )
