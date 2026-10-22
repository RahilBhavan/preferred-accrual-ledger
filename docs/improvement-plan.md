# Explain the five aggregate gaps

Reader: a ledger reviewer tracing a reported total to dated components. Scope: additive
CLI/JSON reconciliation bridges, using the unchanged October 21 financial snapshot.
No new UI, source refresh, settlement inference or fitted financial inputs.

Done conditions:

1. All five out-of-tolerance checks have stable bridge IDs, USD amounts, source links,
   record/payment or funding dates, components, rounding uncertainty and unknown inputs.
2. STRE bridges expose EUR entitlement, ECB observation/date and implied company FX as a
   diagnostic only. No implied rate is substituted into the ledger.
3. September separately itemizes the three September 15 regular coupons from parsed
   June 10-Q principal/rate/date rows. Holding June principal constant is labeled a
   sensitivity, including when its numerical range overlaps reported funding.
4. Every bridge conserves: reported = component total + residual, for both range
   endpoints. Five raw gaps and 11/16 matches remain unchanged.
5. The standard offline demo writes a readable text drill-down and additive JSON
   bridges. Tests cover components, dates, signs, rounding and missing debt evidence;
   repeat runs reproduce all ten output files. A five-minute example and exact
   evidence/limits are documented; existing figure artifacts do not drift.

Baseline (2026-10-22): clean main at 3a0137f; 44 source hashes verified; 36 tests pass.
No glossary or ADR directory exists in this repository. Scope/spec: docs/spec.md;
existing accounting decisions: docs/terms.md, docs/contracts.md, docs/audit.md.
