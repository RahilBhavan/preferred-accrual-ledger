# Preferred accrual ledger: replay five sourced preferred dividend schedules

This tool works out how much Strategy owes in dividends on its five preferred stocks and when, using its SEC filings, then checks the totals against what the company reported paying.

[![Offline ledger checks](https://github.com/RahilBhavan/preferred-accrual-ledger/actions/workflows/ci.yml/badge.svg)](https://github.com/RahilBhavan/preferred-accrual-ledger/actions/workflows/ci.yml)

![11 of 16 checks are within rounding tolerance: quarterly cash totals 6/8, weekly funding 4/7, conditional daily total 1/1. Five gaps remain; funding is not settlement.](docs/reconciliation.svg)

An offline event-replay tool for Strategy's STRF, STRC, STRE, STRK and STRD dividend schedules, entitlements and unpaid scenarios. It keeps USD and EUR separate, fixes entitlement at record dates, and separates cumulative arrears from noncumulative STRD. Financial cutoff: **October 21, 2026**. The [review](docs/audit.md) explains five unresolved aggregate differences without fitting source values.

## What it does

- Replays 37 sourced events from a June 30 opening balance under existing terms and emits dated schedules through March 2027 (`results/current/schedule.csv`). Every seeded row has `status=assumed_settled`; `paid` needs a supplied payment event. `basis` says whether the amount was `declared` or `projected` from the terms.
- Answers "what is due in this window" with `--from/--to` or `--next-days N`, filtered on payment date.
- Shows each row's `payment_form` (`cash`, or `election_unknown` for undeclared STRK, which may be paid in Class A stock) and the share change since the previous record date with the weekly 8-Ks that report it. STRC record-date shares fall from 104,894,705 (June 30) to 85,982,656 (October 31): 18,912,049 shares of reported repurchases, each dated at its 8-K period end.
- Tests all 30 rows of the conditional November STRC daily table. Daily terms are available only with `--scenario approved`; the October 28 vote remains pending at the cutoff.
- Reports 11 of 16 aggregate reconciliation checks within source rounding tolerance (`reconciliation.json`). The five that miss stay open. Each lists the filed figures checked against it, with form, accession number and filing date, and a one-line reason it cannot close yet.
- Found that Strategy's two 2026 10-Qs disagree on Q1 STRE cash dividends: the 10-Q for the quarter ended March 31 reports $22,895 thousand, while the June 30 10-Q's six-month less three-month figures give $22,342 thousand, a $553 thousand difference (`bridges` in `reconciliation.json`).
- Rejects duplicate/conflicting IDs, supports idempotent JSONL append/reload, and tests record-date entitlement, compounding, step-up caps and undeclared STRD forfeiture.

## How it works

`ledger/filings.py` parses cached filings; `seed.py` creates attributed events; `schedule.py` computes per-share schedules; `engine.py` replays shares, declarations and payment assumptions; `reconcile.py` compares model amounts with filed totals; `bridges.py` explains each gap and sets filed cross-checks beside it.

## Run it

Python 3.12+. The 55 tests also passed on Python 3.12.14. Local validation uses Python 3.14.7 and CI pins Python 3.14.0. Standard library only. From a fresh clone:

```bash
git clone https://github.com/RahilBhavan/preferred-accrual-ledger.git
cd preferred-accrual-ledger
python3 scripts/snapshot.py
python3 scripts/verify_sources.py
python3 -m unittest discover -s tests -v
python3 -m ledger
python3 -m ledger --scenario approved --out results/approved
python3 scripts/validate.py
python3 scripts/figure.py
```

Observed: **55 tests passed**. Current terms produce 37 events and 30 schedule rows; the approved scenario produces 72 events and 438 rows through March 2027. Both produce `schedule.csv`, `events.jsonl`, `summary.json`, `reconciliation.json` and `reconciliation.txt`. No credentials or dependency install are needed. `validate.py` verifies source hashes, runs tests and repeats both demos, comparing ten output hashes. `figure.py` rebuilds the figure and a responsive local result table; it does not host a website.

To list payments due in a window, add `--from`/`--to` (ISO dates, inclusive) or `--next-days N` (the N days after the October 21, 2026 cutoff). Stdout becomes CSV; the full files are still written. Observed output:

```bash
python3 -m ledger --from 2026-12-01 --to 2026-12-31 2>/dev/null
```

```text
ticker,currency,record_date,payment_date,record_shares,amount,status,basis,payment_form
STRC,USD,2026-11-30,2026-12-15,85982656,42991328.00,assumed_settled,projected,cash
STRC,USD,2026-12-15,2026-12-31,85982656,42991328.00,assumed_settled,projected,cash
STRD,USD,2026-12-15,2026-12-31,14024221,35060552.50,assumed_settled,projected,cash
STRE,EUR,2026-12-15,2026-12-31,7750000,19375000.00,assumed_settled,projected,cash
STRF,USD,2026-12-15,2026-12-31,12839689,32099222.50,assumed_settled,projected,cash
STRK,USD,2026-12-15,2026-12-31,14020744,28041488.00,assumed_settled,projected,election_unknown
```

`python3 -m ledger --next-days 45 2>/dev/null` returns the two declared STRC payments (November 2 and 16) and the projected November 30 payment. STRE amounts are EUR.

## Trace a gap in five minutes

Run `python3 scripts/snapshot.py && python3 -m ledger`, then open
`results/current/reconciliation.txt`. Search for `strc-funding-2026-09-21`:
the 8-K's $57.4m used "to fund the payment of dividends on its preferred stock and
interest on its outstanding indebtedness" is separated into modeled STRC dividends, three
regular-coupon sensitivities totaling $8,297,258.125, and an unknown residual
of $20,490.375–$925,932.875. The coupons hold June principal constant, so the raw
check still fails. Its `Open:` line names the missing inputs.

The same five bridges are in `reconciliation.json` under `bridges`, with USD
amounts, source links, dated inputs, rounding uncertainty, unknowns, filed
cross-checks (`filed_evidence`) and an `open_reason`. See
[the bridge contract](docs/contracts.md#reconciliation-bridges).

## Repository layout

- `ledger/`: terms, calendars, events, replay, reconciliation and CLI.
- `scripts/`: offline source restoration and hash verification.
- `snapshot/`: compressed frozen source cache.
- `provenance/`: source URL/date/hash inventories.
- `tests/`: real-source checks and replay invariants.
- `docs/`: scope, terms, reconciliation and validation.
- `AGENTS.md`, `CLAUDE.md`, `DESIGN.md`, `design/`, `.githooks/`: instructions, design tokens and a pre-commit size check for the coding agents that work in this repository. The code does not use them.

## Documentation

- [Public design system](DESIGN.md): Rahil Design 3.3.0, shared tokens and visual review rules.
- [Scope and acceptance](docs/spec.md): local v1 contract.
- [Terms and limitations](docs/terms.md): schedules, scenarios and arrears boundary.
- [Reconciliation](docs/reconciliation.md): unresolved mismatches and provenance.
- [Validation](docs/validation.md): tests and reproducibility checks.
- [Correctness review](docs/audit.md): proven fixes and all five aggregate gaps.
- [Consumer contract](docs/contracts.md): portable source and output formats for other tools.
- [Publication receipt](docs/publication.md): commit, clean-clone and CI evidence.

## Sources

The snapshot preserves 45 attributed source bodies: primary SEC filings/declarations and ECB currency observations. Financial inputs include the March and June 2026 10-Qs ([0001050446-26-000031](https://www.sec.gov/Archives/edgar/data/1050446/000105044626000031/mstr-20260331.htm), filed 2026-05-06; [0001050446-26-000044](https://www.sec.gov/Archives/edgar/data/1050446/000105044626000044/mstr-20260630.htm), filed 2026-08-03), the October 5 proxy and weekly 8-Ks through October 19. See `provenance/` and the [source discussion](docs/reconciliation.md). The archive and individual bodies have SHA-256 checks; original URL/fetch metadata is restored with the cache. Third-party filings/data are attributed research inputs; no ownership of them is claimed.

## Scope and limits

- Independent research, not affiliated with Strategy. Not an operational paying-agent ledger; no bank settlement feed is connected.
- Existing quarterly/semi-monthly terms are the default. Daily terms are a hypothetical branch; STRE stays quarterly.
- Opening arrears are zero and weekly share changes use assumed dating. Declared amounts are assumed settled.
- Current-term arrears use approximate open-period/stub treatment. Daily-scenario arrears, late declarations and early/late payment events are rejected. Cross-series legal payment blockers are not modeled.
- STRK stock payments are monetary values, not delivered share counts; future STRK payment form is unknown. Holidays use encoded rules without ad hoc closures.
- Five of 16 aggregate checks do not reconcile. Funding is not settlement, and ECB reference FX may differ from the company's payment-time rate.
- `as_of` controls payment projections, not point-in-time availability of every filing. JSONL retry/restart supports one serial writer, with no crash-durability guarantee.

## License

[MIT](LICENSE). The license covers this project's code only. Third-party filings/data retain their owners' rights.

Part of [Rahil Bhavan's projects](https://github.com/RahilBhavan).
