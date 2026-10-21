# Signal Scoring Engine

A small, deterministic Python engine that decides which B2B accounts are worth an outbound play right now, and explains why.

It takes a list of accounts with timestamped buying signals (funding rounds, SDR job posts, new sales leaders and so on), runs each account through ordered rejection gates, scores the survivors with time-decayed signal weights and combination bonuses, then ranks them and exports a CSV.

Every number is traceable. For any account you can ask the CLI which gate it failed, or exactly how its score was built.

> **Demo scope.** Version 1 runs entirely on synthetic data. All companies, domains (`.example`), tech stacks and signals are fictional. It makes no API calls, uses no LLMs and needs no API keys. It is a clean-room demonstration of signal scoring concepts, not a copy of any production system, and the default weights are illustrative, not calibrated against real outcomes.

## Quick start

Requires Python 3.11 or newer. There are no runtime dependencies.

```bash
git clone https://github.com/rudreshss09-svg/signal-scoring-engine.git
cd signal-scoring-engine
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

Run the demo:

```bash
# Rank all 13 synthetic accounts and export a CSV
signal-score rank --output output/ranked_accounts.csv

# Explain one account step by step
signal-score explain ACC-001

# See why a strong-looking account was rejected
signal-score explain ACC-009

# Replay the same data at a later date to watch decay and freshness change the ranking
signal-score rank --as-of 2026-10-20 --qualified-only

# Equivalent module form, no console script needed
python -m signal_scoring_engine rank
```

Run the checks:

```bash
pytest
ruff check .
ruff format --check .
```

## Sample output

`signal-score rank --output output/ranked_accounts.csv` with the shipped config (as-of date 2026-10-01):

```text
As of 2026-10-01: 6 qualified, 7 rejected

Rank  Account   Company                 Status      Score  Reason
-----------------------------------------------------------------
   1  ACC-001   Lumenfold               qualified   66.65  Passed all gates
   2  ACC-002   Quarrystack             qualified   36.02  Passed all gates
   3  ACC-003   Bramblepath Analytics   qualified   21.73  Passed all gates
   4  ACC-005   Cobaltline              qualified   20.43  Passed all gates
   5  ACC-004   Tidewell                qualified    8.96  Passed all gates
   6  ACC-012   Wexmoor                 qualified    7.46  Passed all gates
      ACC-006   Fernhollow              rejected           [icp_fit] Industry 'Consumer Apps' is outside the ICP
      ACC-007   Kestrel Ledger          rejected           [icp_fit] 1200 employees is outside the 20-250 ICP range
      ACC-008   Orrin Metrics           rejected           [tool_conflict] Already uses sales_engagement_platform, so an outbound motion likely exists
      ACC-009   Plinthware              rejected           [tool_conflict] Already uses outbound_agency, so an outbound motion likely exists
      ACC-010   Sablecrest              rejected           [signal_freshness] No buying signals observed on or before 2026-10-01
      ACC-011   Vantorra                rejected           [signal_freshness] All signals are stale: newest is 182 days old (limit 120)
      ACC-013   Glintmere               rejected           [icp_fit] Region 'Latin America' is outside the ICP

Wrote 13 rows to output/ranked_accounts.csv
```

`signal-score explain ACC-001`:

```text
Lumenfold (ACC-001, lumenfold.example)
As of 2026-10-01: QUALIFIED, rank 1, score 66.65

Gates (in order, stops at first failure):
  [PASS] icp_fit: B2B SaaS, 85 employees, North America
  [PASS] tool_conflict: No conflicting tools in tech stack
  [PASS] signal_freshness: 3 fresh signal(s) within 120 days

Signals:
  funding_round      2026-09-10   21d old  30 x 0.5^(21/90) = 25.52
  sdr_job_posting    2026-09-22    9d old  25 x 0.5^(9/30) = 20.31
  headcount_growth   2026-08-15   47d old  12 x 0.5^(47/45) = 5.82

Combination bonuses:
  funded_and_hiring_sdrs: +15.00 (funding_round + sdr_job_posting)

Score = 51.65 signal points + 15.00 bonus points = 66.65
```

`signal-score explain ACC-009` shows a high-intent account that is still rejected:

```text
Plinthware (ACC-009, plinthware.example)
As of 2026-10-01: REJECTED

Gates (in order, stops at first failure):
  [PASS] icp_fit: B2B SaaS, 75 employees, India
  [FAIL] tool_conflict: Already uses outbound_agency, so an outbound motion likely exists

Signals:
  funding_round      2026-09-20   11d old  fresh, not scored
  sdr_job_posting    2026-09-26    5d old  fresh, not scored

Not scored: rejected accounts are explained but never ranked.
```

CSV columns: `rank, account_id, company_name, status, score, signal_points, bonus_points, rejected_at_gate, reason, fresh_signals, bonuses`. One row per account, qualified accounts first in rank order, then rejected accounts by ID.

## How it works

```text
config/scoring.toml ──► load_config ──┐
                                      ├──► for each account:
data/accounts.json ───► load_accounts ┘      1. gates (stop at first failure)
                                             │    icp_fit → tool_conflict → signal_freshness
                                             │
                                             ├─ rejected ─► reason recorded, not scored
                                             │
                                             └─ passed ──► 2. decay each fresh signal
                                                           3. add combination bonuses
                                                           4. score
                                      rank (score desc, account_id asc)
                                             │
                                ┌────────────┴────────────┐
                          terminal table / explain     CSV export
```

### Signal decay

Each signal type has a base weight and a half-life. A signal's value on the as-of date is:

```text
points = weight × 0.5 ^ (age_days / half_life_days)
```

So a signal is worth its full weight on day 0, half after one half-life, and a quarter after two. Different signal types fade at different speeds: an SDR job post (30-day half-life) goes cold faster than a funding round (90-day half-life).

Each signal's points are rounded to 2 decimals once, and every total is the sum of those rounded values, so the numbers in `explain` and the CSV always add up exactly.

Age is always measured against a fixed **as-of date** from the config, never the system clock. The same inputs give the same output on any machine on any day. `--as-of` lets you replay the data at a different date.

### Rejection gates

Gates run in a fixed order and stop at the first failure, so each rejected account has exactly one reason:

| Order | Gate | Rejects when |
|---|---|---|
| 1 | `icp_fit` | Industry, employee count or region is outside the configured ICP |
| 2 | `tool_conflict` | Tech stack includes a configured conflicting tool category (the account likely already runs outbound) |
| 3 | `signal_freshness` | No signal is dated on or before the as-of date (the account has none, or only future-dated ones), or every such signal is older than `max_signal_age_days` |

Cheap structural checks come first, signal checks last. In a live pipeline this ordering is what keeps you from spending enrichment effort on accounts you would reject anyway.

### Signal statuses

| Status | Meaning | Points |
|---|---|---|
| fresh | 0 to `max_signal_age_days` days old | decayed weight |
| stale | Older than `max_signal_age_days` | 0 |
| future | Dated after the as-of date (not yet observed at that point in time) | 0, and does not count toward the freshness gate or combination bonuses |

### Combination bonuses

Some signals mean more together. A combination grants a flat bonus once, when **all** of its signal types are present among the account's fresh signals. For example, `funding_round` + `sdr_job_posting` suggests freshly funded and actively building an outbound team.

## Configuration

All tunable behaviour lives in [`config/scoring.toml`](config/scoring.toml). The code has no hardcoded weights, thresholds or ICP rules.

```toml
as_of = 2026-10-01

[freshness]
max_signal_age_days = 120

[signals.sdr_job_posting]
weight = 25.0
half_life_days = 30

[[combinations]]
name = "funded_and_hiring_sdrs"
signals = ["funding_round", "sdr_job_posting"]
bonus = 15.0

[icp]
industries = ["B2B SaaS"]
min_employees = 20
max_employees = 250
regions = ["North America", "Europe", "India"]

[tool_conflict]
conflicting_tools = ["sales_engagement_platform", "outbound_agency"]
```

Point the CLI at your own files with `--config path/to/config.toml --accounts path/to/accounts.json`. The config is validated on load, and so is the account data (unknown signal types, bad dates, duplicate IDs and missing fields all fail fast with a clear error and exit code 2).

## Project layout

```text
signal-scoring-engine/
├── config/scoring.toml             # weights, half-lives, gates, bonuses, as-of date
├── data/accounts.json              # 13 fictional accounts with synthetic signals
├── src/signal_scoring_engine/
│   ├── models.py                   # Account and Signal dataclasses
│   ├── config.py                   # TOML loading and validation
│   ├── data.py                     # JSON loading and validation
│   ├── decay.py                    # half-life decay maths
│   ├── gates.py                    # ordered rejection gates, signal freshness
│   ├── scoring.py                  # scoring, bonuses, deterministic ranking
│   ├── export.py                   # CSV export, table and explanation output
│   └── cli.py                      # argparse CLI (rank, explain)
├── tests/                          # pytest suite
├── .github/workflows/ci.yml        # ruff + pytest on Python 3.11, 3.12, 3.13
└── pyproject.toml
```

## Design decisions

- **Rejection before scoring.** An account must pass every gate before it gets a score. Rejected accounts keep their explanation but are never ranked, so a high-intent account with a disqualifying trait (ACC-009) can't outrank a good fit.
- **One reason per rejection.** Gates short-circuit, so the reason a rep reads is always the first and most fundamental problem.
- **Fixed as-of date.** Decay is relative to a configured date, not `today()`. That makes results reproducible, testable and replayable.
- **Explainability as a first-class output.** Every point in a score traces back to a specific signal, its age and half-life, or a named bonus. `explain` prints the exact formula (`30 x 0.5^(21/90)`) instead of a rounded decay factor, and the displayed parts always add up exactly to the displayed totals. Tests enforce this.
- **Deterministic ordering.** Ties on score are broken by `account_id`, and signal breakdowns have a fixed sort order. Input order does not affect output, and a test enforces this.
- **Config separate from code.** Weights, half-lives, ICP rules and conflicting tools are all data, so tuning the model doesn't need a code change.
- **Standard library only at runtime.** `tomllib`, `json`, `csv`, `argparse` and `dataclasses` are all you need to run it.
- **Tech stack as categories.** The demo uses generic tool categories (`sales_engagement_platform`, `crm`) instead of vendor names, which keeps the data fictional and the rule portable.

## Limitations

- **Synthetic data only.** The 13 accounts and their signals are invented to exercise every code path. No conclusions about real companies or markets should be drawn from them.
- **Uncalibrated weights.** The default weights, half-lives and bonuses are reasonable starting points, not values fitted to conversion data. This version has no way to learn or validate them against outcomes.
- **No live signal collection or enrichment.** Signals are read from a JSON file. Detecting job posts, funding news or stack changes from real sources is out of scope for v1.
- **Simple ICP model.** ICP fit is a set of hard pass or fail rules. There is no partial fit or weighted firmographic scoring.
- **Exact-match rules.** Industry, region and tool matching are exact string comparisons, with no normalization or fuzzy matching.
- **One signal, one value.** Repeated signals of the same type each add points independently. There is no saturation or de-duplication of near-identical events.
- **Batch CLI only.** No API, database, scheduler or CRM sync.

## License

[MIT](LICENSE) © 2026 Rudresh Shendge
