from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from signal_scoring_engine.config import ScoringConfig, parse_config
from signal_scoring_engine.models import Account, Signal

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config" / "scoring.toml"
ACCOUNTS_PATH = ROOT / "data" / "accounts.json"


@pytest.fixture
def config() -> ScoringConfig:
    """Small, hand-checkable config independent of the shipped demo config."""
    return parse_config(
        {
            "as_of": date(2026, 10, 1),
            "freshness": {"max_signal_age_days": 100},
            "signals": {
                "funding_round": {"weight": 40.0, "half_life_days": 50},
                "sdr_job_posting": {"weight": 20.0, "half_life_days": 10},
                "headcount_growth": {"weight": 10.0, "half_life_days": 30},
            },
            "combinations": [
                {
                    "name": "funded_and_hiring",
                    "signals": ["funding_round", "sdr_job_posting"],
                    "bonus": 15.0,
                },
            ],
            "icp": {
                "industries": ["B2B SaaS"],
                "min_employees": 20,
                "max_employees": 200,
                "regions": ["Europe"],
            },
            "tool_conflict": {"conflicting_tools": ["sales_engagement_platform"]},
        }
    )


def make_account(
    account_id: str = "T-1",
    *,
    industry: str = "B2B SaaS",
    employee_count: int = 50,
    region: str = "Europe",
    tech_stack: tuple[str, ...] = ("crm",),
    signals: tuple[tuple[str, str], ...] = (("funding_round", "2026-09-21"),),
) -> Account:
    return Account(
        account_id=account_id,
        company_name=f"Test Co {account_id}",
        domain=f"{account_id.lower()}.example",
        industry=industry,
        employee_count=employee_count,
        region=region,
        tech_stack=tech_stack,
        signals=tuple(Signal(t, date.fromisoformat(d)) for t, d in signals),
    )
