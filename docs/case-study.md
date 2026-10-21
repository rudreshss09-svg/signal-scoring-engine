# Case Study: Explainable GTM Account Prioritisation

**Project:** Signal Scoring Engine  
**Role:** Independent GTM systems project  
**Stack:** Python 3.11+, TOML, JSON, CLI, CSV, pytest, Ruff, GitHub Actions  
**Status:** Public v1 demonstration using synthetic data

## Executive summary

Outbound teams can waste time researching accounts that are a poor fit, already have an outbound motion, or no longer show a timely buying signal. This project demonstrates a small, explainable decision engine that screens accounts before scoring them, reduces the value of older signals over time, and makes each result auditable.

The engine reads account records and scoring rules from separate files. It applies ordered rejection gates, scores only accounts that pass, ranks qualified accounts deterministically, and exports both a terminal report and CSV. A dedicated `explain` command shows the gates, signal contributions, and any combination bonuses behind an account's result.

> **Scope and evidence:** This public repository is a clean-room demonstration with 13 fictional accounts and `.example` domains. It makes no API calls, uses no LLMs, and does not connect to a CRM or collect live buying signals. The default weights and bonuses are illustrative, not calibrated against real conversion outcomes. It should not be interpreted as a copy of a production system.

## The problem

A signal-led outbound workflow needs to answer two different questions:

1. **Should this account be considered at all?** Does it fit the ICP, appear to already have an outbound motion, and have at least one sufficiently recent signal?
2. **Among eligible accounts, what should be prioritised now?** Which observed signals remain meaningful after accounting for their age, and what combinations may justify additional priority?

Combining those questions into one opaque score can create undesirable outcomes: an account with a strong-looking signal might rank highly despite being outside the ICP, or old intent could be treated like current intent. A score without an explanation is also difficult for a sales rep to trust or challenge.

## Design

The engine separates hard eligibility checks from prioritisation.

1. **Load and validate inputs.** Account data is read from JSON and rules from TOML. Invalid dates, duplicate IDs, missing fields, and unknown signal types fail fast.
2. **Apply ordered rejection gates.** The first failed gate stops evaluation and supplies the rejection reason.
3. **Classify signals against a fixed as-of date.** Signals are fresh, stale, or future-dated. Only fresh signals contribute points.
4. **Calculate decayed signal points.** Each signal type has a configurable base weight and half-life.
5. **Apply combination bonuses.** A configured bonus is added once when all required signal types appear among the account's fresh signals.
6. **Rank and explain.** Qualified accounts sort by descending score, with account ID as a deterministic tie-breaker. Rejected accounts remain visible with their reason but receive no rank.
7. **Export.** The CLI produces a readable table, an account-level explanation, and CSV output for downstream review.

See [the architecture diagram](architecture.md) for the flow and module boundaries.

## Rejection before scoring

The gates run in this fixed order:

| Order | Gate | Rule |
|---|---|---|
| 1 | `icp_fit` | Reject if industry, employee count, or region falls outside the configured ICP. |
| 2 | `tool_conflict` | Reject if the account has a configured conflicting tool category, used here as a proxy for an existing outbound motion. |
| 3 | `signal_freshness` | Reject if there is no signal dated on or before the as-of date, or if every observed signal is older than the freshness limit. |

The order is intentional: inexpensive structural checks precede signal freshness. In a production pipeline with paid enrichment steps, the same principle can help avoid spending enrichment effort on accounts that would be rejected anyway. **This demo does not perform enrichment or measure credits saved**; that is the operational principle the design illustrates.

Each rejected account has one primary reason because evaluation stops at the first failed gate. For example, synthetic account `ACC-009` has fresh funding and SDR hiring signals, but is rejected at `tool_conflict` because its fictional tech stack contains the configured `outbound_agency` category. It is explained, not scored or ranked.

## Time-decayed signals

The score for an individual fresh signal is calculated as:

```text
points = weight × 0.5 ^ (age_days / half_life_days)
```

- `weight` is the configured value for a signal at age zero.
- `age_days` is measured against the fixed as-of date.
- `half_life_days` controls how quickly the signal loses value.

A signal retains half its starting value after one half-life and a quarter after two. The configuration uses different half-lives for different signal types, for example 30 days for an SDR job posting and 90 days for a funding round. These values are illustrative defaults, not validated claims about real buying behaviour.

The fixed as-of date avoids dependence on the machine clock. Using `--as-of` makes it possible to replay the same inputs at another date and inspect how freshness, scores, and ranking change.

Future-dated signals are treated as not yet observed at the selected as-of date. They do not pass the freshness gate, earn points, or trigger combination bonuses. Stale signals contribute zero and cannot make an account pass freshness on their own.

## Combination bonuses and deterministic output

The configuration contains two example combinations:

- `funding_round` + `sdr_job_posting`
- `new_sales_leader` + `sdr_job_posting`

A configured bonus is awarded once when all required signal types are present among the account's fresh signals. These are demonstration rules, not evidence that those combinations predict conversion in a real dataset.

To keep the output auditable, each fresh signal contribution is rounded to two decimal places once; totals are calculated from those displayed contributions. The explanation shows the exact decay expression rather than a rounded intermediate factor. Scores sort descending, ties break by account ID, and signal breakdowns use a stable order. The test suite checks arithmetic reconciliation and reproducibility.

## Example result

With the shipped configuration and as-of date of 2026-10-01, the synthetic dataset contains **6 qualified and 7 rejected accounts**. `ACC-001` ranks first at 66.65 points: 51.65 signal points plus a 15.00-point combination bonus. The CLI can explain the contribution from each signal and the rule behind the bonus.

These numbers describe only the invented sample dataset. They are not a performance benchmark, conversion uplift, or business result.

## Validation and engineering practices

The repository includes:

- Input validation for configuration and account records.
- Unit and CLI/export tests, including score-component reconciliation and gate coverage.
- Ruff lint and formatting checks.
- GitHub Actions CI on Python 3.11, 3.12, and 3.13.
- A CLI smoke test in CI, and README sample output generated from the actual CLI.
- No runtime dependencies beyond the Python standard library.

At the published v1 commit, the local verification reported 56 passing tests on each of Python 3.11, 3.12, and 3.13. The first GitHub Actions workflow also passed its three-version matrix. See [the CI run](https://github.com/rudreshss09-svg/signal-scoring-engine/actions/runs/39649854334).

## Trade-offs and limitations

This is intentionally a small batch CLI, not a production GTM platform.

- **Synthetic data only:** the sample is fictional and cannot support market or conversion conclusions.
- **No calibration:** weights, half-lives, thresholds, and bonuses have not been fitted to historical outcomes.
- **No live collection or enrichment:** signals come from a JSON file; there are no web scrapers, enrichment providers, APIs, LLMs, or secrets.
- **Hard ICP gates:** firmographic fit is pass/fail, not a nuanced fit score.
- **Exact string matching:** industry, region, and tool categories are not normalized or fuzzy-matched.
- **No deduplication or saturation:** repeated signals of the same type each contribute independently.
- **No persistence or integrations:** there is no database, scheduler, web service, or CRM sync.
- **No measured business impact:** runtime tests validate software behaviour, not sales outcomes.

A production next step would be to validate signal definitions and weights against historical outcomes, add deduplication and data-quality monitoring, instrument human overrides, and measure whether prioritisation improves rep efficiency or conversion. Any live integrations should be added only with appropriate access controls, observability, and a clear review process.

## Relevance to GTM Engineering and RevOps

The project demonstrates a few transferable systems principles:

- Translate an outbound strategy into explicit, configurable rules.
- Separate eligibility from prioritisation.
- Make recency and time assumptions visible.
- Design deterministic outputs that can be replayed and audited.
- Keep rules in configuration rather than burying them in code.
- Validate the operational contract with tests and CI before integrating a workflow.

These principles are relevant to GTM systems design, routing, prioritisation, and revenue operations. They do not by themselves demonstrate live CRM integration or production performance.

This public demo should be kept distinct from my separate prior GTM automation work, which involved real workflow orchestration and systems integrations. The repository here is synthetic and standalone.

## Website-ready project summary

**Signal Scoring Engine: Explainable GTM Account Prioritisation**

A Python CLI that screens fictional B2B accounts through ordered ICP, tool-conflict, and signal-freshness gates, then ranks qualified accounts using time-decayed buying signals and configurable combination bonuses. Includes per-account explanations, CSV export, deterministic replay, automated tests, and a three-version CI matrix.

**Built with:** Python, TOML, JSON, CSV, pytest, Ruff, GitHub Actions  
**Links:** [Source code](https://github.com/rudreshss09-svg/signal-scoring-engine) · [Technical case study](case-study.md) · [Architecture](architecture.md)

## Interview talking points

1. **Why gate before score?** Hard disqualifiers should not be compensated for by a high intent score. Short-circuiting also gives the rep one clear primary reason.
2. **Why use a fixed as-of date?** It makes runs reproducible and supports historical replay without the system clock changing results.
3. **Why show the formula?** Reps and operators should be able to audit the score and identify a questionable signal or rule rather than trust an opaque number.
4. **Why configuration-driven rules?** GTM teams need to tune ICP boundaries, signal weights, half-lives, and combinations without editing application logic.
5. **What would you add for production?** Historical calibration, signal deduplication, normalization, observability, human override capture, and measured outcome validation before live CRM activation.
6. **What is not claimed?** The demo does not collect live signals, call external APIs, sync a CRM, use an LLM, or prove conversion uplift.

## Run it locally

Follow the install and CLI instructions in the [repository README](../README.md). The shipped sample is safe to run without API keys or external services.
