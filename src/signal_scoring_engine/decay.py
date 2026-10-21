"""Exponential half-life decay for signal values."""

from __future__ import annotations

from datetime import date


def age_in_days(observed_at: date, as_of: date) -> int:
    """Whole days between when a signal was observed and the scoring date."""
    return (as_of - observed_at).days


def decay_factor(age_days: float, half_life_days: float) -> float:
    """Fraction of a signal's weight that remains after ``age_days``.

    A signal keeps 100% of its weight on day 0 and 50% after one half-life.
    """
    if half_life_days <= 0:
        raise ValueError("half_life_days must be positive")
    if age_days < 0:
        raise ValueError("age_days cannot be negative (signal is after the as-of date)")
    return 0.5 ** (age_days / half_life_days)


def decayed_value(weight: float, age_days: float, half_life_days: float) -> float:
    return weight * decay_factor(age_days, half_life_days)
