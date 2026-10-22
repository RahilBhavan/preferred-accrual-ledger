# Validation evidence

Financial cutoff: 2026-10-21. Local runtime: Python 3.14.7, standard library only. CI pins Python 3.14.0 on Ubuntu 24.04, with full-SHA action references and read-only contents permission. It has no schedule, secrets or paid-service dependency. Python syntax is checked with `compileall`; there is no static typechecker configured.

```bash
python3 scripts/snapshot.py
python3 scripts/validate.py
python3 scripts/figure.py
python3 -m compileall -q ledger scripts tests
```

Observed: **36 tests passed**, **44 source bodies** matched the committed hash/size inventory, and **eight demo outputs** had identical hashes on consecutive runs. `validate.py` checks the exact required outputs, not unrelated local files. Exact hashes and commands are in [validation.json](validation.json).

Both current and approved scenarios reproduce. Current produces 37 events and 30 schedule rows through March 2027; approved produces 72 events and 438 rows. Both retain the same historical reconciliation: 11 of 16 numerical comparisons within source rounding tolerance, with five gaps documented in [audit](audit.md). All 30 conditional November amount/date rows match; this does not establish approval of daily terms.

A scratch copy under `~/scratch/preferred-accrual-ledger/` contained only publication-eligible files, with no restored cache, generated results or local environment. It restored the committed archive offline and passed the commands above. All eight output hashes matched the working copy. A remote fresh-clone check and CI run are recorded in [publication.md](publication.md).

Behavioral coverage includes record-date entitlement after issuance (including zero shares), cumulative arrears versus undeclared STRD forfeiture, declared-but-unpaid STRD, oldest-arrears-first allocation, regular compounding, step-up caps, deterministic replay, serial JSONL append/retry/reload, corrupt/truncated-store rejection, unique start-date balances, declaration chronology, unsupported payment dates, daily paid/missed scenarios, malformed input, empty CLI output and 2026–27 calendar boundaries. Regression tests failed before the fixes described in the audit.

The generated [summary SVG](reconciliation.svg) was inspected at 900 px; the [responsive table](result.html) at 728 and 390 px through T3's HTML preview, with no console errors. It uses Rahil's light figure colors and IBM Plex Sans with system fallback; fonts are not bundled. The wide README image is a summary; the responsive table and text audit carry the exact readable figures on narrow screens. No external website was deployed. No human reader study or cross-platform typography certification is claimed.

Reproducibility checks compare reruns on the tested interpreter and clean clone; they do not promise byte identity on every future Python version. A passing suite does not resolve legal/payment-model limitations. Hooks enforce the 20,000-byte staged-file limit and were not bypassed. No license was selected.
