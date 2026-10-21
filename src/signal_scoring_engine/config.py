"""Load and validate scoring configuration from a TOML file."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, replace
from datetime import date
from pathlib import Path
from typing import Any


class ConfigError(ValueError):
    """Raised when the scoring configuration is missing or invalid."""


@dataclass(frozen=True)
class SignalType:
    name: str
    weight: float
    half_life_days: float
    description: str = ""


@dataclass(frozen=True)
class Combination:
    name: str
    signals: tuple[str, ...]
    bonus: float


@dataclass(frozen=True)
class IcpRules:
    industries: tuple[str, ...]
    min_employees: int
    max_employees: int
    regions: tuple[str, ...]


@dataclass(frozen=True)
class ScoringConfig:
    as_of: date
    max_signal_age_days: int
    signal_types: dict[str, SignalType]
    combinations: tuple[Combination, ...]
    icp: IcpRules
    conflicting_tools: tuple[str, ...]

    def with_as_of(self, as_of: date) -> ScoringConfig:
        """Return a copy of this config evaluated at a different date."""
        return replace(self, as_of=as_of)


def load_config(path: str | Path) -> ScoringConfig:
    """Read a TOML config file and return a validated ScoringConfig."""
    path = Path(path)
    try:
        with path.open("rb") as fh:
            raw = tomllib.load(fh)
    except FileNotFoundError as exc:
        raise ConfigError(f"Config file not found: {path}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"Invalid TOML in {path}: {exc}") from exc
    return parse_config(raw)


def parse_config(raw: dict[str, Any]) -> ScoringConfig:
    """Build a ScoringConfig from an already-parsed mapping."""
    as_of = raw.get("as_of")
    if not isinstance(as_of, date):
        raise ConfigError("'as_of' must be a date such as 2026-10-01")

    max_age = _section(raw, "freshness").get("max_signal_age_days")
    if not _is_int(max_age) or max_age <= 0:
        raise ConfigError("'freshness.max_signal_age_days' must be a positive integer")

    signal_types = _parse_signal_types(_section(raw, "signals"))
    combinations = _parse_combinations(raw.get("combinations", []), signal_types)

    icp_raw = _section(raw, "icp")
    icp = IcpRules(
        industries=_str_tuple(icp_raw, "industries", "icp"),
        min_employees=_non_negative_int(icp_raw, "min_employees", "icp"),
        max_employees=_non_negative_int(icp_raw, "max_employees", "icp"),
        regions=_str_tuple(icp_raw, "regions", "icp"),
    )
    if icp.min_employees > icp.max_employees:
        raise ConfigError("'icp.min_employees' cannot exceed 'icp.max_employees'")

    conflicting_tools = _str_tuple(
        _section(raw, "tool_conflict"), "conflicting_tools", "tool_conflict"
    )

    return ScoringConfig(
        as_of=as_of,
        max_signal_age_days=max_age,
        signal_types=signal_types,
        combinations=combinations,
        icp=icp,
        conflicting_tools=conflicting_tools,
    )


def _section(raw: dict[str, Any], name: str) -> dict[str, Any]:
    value = raw.get(name)
    if not isinstance(value, dict):
        raise ConfigError(f"Missing or invalid [{name}] section")
    return value


def _parse_signal_types(raw: dict[str, Any]) -> dict[str, SignalType]:
    if not raw:
        raise ConfigError("At least one signal type must be defined under [signals]")
    result: dict[str, SignalType] = {}
    for name, spec in raw.items():
        if not isinstance(spec, dict):
            raise ConfigError(f"[signals.{name}] must be a table")
        weight = spec.get("weight")
        half_life = spec.get("half_life_days")
        if not _is_number(weight) or weight < 0:
            raise ConfigError(f"'signals.{name}.weight' must be a non-negative number")
        if not _is_number(half_life) or half_life <= 0:
            raise ConfigError(f"'signals.{name}.half_life_days' must be a positive number")
        result[name] = SignalType(
            name=name,
            weight=float(weight),
            half_life_days=float(half_life),
            description=str(spec.get("description", "")),
        )
    return result


def _parse_combinations(
    raw: list[Any], signal_types: dict[str, SignalType]
) -> tuple[Combination, ...]:
    if not isinstance(raw, list):
        raise ConfigError("'combinations' must be an array of tables")
    combos = []
    for spec in raw:
        if not isinstance(spec, dict):
            raise ConfigError("Each [[combinations]] entry must be a table")
        name = spec.get("name")
        signals = spec.get("signals")
        bonus = spec.get("bonus")
        if not isinstance(name, str) or not name:
            raise ConfigError("Each combination needs a non-empty 'name'")
        if not isinstance(signals, list) or len(signals) < 2:
            raise ConfigError(f"Combination '{name}' needs at least two signal types")
        unknown = [s for s in signals if s not in signal_types]
        if unknown:
            raise ConfigError(f"Combination '{name}' references unknown signal types: {unknown}")
        if not _is_number(bonus) or bonus < 0:
            raise ConfigError(f"Combination '{name}' bonus must be a non-negative number")
        combos.append(Combination(name=name, signals=tuple(signals), bonus=float(bonus)))
    return tuple(combos)


def _str_tuple(raw: dict[str, Any], key: str, section: str) -> tuple[str, ...]:
    value = raw.get(key)
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise ConfigError(f"'{section}.{key}' must be a list of strings")
    return tuple(value)


def _non_negative_int(raw: dict[str, Any], key: str, section: str) -> int:
    value = raw.get(key)
    if not _is_int(value) or value < 0:
        raise ConfigError(f"'{section}.{key}' must be a non-negative integer")
    return value


# bool is a subclass of int in Python, so `true` in TOML would otherwise pass as 1.
def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_number(value: Any) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)
