# Preferred accrual ledger: replay five sourced preferred dividend schedules

[![Offline ledger checks](https://github.com/RahilBhavan/preferred-accrual-ledger/actions/workflows/ci.yml/badge.svg)](https://github.com/RahilBhavan/preferred-accrual-ledger/actions/workflows/ci.yml)

![11 of 16 checks are within rounding tolerance: quarterly cash totals 6/8, weekly funding 4/7, conditional daily total 1/1. Five gaps remain; funding is not settlement.](docs/reconciliation.svg)

An offline event-replay tool for Strategy's STRF, STRC, STRE, STRK and STRD dividend schedules, entitlements and unpaid scenarios. It preserves USD/EUR currencies and sources, fixes entitlement at record dates, and separates cumulative arrears from noncumulative STRD. Financial cutoff: **October 21, 2026**. The [review](docs/audit.md) explains five unresolved aggregate differences without fitting source values.

## What it does

- Replays 37 sourced events from a June 30 opening balance under existing terms and emits dated schedules through March 2027 (`results/current/schedule.csv`). Future payments and settlement of declarations are assumptions, so every seeded row has `status=assumed_settled`; `paid` needs a supplied payment event. `basis` says whether the amount was `declared` or `projected` from the terms.
- Answers "what is due in this window" with `--from/--to` or `--next-days N`, filtered on payment date.
- Shows each row's `payment_form` (`cash`, or `election_unknown` for undeclared STRK, which may be paid in Class A stock) and the share change since the previous record date with the weekly 8-Ks that report it. STRC record-date shares fall from 104,894,705 (June 30) to 85,982,656 (October 31): 18,912,049 shares of reported repurchases, each dated at its 8-K period end.
- Tests all 30 rows of the conditional November STRC daily table. Daily terms are available only with `--scenario approved`; the October 28 vote remains pending at the cutoff.
- Reports 11 of 16 aggregate reconciliation checks within source rounding tolerance. Five mismatches remain visible; FX, record-date share assumptions and funding-versus-settlement differences limit agreement (`reconciliation.json`).
- Rejects duplicate/conflicting IDs, supports idempotent JSONL append/reload, and tests record-date entitlement, compounding, step-up caps and undeclared STRD forfeiture.

## How it works

`ledger/filings.py` parses cached filings; `seed.py` creates attributed events; `schedule.py` computes per-share schedules; `engine.py` replays shares, declarations and payment assumptions; `reconcile.py` compares model amounts with filed totals. No bank settlement feed is connected.

## Run it

Python 3.12+; local validation uses Python 3.14.7 and CI pins Python 3.14.0. Standard library only. From a fresh clone:

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

Observed: **50 tests passed**. Current terms produce 37 events and 30 schedule rows; the approved scenario produces 72 events and 438 rows through March 2027. Both produce `schedule.csv`, `events.jsonl`, `summary.json`, `reconciliation.json` and `reconciliation.txt`. No credentials or dependency install are needed. `validate.py` verifies source hashes, runs tests and repeats both demos, comparing ten output hashes. `figure.py` rebuilds the figure and a responsive local result table; it does not host a website.

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
of $20,490.375–$925,932.875. The coupon sensitivity holds June principal constant;
it does not establish actual September payments. The raw check still fails.

The same five bridges are in `reconciliation.json` under `bridges`, with USD
amounts, source links, dated inputs, rounding uncertainty and unknowns. See
[the bridge contract](docs/contracts.md#reconciliation-bridges).

## Repository layout

- `ledger/`: terms, calendars, events, replay, reconciliation and CLI.
- `scripts/`: offline source restoration and hash verification.
- `snapshot/`: compressed frozen source cache.
- `provenance/`: source URL/date/hash inventories.
- `tests/`: real-source checks and replay invariants.
- `docs/`: scope, terms, reconciliation and validation.

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

The snapshot preserves 44 attributed source bodies: primary SEC filings/declarations and ECB currency observations. Financial inputs include the June 2026 10-Q and weekly 8-Ks through October 19. See `provenance/` and the [source discussion](docs/reconciliation.md). The archive and individual bodies have SHA-256 checks; original URL/fetch metadata is restored with the cache. Third-party filings/data are attributed research inputs; no ownership of them is claimed.

## Scope and limits

- Independent research, not affiliated with Strategy. This is not an operational paying-agent ledger.
- Existing quarterly/semi-monthly terms are the default. Daily approval is a hypothetical branch; STRE remains quarterly.
- Zero opening arrears; weekly share changes use assumed dating. Declared amounts are assumed settled; absent evidence is not proof of an actual missed dividend.
- Current-term arrears use approximate open-period/stub treatment. Daily-scenario arrears, late declarations and early/late payment events are rejected. Cross-series legal payment blockers are not modeled.
- STRK stock payments are monetary values, not delivered share counts. `payment_form=cash` for STRK rests on a cash declaration; future STRK form is unknown. Holidays use encoded rules without ad hoc closures. See terms before extending to other years.
- USD and EUR are not summed implicitly. Aggregate reconciliation is incomplete.
- Replay uses the supplied frozen event set; `as_of` controls payment projections, not point-in-time availability of every filing. JSONL retry/restart supports a serial writer; it has no concurrent-writer or crash-durability guarantee.

## License

[MIT](LICENSE). The license covers this project's code only. Third-party filings/data retain their owners' rights.

Part of [Rahil Bhavan's projects](https://github.com/RahilBhavan).
