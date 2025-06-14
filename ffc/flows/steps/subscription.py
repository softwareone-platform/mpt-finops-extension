import logging

from mpt_extension_sdk.flows.pipeline import Step
from mpt_extension_sdk.mpt_http.mpt import create_subscription

from ffc.flows.order import get_subscription_by_line_and_item_id

logger = logging.getLogger(__name__)


class CreateSubscription(Step):
    def __call__(self, client, context, next_step):
        for line in context.order["lines"]:
            order_subscription = get_subscription_by_line_and_item_id(
                context.order["subscriptions"],
                line["item"]["id"],
                line["id"],
            )
            if not order_subscription:
                subscription = {
                    "name": f"Subscription for {line['item']['name']}",
                    "parameters": {},
                    "externalIds": {"vendor": context.organization["id"]},
                    "lines": [
                        {
                            "id": line["id"],
                        },
                    ],
                }
                subscription = create_subscription(
                    client,
                    context.order["id"],
                    subscription,
                )
                logger.info(
                    f'{context}: subscription {line["id"]} ' f'({subscription["id"]}) created'
                )
        next_step(client, context)
