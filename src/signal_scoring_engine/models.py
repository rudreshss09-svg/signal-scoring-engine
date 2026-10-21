"""Core data structures for accounts and their buying signals."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass(frozen=True)
class Signal:
    """A single timestamped buying signal observed for an account."""

    type: str
    observed_at: date
    detail: str = ""


@dataclass(frozen=True)
class Account:
    """A target account with firmographics, tech stack and observed signals."""

    account_id: str
    company_name: str
    domain: str
    industry: str
    employee_count: int
    region: str
    tech_stack: tuple[str, ...] = ()
    signals: tuple[Signal, ...] = field(default_factory=tuple)
