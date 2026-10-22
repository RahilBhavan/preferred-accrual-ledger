# Preferred accrual ledger: replay five sourced preferred dividend schedules

A local event-replay tool for Strategy's STRF, STRC, STRE, STRK and STRD dividend schedules, entitlements and unpaid scenarios. It preserves USD/EUR currencies and sources, fixes entitlement at record dates, and separates cumulative arrears from noncumulative STRD. Financial cutoff: October 21, 2026.

## What it does

- Replays 37 sourced events from a June 30 opening balance under existing terms and emits dated schedules through March 2027 (`results/current/`). Future payments and settlement of declarations are assumptions.
- Tests all 30 rows of the conditional November STRC daily table. Daily terms are available only with `--scenario approved`; the October 28 vote remains pending at the cutoff.
- Reports 11 of 16 aggregate reconciliation checks within source rounding tolerance. Five mismatches remain visible; FX, record-date share assumptions and funding-versus-settlement differences limit agreement (`reconciliation.json`).
- Rejects duplicate/conflicting IDs, supports idempotent JSONL append/reload, and tests record-date entitlement, compounding, step-up caps and undeclared STRD forfeiture.

## How it works

`ledger/filings.py` parses cached filings; `seed.py` creates attributed events; `schedule.py` computes per-share schedules; `engine.py` replays shares, declarations and payment assumptions; `reconcile.py` compares model amounts with filed totals. No bank settlement feed is connected.

## Run it

Python 3.12+; tested with Python 3.14.7. Standard library only. From this repository:

```bash
python3 scripts/snapshot.py
python3 scripts/verify_sources.py
python3 -m unittest discover -s tests -v
python3 -m ledger
python3 -m ledger --scenario approved --out results/approved
```

Observed: **23 tests passed**. The first demo retains current schedules; the second assumes approval and effectiveness of the proposed daily terms. Both produce `schedule.csv`, `events.jsonl`, `summary.json` and `reconciliation.json`. No credentials or dependency install are needed. Repeating these commands reproduces output hashes.

## Repository layout

- `ledger/`: terms, calendars, events, replay, reconciliation and CLI.
- `scripts/`: offline source restoration and hash verification.
- `snapshot/`: compressed frozen source cache.
- `provenance/`: source URL/date/hash inventories.
- `tests/`: real-source checks and replay invariants.
- `docs/`: scope, terms, reconciliation and validation.

## Documentation

- [Scope and acceptance](docs/spec.md): local v1 contract.
- [Terms and limitations](docs/terms.md): schedules, scenarios and arrears boundary.
- [Reconciliation](docs/reconciliation.md): unresolved mismatches and provenance.
- [Validation](docs/validation.md): tests and reproducibility checks.

## Sources

The snapshot preserves 44 attributed source bodies: primary SEC filings/declarations and ECB currency observations. Financial inputs include the June 2026 10-Q and weekly 8-Ks through October 19. See `provenance/` and the [source discussion](docs/reconciliation.md). Original metadata is restored with the cache.

## Scope and limits

- Independent research, not affiliated with Strategy. This is not an operational paying-agent ledger.
- Existing quarterly/semi-monthly terms are the default. Daily approval is a hypothetical branch; STRE remains quarterly.
- Zero opening arrears; weekly share changes use assumed dating. Declared amounts are assumed settled; absent evidence is not proof of an actual missed dividend.
- Current-term arrears use approximate open-period/stub treatment. Daily-scenario arrears are rejected. Late settlement and cross-series legal payment blockers are not comprehensively modeled.
- STRK stock payments are monetary values, not delivered share counts. Holidays use encoded rules without ad hoc closures. See terms before extending to other years.
- USD and EUR are not summed implicitly. Aggregate reconciliation is incomplete.

## License

No license file yet. Third-party filings/data retain their owners' rights.

Part of [Rahil Bhavan's projects](https://github.com/RahilBhavan).
