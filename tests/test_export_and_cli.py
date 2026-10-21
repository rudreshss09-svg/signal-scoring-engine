import csv
import io
import re
import tomllib
from datetime import date
from decimal import Decimal

import pytest

from conftest import ACCOUNTS_PATH, CONFIG_PATH
from signal_scoring_engine.cli import main
from signal_scoring_engine.config import ConfigError, load_config, parse_config
from signal_scoring_engine.data import DataError, load_accounts, parse_accounts
from signal_scoring_engine.export import CSV_COLUMNS, results_to_csv, write_csv
from signal_scoring_engine.scoring import rank_accounts


def demo_results(as_of=None):
    config = load_config(CONFIG_PATH)
    if as_of:
        config = config.with_as_of(date.fromisoformat(as_of))
    return rank_accounts(load_accounts(ACCOUNTS_PATH, config.signal_types), config)


def test_csv_has_expected_header_and_one_row_per_account(tmp_path):
    results = demo_results()
    path = write_csv(results, tmp_path / "out" / "ranked.csv")
    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    assert tuple(rows[0].keys()) == CSV_COLUMNS
    assert len(rows) == len(results) == 13


def test_csv_rows_explain_qualified_and_rejected():
    rows = list(csv.DictReader(io.StringIO(results_to_csv(demo_results()))))
    qualified = [r for r in rows if r["status"] == "qualified"]
    rejected = [r for r in rows if r["status"] == "rejected"]
    assert qualified and rejected
    assert [int(r["rank"]) for r in qualified] == list(range(1, len(qualified) + 1))
    scores = [float(r["score"]) for r in qualified]
    assert scores == sorted(scores, reverse=True)
    for r in rejected:
        assert r["rank"] == "" and r["score"] == ""
        assert r["rejected_at_gate"] in {"icp_fit", "tool_conflict", "signal_freshness"}
        assert r["reason"]


def test_demo_data_exercises_every_gate():
    gates = {r.rejected_at for r in demo_results() if r.rejected_at}
    assert gates == {"icp_fit", "tool_conflict", "signal_freshness"}


def test_demo_data_exercises_every_rejection_rule():
    reasons = [r.reason for r in demo_results() if r.rejected_at]
    for fragment in (
        "Industry",
        "employees is outside",
        "Region",
        "Already uses",
        "No buying signals",
        "All signals are stale",
    ):
        assert any(fragment in reason for reason in reasons), fragment


AS_OF_DATES = [None, "2026-09-15", "2026-10-01", "2026-10-20", "2026-12-31"]


@pytest.mark.parametrize("as_of", AS_OF_DATES)
def test_explanations_reconcile_exactly(as_of, capsys):
    """Displayed per-signal points must add up to the displayed totals, to the cent."""
    args = ["--config", str(CONFIG_PATH), "--accounts", str(ACCOUNTS_PATH)]
    if as_of:
        args += ["--as-of", as_of]
    for result in demo_results(as_of):
        if result.score is None:
            continue
        assert main(["explain", result.account.account_id, *args]) == 0
        text = capsys.readouterr().out
        parts = [Decimal(x) for x in re.findall(r"\) = (\d+\.\d\d)$", text, re.MULTILINE)]
        bonuses = [Decimal(x) for x in re.findall(r": \+(\d+\.\d\d) \(", text)]
        total = re.search(r"Score = (\S+) signal points \+ (\S+) bonus points = (\S+)$", text, re.M)
        signal_total, bonus_total, score = (Decimal(x) for x in total.groups())
        assert sum(parts, Decimal(0)) == signal_total
        assert sum(bonuses, Decimal(0)) == bonus_total
        assert signal_total + bonus_total == score


@pytest.mark.parametrize("as_of", AS_OF_DATES)
def test_csv_rows_reconcile_exactly(as_of):
    for row in csv.DictReader(io.StringIO(results_to_csv(demo_results(as_of)))):
        if row["status"] != "qualified":
            continue
        parts = [Decimal(p.split("=")[1]) for p in row["fresh_signals"].split("; ")]
        bonuses = [Decimal(b.split("=+")[1]) for b in row["bonuses"].split("; ") if b]
        assert sum(parts, Decimal(0)) == Decimal(row["signal_points"])
        assert sum(bonuses, Decimal(0)) == Decimal(row["bonus_points"])
        assert Decimal(row["signal_points"]) + Decimal(row["bonus_points"]) == Decimal(row["score"])


def test_runs_are_reproducible():
    assert results_to_csv(demo_results()) == results_to_csv(demo_results())


def test_input_order_does_not_change_output():
    config = load_config(CONFIG_PATH)
    accounts = load_accounts(ACCOUNTS_PATH, config.signal_types)
    forward = results_to_csv(rank_accounts(accounts, config))
    backward = results_to_csv(rank_accounts(list(reversed(accounts)), config))
    assert forward == backward


def test_cli_rank_writes_csv(tmp_path, capsys):
    out = tmp_path / "ranked.csv"
    code = main(
        ["rank", "--config", str(CONFIG_PATH), "--accounts", str(ACCOUNTS_PATH), "-o", str(out)]
    )
    assert code == 0
    assert out.read_text(encoding="utf-8") == results_to_csv(demo_results())
    assert "qualified" in capsys.readouterr().out


def test_cli_explain_and_unknown_account(capsys):
    args = ["--config", str(CONFIG_PATH), "--accounts", str(ACCOUNTS_PATH)]
    assert main(["explain", "ACC-001", *args]) == 0
    assert "Score =" in capsys.readouterr().out
    assert main(["explain", "ACC-999", *args]) == 1


def test_cli_reports_missing_config(tmp_path, capsys):
    assert main(["rank", "--config", str(tmp_path / "missing.toml")]) == 2
    assert "not found" in capsys.readouterr().err


def test_invalid_config_is_rejected():
    with pytest.raises(ConfigError):
        parse_config({"as_of": "not a date"})


def test_unknown_signal_type_is_rejected():
    record = {
        "account_id": "X",
        "company_name": "X",
        "domain": "x.example",
        "industry": "B2B SaaS",
        "employee_count": 10,
        "region": "Europe",
        "signals": [{"type": "mystery", "observed_at": "2026-09-01"}],
    }
    with pytest.raises(DataError):
        parse_accounts([record], ["funding_round"])


def valid_record(**overrides):
    record = {
        "account_id": "X",
        "company_name": "X",
        "domain": "x.example",
        "industry": "B2B SaaS",
        "employee_count": 10,
        "region": "Europe",
        "tech_stack": ["crm"],
        "signals": [],
    }
    return record | overrides


@pytest.mark.parametrize(
    "overrides",
    [
        # A string here used to be split into characters, hiding tool conflicts.
        {"tech_stack": "sales_engagement_platform"},
        {"signals": "funding_round"},
        {"employee_count": True},
    ],
)
def test_malformed_account_fields_are_rejected(overrides):
    with pytest.raises(DataError):
        parse_accounts([valid_record(**overrides)], ["funding_round"])


@pytest.mark.parametrize(
    "mutate",
    [
        lambda raw: raw.__setitem__("combinations", [1]),
        lambda raw: raw["signals"]["funding_round"].__setitem__("weight", True),
        lambda raw: raw["freshness"].__setitem__("max_signal_age_days", True),
        lambda raw: raw["combinations"][0].__setitem__("bonus", True),
    ],
)
def test_malformed_config_values_are_rejected(mutate):
    raw = tomllib.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    mutate(raw)
    with pytest.raises(ConfigError):
        parse_config(raw)
