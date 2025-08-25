from dataclasses import dataclass, field
from datetime import date
from typing import Any

from _decimal import Decimal


class AuthBillingProcess:
    pass


@dataclass
class Datasource:
    linked_datasource_id: str
    linked_datasource_type: str
    datasource_id: str
    datasource_name: str


@dataclass
class Refund:
    amount: Decimal
    start_date: date
    end_date: date
    description: str


@dataclass
class TrialInfo:
    trial_days: set[int] | None = None
    refund_from: date | None = None
    refund_to: date | None = None


@dataclass
class CurrencyConversionInfo:
    base_currency: str
    billing_currency: str
    exchange_rate: Decimal
    exchange_rates: dict[str, Any] | None = None


@dataclass
class AuthorizationProcessResult:
    authorization_id: str
    errors: list[str] = field(default_factory=list)
