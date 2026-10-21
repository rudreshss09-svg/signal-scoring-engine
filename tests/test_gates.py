from conftest import make_account
from signal_scoring_engine.gates import run_gates


def failed_gate(account, config):
    last = run_gates(account, config)[-1]
    return None if last.passed else last.gate


def test_good_account_passes_all_gates(config):
    results = run_gates(make_account(), config)
    assert [r.gate for r in results] == ["icp_fit", "tool_conflict", "signal_freshness"]
    assert all(r.passed for r in results)


def test_wrong_industry_fails_icp(config):
    assert failed_gate(make_account(industry="Consumer Apps"), config) == "icp_fit"


def test_employee_count_outside_range_fails_icp(config):
    assert failed_gate(make_account(employee_count=5), config) == "icp_fit"
    assert failed_gate(make_account(employee_count=500), config) == "icp_fit"


def test_employee_range_bounds_are_inclusive(config):
    assert failed_gate(make_account(employee_count=20), config) is None
    assert failed_gate(make_account(employee_count=200), config) is None


def test_wrong_region_fails_icp(config):
    assert failed_gate(make_account(region="North America"), config) == "icp_fit"


def test_conflicting_tool_fails_tool_gate(config):
    account = make_account(tech_stack=("crm", "sales_engagement_platform"))
    assert failed_gate(account, config) == "tool_conflict"


def test_missing_signals_fail_freshness(config):
    results = run_gates(make_account(signals=()), config)
    assert results[-1].gate == "signal_freshness"
    assert "No buying signals" in results[-1].reason


def test_only_stale_signals_fail_freshness(config):
    # 2026-06-01 is 122 days before the as-of date, past the 100 day limit.
    results = run_gates(make_account(signals=(("funding_round", "2026-06-01"),)), config)
    assert results[-1].gate == "signal_freshness"
    assert "stale" in results[-1].reason


def test_signal_exactly_at_age_limit_is_fresh(config):
    # 2026-06-23 is exactly 100 days before 2026-10-01.
    account = make_account(signals=(("funding_round", "2026-06-23"),))
    assert failed_gate(account, config) is None


def test_future_signals_count_as_missing(config):
    results = run_gates(make_account(signals=(("funding_round", "2026-10-05"),)), config)
    assert results[-1].gate == "signal_freshness"
    assert "No buying signals" in results[-1].reason


def test_gates_stop_at_first_failure(config):
    # Fails ICP, has a tool conflict and no signals. Only the first failure is reported.
    account = make_account(
        industry="Consumer Apps", tech_stack=("sales_engagement_platform",), signals=()
    )
    results = run_gates(account, config)
    assert len(results) == 1
    assert results[0].gate == "icp_fit"
