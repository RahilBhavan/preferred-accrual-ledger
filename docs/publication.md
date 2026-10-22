# Publication receipt

Repository: `https://github.com/RahilBhavan/preferred-accrual-ledger`

Financial snapshot: **2026-10-21**. Publication continuation preserves the original `df21cf6` v1 and its history. It repairs proven defects, records unresolved evidence gaps, and adds reproducible offline verification. No license was selected; no website was deployed.

## Pre-publication evidence

- Local Python 3.14.7: 36 tests passed, 44 source bodies verified, eight demo output hashes repeated.
- Clean scratch restore passed tests, demos, figure generation and syntax checks without dependencies or credentials. Hashes matched the working copy.
- Current demo: 37 events / 30 schedule rows. Approved scenario: 72 events / 438 rows. Both retain 11/16 aggregate comparisons; five discrepancies remain in the audit.
- Inspected tracked/current files and all reachable Git blobs, plus the decompressed source archive. No credentials, private account records, databases, caches or user contact artifacts were found in published file content. Public issuer contact details occur in attributed SEC documents. Existing Git author metadata was verified already public in GitHub commit search; it is retained with the original commit. New commits use GitHub's no-reply address.
- Archive: SHA-256 `6dccb7dd33f21d9d6fbcc84ef2441dd7b4d78b6aa3d055e8f759476b671c69d7`. All archive members are public source bodies/metadata under `data/raw/`. No source refresh was performed.
- Each staged source file is at most 20,000 bytes; no hook bypass, history rewrite or force push.

## Remote verification

- Public repository created under authenticated `RahilBhavan`; default branch is `main`.
- Reviewed implementation commit: [`7c14621001c832de625078cb55e90cf79a4609b6`](https://github.com/RahilBhavan/preferred-accrual-ledger/commit/7c14621001c832de625078cb55e90cf79a4609b6), containing the original `df21cf6` ancestor and correctness commit `f5abd70`.
- [GitHub Actions run 39718963656](https://github.com/RahilBhavan/preferred-accrual-ledger/actions/runs/39718963656) passed on Python 3.14.0 / Ubuntu 24.04 at 2026-10-22 03:50 UTC. Publication/check time is separate from the frozen financial cutoff.
- A new HTTPS clone from GitHub restored the snapshot and ran every README command: source verification, 36 tests, both scenarios, `validate.py`, `figure.py` and `compileall`. Eight output hashes matched the working copy and `git diff --exit-code` passed after generation.
- Remote `main` SHA was checked against the reviewed local commit. The receipt follow-up changes only this evidence and the verified CI badge; execution source and frozen inputs are unchanged. The final receipt commit is visible in repository history and is checked again before goal completion.
- No PR, deployment, account transaction, schedule or outbound message was created. Repository About/topics describe the actual offline research tool.

The publication goal is completed only after the final remote commit, clean-clone commands and CI are confirmed. The persistent goal status is maintained in the T3 project chat; five source discrepancies remain explicitly unresolved.

## Update 2026-10-22: license

The MIT license was added in `LICENSE`. It covers this project's code only. Earlier statements in this record that no license file existed describe the state at publication.
