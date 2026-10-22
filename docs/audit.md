# Correctness and source review

Publication review of the preserved v1 (`df21cf6`). Financial evidence stays frozen at **2026-10-21**; source fetch dates are separate in `provenance/`. This review does not update the October 28 proposal to an enacted term.

## Proven repairs

Every regression below failed before its fix and passed afterwards. No financial source values were fitted.

- A zero-share STRF record date followed by issuance incorrectly showed accrued entitlement on the new shares. An explicit `None` check preserves zero entitlement.
- A payment dated October 5 was applied on September 30. Early/late payment dates are now rejected; v1 supports payment events only on the obligation's payment date.
- An October 15 declaration could authorize an assumed September 30 payment. Late declarations are rejected; a September 20 declaration becomes visible on September 20, while retaining September 15 shares.
- A second opening balance silently reset outstanding shares. Replay now requires exactly one opening balance per included ticker, dated at replay start.
- Appending after a complete JSONL row without a final newline corrupted the file. Append now supplies the separator. Existing duplicate IDs and truncated JSON are rejected before any write.
- `--end 2026-06-30` crashed on an empty schedule. It now emits a header-only CSV.
- The Easter algorithm included an extra year-remainder term. It put 2027 Easter on April 18 instead of March 28, making March 26 a EUR business day. The corrected computation and holiday tests cover Good Friday/Easter Monday and Fed weekend substitutions. See [UK bank holidays](https://www.gov.uk/bank-holidays), [NY Fed holidays](https://www.newyorkfed.org/aboutthefed/holiday_schedule.html) and [TARGET operating schedule](https://www.ecb.europa.eu/paym/target/target2/profuse/calendar/html/index.en.html).
- Daily generation requested rates in an unnecessary 120-day margin before its effective date. A short November approved-scenario replay now works with a November rate; missed daily dividends still raise the intended unsupported-arrears error.

The validation script also included unrelated result files and tolerated missing required outputs. It now hashes exactly the eight demo files and fails if one is absent. A regression verifies both cases.

Tests also exercise oldest-arrears-first allocation: ten STRK shares miss September's $20; the December $20 pays old arrears first, leaving $0.40 old arrears plus $20 current arrears.

## Five aggregate gaps remain

These are comparisons under stated assumptions, not certification of payment accuracy. Units below are **USD millions**, including STRE translated from EUR. Model ranges vary weekly share dating; they are not guaranteed bounds. All 16 raw checks remain in `results/current/reconciliation.json`; 11 are within source rounding tolerance.

| Comparison | Reported | Model | Reported minus nearest bound |
|---|---:|---:|---:|
| STRE Q1 cash dividends | 22.342 | 22.277375 | 0.064625 |
| STRE Q2 cash dividends | 22.136 | 22.075875 | 0.060125 |
| STRC August 17 funding | 52.4 | 51.846816–52.3028875 | 0.0971125 |
| September 14–20 funding, including interest | 57.4 | 48.176809–49.0822515 | 8.3177485 |
| STRC October 15 funding | 45.5 | 45.2971075 | 0.2028925 |

**STRE FX:** The [10-Q](https://www.sec.gov/Archives/edgar/data/1050446/000105044626000044/mstr-20260630.htm) uses exchange rates at payment time, not necessarily the ECB reference rates. Under the assumed 7,750,000 shares and EUR 2.50 dividend, reported totals imply approximately 1.15313548 and 1.14250323 USD/EUR, versus modeled ECB 1.1498 and 1.1394. These ratios are diagnostic, not observed company FX. Actual conversion rates and earlier record-date balances are needed to resolve the gaps.

**August STRC:** Record July 31, nominal payment August 15, adjusted payment August 17. The [August 17 8-K](https://www.sec.gov/Archives/edgar/data/1050446/000119312526353240/mstr-20260817.htm) reports $52.4m of sale proceeds used to fund dividends. Neither its funding date nor weekly buyback totals establish exact entitled shares or settlement. Do not shift the record date to August 15 to fit it.

**October STRC:** September 30 entitlement is modeled at 90,594,215 shares × $0.50. The [October 19 8-K](https://www.sec.gov/Archives/edgar/data/1050446/000119312526424688/mstr-20261019.htm) gives $45.5m aggregate preferred funding. Its $202,892.50 residual is unresolved; funding and modeled dividends are different measures.

**September interest sensitivity:** The [September 21 filing](https://www.sec.gov/Archives/edgar/data/1050446/000119312526396093/mstr-20260914.htm) explicitly combines dividends and debt interest. The June 10-Q's Note 8 reports principal balances of $1,010m (2028), $800m (2030A), and $603.659m (2031), rates of 0.625%, 0.625%, and 0.875%, and March/September 15 coupon dates. Holding those balances constant gives a hypothetical semiannual coupon:

```text
1,010,000,000 × 0.00625 / 2 = 3,156,250
  800,000,000 × 0.00625 / 2 = 2,500,000
  603,659,000 × 0.00875 / 2 = 2,641,008.125
Total assumed coupons       = 8,297,258.125 USD
Plus modeled STRC           = 56.474067125–57.379509625 USD millions
```

That sensitivity overlaps $57.4m at its $0.05m rounding tolerance. It is a plausible explanation, **not an observed allocation or a new reconciled aggregate check**: intervening conversions, special interest and actual cash dates are not established here. The raw preferred-only comparison remains outside tolerance. September 28–October 4 funding also includes interest; its existing numerical overlap does not independently validate settlement.

## Review boundaries

The sweep covered correctness, error handling, security, accessibility (CLI/docs only), performance, dead code and project conventions. No measured performance defect or exploitable security defect survived the review. This is not a security certification. One T3 read-only review independently reproduced the late-declaration defect and the five gaps; the parent implemented and verified fixes.

Arrears are approximate open-period scenarios, not legal-accounting calculations. STRD forfeiture means undeclared amounts do not accumulate in this model; declared unpaid amounts remain separate. The frozen corpus is not a point-in-time information backtest: `as_of` controls assumed future payment, not availability of all filings/rates. JSONL supports serial writers and validates retry/restart; it has no concurrent-writer lock, transactional durability or automatic recovery of partial writes.
