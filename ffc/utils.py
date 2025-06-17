from datetime import datetime
from uuid import uuid4

from django.conf import settings


def find_first(func, iterable, default=None):
    return next(filter(func, iterable), default)


def get_ff_parameter(agreement, parameter_name, is_date=False):
    for parameter in agreement["parameters"]["fulfillment"]:
        if parameter["externalId"] == parameter_name and parameter.get("value"):
            if is_date:
                return datetime.strptime(parameter["value"], "%Y-%m-%d").date()
            return parameter["value"]
    return None


def convert_expenses_to_daily(expenses):
    daily_expenses = {0: 0}
    for day in range(1, len(expenses) + 1):
        if day not in expenses:
            daily_expenses[day] = 0
            continue
        daily_expenses[day] = expenses[day] - expenses[day - 1]

    return daily_expenses


async def async_groupby(
    iterable,
    key,
):
    current_group = []
    current_key = None
    first_item = True

    async for item in iterable:
        k = key(item)
        if first_item:
            current_key = k
            current_group.append(item)
            first_item = False
        elif k == current_key:
            current_group.append(item)
        else:
            yield current_key, current_group
            current_key = k
            current_group = [item]

    if current_group:
        yield current_key, current_group
