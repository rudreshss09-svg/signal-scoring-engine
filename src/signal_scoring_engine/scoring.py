"""Score accounts that pass every gate and rank them deterministically."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date

from .config import ScoringConfig
from .decay import age_in_days, decay_factor
from .gates import GateResult, SignalStatus, classify_signal, run_gates
from .models import Account

QUALIFIED = "qualified"
REJECTED = "rejected"


@dataclass(frozen=True)
class SignalContribution:
    signal_type: str
    observed_at: date
    detail: str
    status: SignalStatus
    age_days: int
    weight: float
    half_life_days: float
    decay_factor: float
    points: float


@dataclass(frozen=True)
class BonusContribution:
    name: str
    signals: tuple[str, ...]
    bonus: float


@dataclass(frozen=True)
class AccountResult:
    account: Account
    status: str
    gate_results: tuple[GateResult, ...]
    signals: tuple[SignalContribution, ...]
    bonuses: tuple[BonusContribution, ...]
    signal_points: float
    bonus_points: float
    score: float | None
    rank: int | None = None

    @property
    def rejected_at(self) -> str | None:
        last = self.gate_results[-1]
        return None if last.passed else last.gate

    @property
    def reason(self) -> str:
        last = self.gate_results[-1]
        return "Passed all gates" if last.passed else last.reason


def evaluate_signals(account: Account, config: ScoringConfig) -> list[SignalContribution]:
    """Break every signal down into age, decay and points. Only fresh signals earn points."""
    contributions = []
    for signal in account.signals:
        spec = config.signal_types[signal.type]
        status = classify_signal(signal, config)
        age = age_in_days(signal.observed_at, config.as_of)
        factor = decay_factor(age, spec.half_life_days) if status != SignalStatus.FUTURE else 0.0
        # Round each contribution once, here, so the parts shown to a user always
        # add up exactly to the totals shown alongside them.
        points = round(spec.weight * factor, 2) if status == SignalStatus.FRESH else 0.0
        contributions.append(
            SignalContribution(
                signal_type=signal.type,
                observed_at=signal.observed_at,
                detail=signal.detail,
                status=status,
                age_days=age,
                weight=spec.weight,
                half_life_days=spec.half_life_days,
                decay_factor=factor,
                points=points,
            )
        )
    # Highest contribution first, then by type and date so output order never varies.
    contributions.sort(key=lambda c: (-c.points, c.signal_type, c.observed_at))
    return contributions


def evaluate_bonuses(
    contributions: list[SignalContribution], config: ScoringConfig
) -> list[BonusContribution]:
    fresh_types = {c.signal_type for c in contributions if c.status == SignalStatus.FRESH}
    return [
        BonusContribution(name=combo.name, signals=combo.signals, bonus=round(combo.bonus, 2))
        for combo in config.combinations
        if set(combo.signals) <= fresh_types
    ]


def score_account(account: Account, config: ScoringConfig) -> AccountResult:
    gate_results = run_gates(account, config)
    contributions = evaluate_signals(account, config)
    if not gate_results[-1].passed:
        # Rejection-first: rejected accounts are explained but never scored or ranked.
        return AccountResult(
            account=account,
            status=REJECTED,
            gate_results=tuple(gate_results),
            signals=tuple(contributions),
            bonuses=(),
            signal_points=0.0,
            bonus_points=0.0,
            score=None,
        )

    bonuses = evaluate_bonuses(contributions, config)
    # Inputs are already rounded to cents; round again only to drop float noise.
    signal_points = round(sum(c.points for c in contributions), 2)
    bonus_points = round(sum(b.bonus for b in bonuses), 2)
    return AccountResult(
        account=account,
        status=QUALIFIED,
        gate_results=tuple(gate_results),
        signals=tuple(contributions),
        bonuses=tuple(bonuses),
        signal_points=signal_points,
        bonus_points=bonus_points,
        score=round(signal_points + bonus_points, 2),
    )


def rank_accounts(accounts: list[Account], config: ScoringConfig) -> list[AccountResult]:
    """Score every account and return qualified accounts ranked first, then rejected ones.

    Ties on score are broken by account_id so the order is fully deterministic.
    """
    results = [score_account(a, config) for a in accounts]
    qualified = sorted(
        (r for r in results if r.status == QUALIFIED),
        key=lambda r: (-(r.score or 0.0), r.account.account_id),
    )
    rejected = sorted(
        (r for r in results if r.status == REJECTED), key=lambda r: r.account.account_id
    )
    ranked = [replace(r, rank=i) for i, r in enumerate(qualified, start=1)]
    return ranked + rejected
