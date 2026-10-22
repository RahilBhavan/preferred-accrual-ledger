# Portable consumer contracts

This CLI owns the ledger and frozen source inputs. Consumers can clone this repository and run its standard-library Python commands; no imports from sibling repositories or personal hub are required. This is a research v1 contract, not a settlement API.

## Source snapshot

`snapshot/index.json` records the financial cutoff, part count, total compressed bytes and archive SHA-256. `scripts/snapshot.py` restores those parts into ignored `data/raw/`. `provenance/sources-*.csv` records `path,url,fetched_utc,sha256,bytes` for each of 44 public SEC/ECB bodies. Sidecar `*.meta.json` files restore the same metadata. Run `scripts/verify_sources.py` before consuming inputs. `fetched_utc` is retrieval time; it is not the financial as-of date or date a proposal became effective.

## Event log

`python3 -m ledger` emits `results/current/events.jsonl`. Each row is an `Event` from `ledger/events.py`. Stable IDs derive from ticker, kind and source period; the JSON serializer uses sorted keys and ISO dates. Decimal values are strings. Required fields are `id,kind,ticker,date`; payload fields depend on `kind`. `source_url,as_of,note,condition` preserve provenance and assumptions. Conditions are explanatory text, not an evaluated rules language: choose `build_events('current')` or `build_events('approved')` explicitly.

`load_jsonl(path)` rejects duplicate IDs and malformed lines. `append_jsonl(path, events)` returns `(added, skipped)`, skips identical retries and rejects conflicting IDs before writing. Replay sorts events deterministically. Stores support a serial writer; truncated writes require manual recovery from a known-good copy. Do not use this as a concurrent financial journal.

Replay requires one opening balance per included ticker at `start`; it does not carry a previous replay's arrears/state forward automatically. A restart means reload the complete event log and replay from the same start. Payment events must use the obligation's modeled payment date; declarations after that date are unsupported.

## Outputs

`schedule.csv` always has these columns, including for zero rows:

```text
ticker,currency,record_date,payment_date,regime,per_share,declared_per_share,
record_shares,amount,model_settlement,status,basis,source
```

The two lines above describe one CSV header. Dates use ISO format. `per_share` is terms-derived; `declared_per_share` is the amount used at record/declaration, which can also be projected/terms-derived. Read `basis` with it. Amounts use instrument currency, **not automatically USD**. `model_settlement` is an assumption unless an explicit supported payment event is supplied; the CLI seed supplies declarations, not a bank feed. Future schedule rows can extend beyond `--end` only by payment/accrual window; the CSV filters record dates after `--end`.

`summary.json` identifies `as_of,scenario,status,opening_share_date,events,ending_state,warnings`. Warnings include conditional declarations inapplicable under the chosen regime. `as_of` controls projections and does not filter the full source corpus into a point-in-time information set.

`reconciliation.json` contains `checks,november_daily_rows,declared_vs_terms`. Each check carries `label,source_url,as_of,reported,ledger_low,ledger_high,unit,note,rounding_uncertainty,within,delta`. Decimal values are strings. `delta` is reported minus the nearest model bound, zero inside the model range; `within` additionally allows source rounding uncertainty. It is a numerical comparison, not a statement that a funding measure proves settlement. The five raw gaps must remain visible to downstream users. Reconciliation is a fixed historical diagnostic shared by both scenario outputs, not a function of the CLI projection horizon.

Consumers should retain currencies, scenario and source links, tolerate additive fields and fail explicitly on unknown semantics. No data refresh or calibration is implied by rerunning the offline snapshot.
