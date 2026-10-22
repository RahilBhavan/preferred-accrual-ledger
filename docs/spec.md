# Local v1 scope and acceptance

Agreed continuation scope, as of 2026-10-21. Reuse the existing partial artifacts.

Replay sourced shares, declarations and schedules for STRF, STRC, STRE, STRK and STRD. Default to existing quarterly/semi-monthly terms. Expose approval of daily terms only as an explicit scenario. Track arrears/compounding separately from noncumulative STRD and keep currencies separate.

Acceptance:

1. Offline demo rebuilds from attributed frozen sources; identical reruns reproduce outputs.
2. Tests exercise real-source parsing, negative inputs and relevant domain invariants.
3. Sources include URLs, as-of dates and content hashes; current/niche claims checked against primary websites.
4. Observed, preliminary, fitted and assumed quantities are distinguished in outputs/documentation.
5. Exact commands, test counts and limitations appear in README; no license is chosen.
6. Commit locally only, each staged file <=20,000 bytes (5,000 estimated tokens). No external writes or recurring automation.

CLI-only v1. Existing figures are not a verified deliverable and will be excluded from the local commit. Frozen raw caches are preserved in compressed 18,000-byte archive parts, with offline restoration and per-source hash inventories. Generated results remain local and rebuild from those sources.
