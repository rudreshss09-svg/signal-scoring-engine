from datetime import date

import pytest

from signal_scoring_engine.decay import age_in_days, decay_factor, decayed_value


def test_full_weight_on_day_zero():
    assert decay_factor(0, 30) == 1.0


def test_half_weight_after_one_half_life():
    assert decay_factor(30, 30) == pytest.approx(0.5)


def test_quarter_weight_after_two_half_lives():
    assert decayed_value(40.0, 60, 30) == pytest.approx(10.0)


def test_shorter_half_life_decays_faster():
    assert decay_factor(20, 10) < decay_factor(20, 90)


def test_age_is_measured_against_as_of_date():
    assert age_in_days(date(2026, 9, 1), date(2026, 10, 1)) == 30


def test_negative_age_is_rejected():
    with pytest.raises(ValueError):
        decay_factor(-1, 30)


def test_non_positive_half_life_is_rejected():
    with pytest.raises(ValueError):
        decay_factor(5, 0)
