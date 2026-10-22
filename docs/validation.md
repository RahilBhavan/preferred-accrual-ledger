# Local validation evidence

Validated the continuation on Python 3.14.7, financial cutoff 2026-10-21. No external account writes.

```bash
python3 scripts/validate.py
```

This runs the source verifier, unittest suite and each README demo twice. Observed: 23 tests passed; 44 source bodies matched the committed SHA-256 inventory; 8 generated files had identical hashes on consecutive runs. Exact output hashes and invoked demo commands are in [validation.json](validation.json). Floating-point model outputs are tied to the documented Python/NumPy environment, not a cross-platform byte-identity guarantee.

Cold-restore check: copied only the files eligible for the local commit into a new directory under `~/scratch/preferred-accrual-ledger/cold-check`, with no raw cache, generated results or installed repo environment. Restored `snapshot/` offline, ran all tests/demos and compared generated hashes with the working repo. The hashes matched. The earnings check used the documented pinned dependency environment under `~/scratch/strategy-fair-value-earnings/venv`. Scratch copies were removed after validation.

Real-source behavior, negative inputs and domain invariants are exercised in `tests/`. A passing suite does not resolve the financial/model limitations in the README. Relative documentation links, whitespace and staged-file sizes were checked before committing. The local pre-commit hook checks index sizes and rejects any staged file above 20,000 bytes (5,000 estimated tokens); it was enabled and not bypassed.

No charts or existing partial figures are part of the validated deliverable. No license was selected. Generated outputs remain available locally and are recreated by the README commands.
