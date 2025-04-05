import copy
import functools
from datetime import datetime

from ffc.utils import find_first

PARAM_PHASE_ORDERING = "ordering"
PARAM_PHASE_FULFILLMENT = "fulfillment"
PARAM_CONTACT = "contact"

PARAM_DUE_DATE = "dueDate"

PARAM_ORGANIZATION_NAME = "organizationName"
PARAM_CURRENCY = "currency"
PARAM_ADMIN_CONTACT = "adminContact"


def get_parameter(parameter_phase, source, param_external_id):
    """
    Returns a parameter of a given phase by its external identifier.
    Returns an empty dictionary if the parameter is not found.
    Args:
        parameter_phase (str): The phase of the parameter (ordering, fulfillment).
        source (str): The source business object from which the parameter
        should be extracted.
        param_external_id (str): The unique external identifier of the parameter.

    Returns:
        dict: The parameter object or an empty dictionary if not found.
    """
    return find_first(
        lambda x: x.get("externalId") == param_external_id,
        source["parameters"][parameter_phase],
        default={},
    )


get_ordering_parameter = functools.partial(get_parameter, PARAM_PHASE_ORDERING)

get_fulfillment_parameter = functools.partial(get_parameter, PARAM_PHASE_FULFILLMENT)


def set_ordering_parameter_error(order, param_external_id, error, required=True):
    """
    Set a validation error on an ordering parameter.

    Args:
        order (dict): The order that contains the parameter.
        param_external_id (str): The external identifier of the parameter.
        error (dict): The error (id, message) that must be set.

    Returns:
        dict: The order updated.
    """
    updated_order = copy.deepcopy(order)
    param = get_ordering_parameter(
        updated_order,
        param_external_id,
    )
    param["error"] = error
    param["constraints"] = {
        "hidden": False,
        "required": required,
    }
    return updated_order


def get_due_date(order):
    """
    Returns Due Date parameter value or None
    """
    due_date_parameter = get_fulfillment_parameter(order, PARAM_DUE_DATE)

    if due_date_parameter.get("value", ""):
        return datetime.strptime(due_date_parameter["value"], "%Y-%m-%d").date()

    return None


def set_due_date(order, due_date):
    """
    Set Due Date parameter
    Args:
        order (dict): Order to be updated
        due_date (date|None): due date
    """
    updated_order = copy.deepcopy(order)

    if due_date:
        due_date = due_date.strftime("%Y-%m-%d")

    param = get_fulfillment_parameter(updated_order, PARAM_DUE_DATE)
    param["value"] = due_date

    return updated_order


def reset_ordering_parameters_error(order):
    """
    Reset errors for all ordering parameters

    Args:
        order (dict): The order that contains the parameter.

    Returns:
        dict: The order updated.
    """
    updated_order = copy.deepcopy(order)

    for param in updated_order["parameters"][PARAM_PHASE_ORDERING]:
        param["error"] = None

    return updated_order
