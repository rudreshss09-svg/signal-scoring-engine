"""Load account and signal data from JSON."""

from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import date
from pathlib import Path
from typing import Any

from .models import Account, Signal


class DataError(ValueError):
    """Raised when account data is missing or invalid."""


REQUIRED_FIELDS = ("account_id", "company_name", "domain", "industry", "employee_count", "region")


def load_accounts(path: str | Path, known_signal_types: Iterable[str]) -> list[Account]:
    """Read accounts from a JSON file and validate them against known signal types."""
    path = Path(path)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise DataError(f"Accounts file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise DataError(f"Invalid JSON in {path}: {exc}") from exc

    records = raw.get("accounts") if isinstance(raw, dict) else None
    if not isinstance(records, list):
        raise DataError("Accounts file must contain an 'accounts' list")
    return parse_accounts(records, known_signal_types)


def parse_accounts(records: list[Any], known_signal_types: Iterable[str]) -> list[Account]:
    known = set(known_signal_types)
    accounts: list[Account] = []
    seen_ids: set[str] = set()
    for record in records:
        account = _parse_account(record, known)
        if account.account_id in seen_ids:
            raise DataError(f"Duplicate account_id: {account.account_id}")
        seen_ids.add(account.account_id)
        accounts.append(account)
    return accounts


def _parse_account(record: Any, known: set[str]) -> Account:
    if not isinstance(record, dict):
        raise DataError("Each account must be a JSON object")
    missing = [f for f in REQUIRED_FIELDS if f not in record]
    if missing:
        raise DataError(f"Account {record.get('account_id', '?')} is missing fields: {missing}")

    account_id = str(record["account_id"])
    employee_count = record["employee_count"]
    # bool is a subclass of int, so reject it explicitly.
    valid_count = isinstance(employee_count, int) and not isinstance(employee_count, bool)
    if not valid_count or employee_count < 0:
        raise DataError(f"Account {account_id}: employee_count must be a non-negative integer")

    # A bare string would otherwise be iterated character by character, silently
    # hiding tool conflicts from the tool_conflict gate.
    tech_stack = record.get("tech_stack", [])
    if not isinstance(tech_stack, list) or not all(isinstance(t, str) for t in tech_stack):
        raise DataError(f"Account {account_id}: tech_stack must be a list of strings")
    raw_signals = record.get("signals", [])
    if not isinstance(raw_signals, list):
        raise DataError(f"Account {account_id}: signals must be a list")

    signals = tuple(_parse_signal(s, account_id, known) for s in raw_signals)
    return Account(
        account_id=account_id,
        company_name=str(record["company_name"]),
        domain=str(record["domain"]),
        industry=str(record["industry"]),
        employee_count=employee_count,
        region=str(record["region"]),
        tech_stack=tuple(tech_stack),
        signals=signals,
    )


def _parse_signal(raw: Any, account_id: str, known: set[str]) -> Signal:
    if not isinstance(raw, dict):
        raise DataError(f"Account {account_id}: each signal must be a JSON object")
    signal_type = raw.get("type")
    if signal_type not in known:
        raise DataError(f"Account {account_id}: unknown signal type {signal_type!r}")
    try:
        observed_at = date.fromisoformat(str(raw.get("observed_at")))
    except ValueError as exc:
        raise DataError(
            f"Account {account_id}: observed_at must be an ISO date (YYYY-MM-DD)"
        ) from exc
    return Signal(type=signal_type, observed_at=observed_at, detail=str(raw.get("detail", "")))
