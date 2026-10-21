from datetime import date

import pytest

from conftest import make_account
from signal_scoring_engine.gates import SignalStatus
from signal_scoring_engine.scoring import QUALIFIED, REJECTED, rank_accounts, score_account


def test_single_signal_score_uses_decay(config):
    # funding_round: weight 40, half-life 50, observed 10 days before as-of.
    result = score_account(make_account(signals=(("funding_round", "2026-09-21"),)), config)
    assert result.status == QUALIFIED
    assert result.score == pytest.approx(round(40 * 0.5 ** (10 / 50), 2))


def test_combination_bonus_applies_when_all_signals_fresh(config):
    account = make_account(
        signals=(("funding_round", "2026-09-21"), ("sdr_job_posting", "2026-09-21"))
    )
    result = score_account(account, config)
    assert [b.name for b in result.bonuses] == ["funded_and_hiring"]
    assert result.bonus_points == 15.0
    assert result.score == pytest.approx(result.signal_points + 15.0)


def test_no_bonus_when_combination_incomplete(config):
    account = make_account(
        signals=(("funding_round", "2026-09-21"), ("headcount_growth", "2026-09-21"))
    )
    result = score_account(account, config)
    assert result.bonuses == ()
    assert result.bonus_points == 0.0


def test_no_bonus_when_combination_member_is_stale(config):
    # sdr_job_posting is 122 days old, beyond the 100 day limit.
    account = make_account(
        signals=(("funding_round", "2026-09-21"), ("sdr_job_posting", "2026-06-01"))
    )
    result = score_account(account, config)
    assert result.bonuses == ()
    stale = [s for s in result.signals if s.status == SignalStatus.STALE]
    assert len(stale) == 1
    assert stale[0].points == 0.0


def test_future_signals_add_no_points(config):
    account = make_account(
        signals=(("funding_round", "2026-09-21"), ("sdr_job_posting", "2026-10-10"))
    )
    result = score_account(account, config)
    assert result.bonuses == ()
    future = [s for s in result.signals if s.status == SignalStatus.FUTURE]
    assert len(future) == 1
    assert future[0].points == 0.0


def test_rejected_accounts_are_not_scored(config):
    result = score_account(make_account(region="Asia"), config)
    assert result.status == REJECTED
    assert result.score is None
    assert result.rejected_at == "icp_fit"


def test_ranking_orders_by_score_then_account_id(config):
    strong = make_account(
        "T-3", signals=(("funding_round", "2026-09-30"), ("sdr_job_posting", "2026-09-30"))
    )
    tie_b = make_account("T-2", signals=(("headcount_growth", "2026-09-30"),))
    tie_a = make_account("T-1", signals=(("headcount_growth", "2026-09-30"),))
    rejected = make_account("T-0", tech_stack=("sales_engagement_platform",))

    results = rank_accounts([tie_b, rejected, tie_a, strong], config)

    assert [r.account.account_id for r in results] == ["T-3", "T-1", "T-2", "T-0"]
    assert [r.rank for r in results] == [1, 2, 3, None]


def test_earlier_as_of_date_changes_scores(config):
    account = make_account(signals=(("funding_round", "2026-09-01"),))
    # Scoring closer to the signal date leaves more of its weight intact.
    at_config_date = score_account(account, config).score
    two_weeks_earlier = score_account(account, config.with_as_of(date(2026, 9, 17))).score
    assert at_config_date is not None and two_weeks_earlier is not None
    assert two_weeks_earlier > at_config_date


def test_signal_points_are_sum_of_rounded_contributions(config):
    # 40 x 0.5^(1/50) = 39.4493... and 20 x 0.5^(3/10) = 16.2450...
    # Rounding the raw sum (55.694...) gives 55.69, but the displayed parts are
    # 39.45 + 16.25 = 55.70. Totals must be built from the displayed parts.
    account = make_account(
        signals=(("funding_round", "2026-09-30"), ("sdr_job_posting", "2026-09-28"))
    )
    result = score_account(account, config)
    assert [c.points for c in result.signals] == [39.45, 16.25]
    assert result.signal_points == 55.70
    assert result.score == 70.70


def test_fractional_bonus_is_rounded_consistently(config):
    from dataclasses import replace as dc_replace

    from signal_scoring_engine.config import Combination

    odd = dc_replace(
        config,
        combinations=(Combination("odd", ("funding_round", "sdr_job_posting"), 1.005),),
    )
    account = make_account(
        signals=(("funding_round", "2026-09-21"), ("sdr_job_posting", "2026-09-21"))
    )
    result = score_account(account, odd)
    assert result.bonus_points == result.bonuses[0].bonus
    assert result.score == round(result.signal_points + result.bonus_points, 2)
