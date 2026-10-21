"""Command-line interface: ``signal-score rank`` and ``signal-score explain``."""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence
from datetime import date

from .config import ConfigError, ScoringConfig, load_config
from .data import DataError, load_accounts
from .export import format_explanation, format_table, write_csv
from .scoring import QUALIFIED, AccountResult, rank_accounts

DEFAULT_CONFIG = "config/scoring.toml"
DEFAULT_ACCOUNTS = "data/accounts.json"


def _iso_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"invalid date {value!r}, expected YYYY-MM-DD") from exc


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--config", default=DEFAULT_CONFIG, help="Path to scoring TOML config")
    common.add_argument("--accounts", default=DEFAULT_ACCOUNTS, help="Path to accounts JSON")
    common.add_argument(
        "--as-of", type=_iso_date, help="Override the config as_of date (YYYY-MM-DD)"
    )

    parser = argparse.ArgumentParser(
        prog="signal-score",
        description="Gate, score and rank accounts from timestamped buying signals.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    rank = sub.add_parser("rank", parents=[common], help="Rank all accounts and export CSV")
    rank.add_argument("--output", "-o", help="Write results to this CSV path")
    rank.add_argument(
        "--qualified-only", action="store_true", help="Hide rejected accounts from the table"
    )

    explain = sub.add_parser("explain", parents=[common], help="Explain one account's result")
    explain.add_argument("account_id", help="Account ID, for example ACC-001")
    return parser


def _load(args: argparse.Namespace) -> tuple[ScoringConfig, list[AccountResult]]:
    config = load_config(args.config)
    if args.as_of:
        config = config.with_as_of(args.as_of)
    accounts = load_accounts(args.accounts, config.signal_types)
    return config, rank_accounts(accounts, config)


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return _run(args)
    except BrokenPipeError:
        # Output was piped into something that closed early (for example `| head`).
        # Point stdout at devnull so Python's exit-time flush doesn't raise again.
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        return 1


def _run(args: argparse.Namespace) -> int:
    try:
        config, results = _load(args)
    except (ConfigError, DataError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.command == "rank":
        # Write the CSV before printing so it exists even if stdout is closed early.
        path = write_csv(results, args.output) if args.output else None
        qualified = sum(1 for r in results if r.status == QUALIFIED)
        shown = [r for r in results if r.status == QUALIFIED] if args.qualified_only else results
        print(f"As of {config.as_of}: {qualified} qualified, {len(results) - qualified} rejected\n")
        print(format_table(shown))
        if path:
            print(f"\nWrote {len(results)} rows to {path}")
        return 0

    match = next((r for r in results if r.account.account_id == args.account_id), None)
    if match is None:
        print(f"error: account {args.account_id!r} not found", file=sys.stderr)
        return 1
    print(format_explanation(match, config.as_of.isoformat()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
