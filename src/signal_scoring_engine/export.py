"""CSV export and human-readable reports."""

from __future__ import annotations

import csv
import io
from collections.abc import Iterable
from pathlib import Path

from .gates import SignalStatus
from .scoring import AccountResult

CSV_COLUMNS = (
    "rank",
    "account_id",
    "company_name",
    "status",
    "score",
    "signal_points",
    "bonus_points",
    "rejected_at_gate",
    "reason",
    "fresh_signals",
    "bonuses",
)


def to_row(result: AccountResult) -> dict[str, str]:
    qualified = result.score is not None
    fresh = [c for c in result.signals if c.status == SignalStatus.FRESH]
    return {
        "rank": "" if result.rank is None else str(result.rank),
        "account_id": result.account.account_id,
        "company_name": result.account.company_name,
        "status": result.status,
        "score": f"{result.score:.2f}" if qualified else "",
        "signal_points": f"{result.signal_points:.2f}" if qualified else "",
        "bonus_points": f"{result.bonus_points:.2f}" if qualified else "",
        "rejected_at_gate": result.rejected_at or "",
        "reason": result.reason,
        "fresh_signals": "; ".join(f"{c.signal_type}={c.points:.2f}" for c in fresh)
        if qualified
        else "; ".join(c.signal_type for c in fresh),
        "bonuses": "; ".join(f"{b.name}=+{b.bonus:.2f}" for b in result.bonuses),
    }


def results_to_csv(results: Iterable[AccountResult]) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for result in results:
        writer.writerow(to_row(result))
    return buffer.getvalue()


def write_csv(results: Iterable[AccountResult], path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(results_to_csv(results), encoding="utf-8", newline="")
    return path


def format_table(results: list[AccountResult]) -> str:
    """Fixed-width summary table for the terminal."""
    header = f"{'Rank':>4}  {'Account':<8}  {'Company':<22}  {'Status':<9}  {'Score':>6}  Reason"
    lines = [header, "-" * len(header)]
    for r in results:
        rank = "" if r.rank is None else str(r.rank)
        score = "" if r.score is None else f"{r.score:.2f}"
        reason = r.reason if r.rejected_at is None else f"[{r.rejected_at}] {r.reason}"
        lines.append(
            f"{rank:>4}  {r.account.account_id:<8}  {r.account.company_name:<22}  "
            f"{r.status:<9}  {score:>6}  {reason}"
        )
    return "\n".join(lines)


def format_explanation(result: AccountResult, as_of: str) -> str:
    """Step-by-step explanation of how an account was gated and scored."""
    a = result.account
    lines = [
        f"{a.company_name} ({a.account_id}, {a.domain})",
        f"As of {as_of}: {result.status.upper()}"
        + (f", rank {result.rank}, score {result.score:.2f}" if result.score is not None else ""),
        "",
        "Gates (in order, stops at first failure):",
    ]
    for g in result.gate_results:
        lines.append(f"  [{'PASS' if g.passed else 'FAIL'}] {g.gate}: {g.reason}")

    lines += ["", "Signals:"]
    if not result.signals:
        lines.append("  (none)")
    for c in result.signals:
        prefix = f"  {c.signal_type:<18} {c.observed_at}  "
        if c.status == SignalStatus.FUTURE:
            lines.append(prefix + "ignored: dated after the as-of date")
        elif c.status == SignalStatus.STALE:
            lines.append(prefix + f"{c.age_days:>3}d old  ignored: stale")
        elif result.score is None:
            lines.append(prefix + f"{c.age_days:>3}d old  fresh, not scored")
        else:
            # Show the exact formula rather than a rounded decay factor, so the
            # line can be checked by hand without rounding drift.
            lines.append(
                prefix + f"{c.age_days:>3}d old  {c.weight:g} x 0.5^({c.age_days}/"
                f"{c.half_life_days:g}) = {c.points:.2f}"
            )

    if result.score is not None:
        lines += ["", "Combination bonuses:"]
        if not result.bonuses:
            lines.append("  (none)")
        for b in result.bonuses:
            lines.append(f"  {b.name}: +{b.bonus:.2f} ({' + '.join(b.signals)})")
        lines += [
            "",
            f"Score = {result.signal_points:.2f} signal points "
            f"+ {result.bonus_points:.2f} bonus points = {result.score:.2f}",
        ]
    else:
        lines += ["", "Not scored: rejected accounts are explained but never ranked."]
    return "\n".join(lines)
