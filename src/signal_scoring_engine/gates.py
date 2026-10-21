"""Ordered rejection gates.

Gates run in a fixed order and evaluation stops at the first failure, so every
rejected account has exactly one rejection reason: the earliest gate it failed.
Cheap, structural checks (ICP fit, tool conflict) run before signal checks.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum

from .config import ScoringConfig
from .decay import age_in_days
from .models import Account, Signal


class SignalStatus(StrEnum):
    FRESH = "fresh"
    STALE = "stale"
    FUTURE = "future"


@dataclass(frozen=True)
class GateResult:
    gate: str
    passed: bool
    reason: str


def classify_signal(signal: Signal, config: ScoringConfig) -> SignalStatus:
    """Fresh signals count toward the score. Stale and future signals do not.

    Signals dated after the as-of date are treated as not yet observed, which
    keeps runs reproducible when replaying the same data at an earlier date.
    """
    age = age_in_days(signal.observed_at, config.as_of)
    if age < 0:
        return SignalStatus.FUTURE
    if age > config.max_signal_age_days:
        return SignalStatus.STALE
    return SignalStatus.FRESH


def icp_fit_gate(account: Account, config: ScoringConfig) -> GateResult:
    icp = config.icp
    if account.industry not in icp.industries:
        return GateResult("icp_fit", False, f"Industry '{account.industry}' is outside the ICP")
    if not icp.min_employees <= account.employee_count <= icp.max_employees:
        return GateResult(
            "icp_fit",
            False,
            f"{account.employee_count} employees is outside the "
            f"{icp.min_employees}-{icp.max_employees} ICP range",
        )
    if account.region not in icp.regions:
        return GateResult("icp_fit", False, f"Region '{account.region}' is outside the ICP")
    return GateResult(
        "icp_fit",
        True,
        f"{account.industry}, {account.employee_count} employees, {account.region}",
    )


def tool_conflict_gate(account: Account, config: ScoringConfig) -> GateResult:
    conflicts = sorted(set(account.tech_stack) & set(config.conflicting_tools))
    if conflicts:
        return GateResult(
            "tool_conflict",
            False,
            f"Already uses {', '.join(conflicts)}, so an outbound motion likely exists",
        )
    return GateResult("tool_conflict", True, "No conflicting tools in tech stack")


def signal_freshness_gate(account: Account, config: ScoringConfig) -> GateResult:
    observed = [s for s in account.signals if classify_signal(s, config) != SignalStatus.FUTURE]
    if not observed:
        return GateResult(
            "signal_freshness", False, f"No buying signals observed on or before {config.as_of}"
        )
    fresh = [s for s in observed if classify_signal(s, config) == SignalStatus.FRESH]
    if not fresh:
        newest_age = min(age_in_days(s.observed_at, config.as_of) for s in observed)
        return GateResult(
            "signal_freshness",
            False,
            f"All signals are stale: newest is {newest_age} days old "
            f"(limit {config.max_signal_age_days})",
        )
    return GateResult(
        "signal_freshness",
        True,
        f"{len(fresh)} fresh signal(s) within {config.max_signal_age_days} days",
    )


Gate = Callable[[Account, ScoringConfig], GateResult]

GATES: tuple[Gate, ...] = (icp_fit_gate, tool_conflict_gate, signal_freshness_gate)


def run_gates(account: Account, config: ScoringConfig) -> list[GateResult]:
    """Run gates in order, stopping after the first failure."""
    results: list[GateResult] = []
    for gate in GATES:
        result = gate(account, config)
        results.append(result)
        if not result.passed:
            break
    return results
