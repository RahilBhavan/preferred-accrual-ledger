"""Dividend terms of Strategy's five preferreds, encoded from the filed documents.

Each Instrument cites the document a term comes from. Quotes and page references are in
docs/terms.md. Where the encoding is an interpretation rather than a quotation, the field
comment says so.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from decimal import Decimal

D = Decimal
SEC = "https://www.sec.gov/Archives/edgar/data/1050446"

PROXY = f"{SEC}/000119312526413159/d503578ddef14a.htm"          # DEF 14A, 2026-10-05
TENQ = f"{SEC}/000105044626000044/mstr-20260630.htm"           # 10-Q, quarter ended 2026-06-30
TENQ_Q1 = f"{SEC}/000105044626000031/mstr-20260331.htm"        # 10-Q, quarter ended 2026-03-31
EX42 = f"{SEC}/000105044626000020/ex42descriptionofregistere.htm"  # 10-K 2025, Ex. 4.2
STRE_COD = f"{SEC}/000119312525280178/d205736dex31.htm"         # STRE CoD, 8-K 2025-11-13
DECL_NOV_DAILY = f"{SEC}/000119312526423400/mstr-20261015.htm"   # 8-K 2026-10-15


@dataclass(frozen=True)
class Instrument:
    ticker: str
    name: str
    currency: str                 # "USD" or "EUR"
    stated_amount: Decimal        # per share, in currency
    fixed_rate: Decimal | None    # None for STRC (variable; supplied by RateReset events)
    cumulative: bool
    compounding: str | None       # "step_up" (rate+1%, +1% per period, cap 18%), "regular", or None
    base_regime: str              # regime in force before any RegimeChange event
    calendar: str                 # business-day calendar for payment dates
    stock_payment_allowed: bool   # STRK only: Class A common stock at the company's election
    liquidation_rank: int         # 1 = most senior among the preferreds
    sources: tuple[str, ...]


INSTRUMENTS: dict[str, Instrument] = {
    "STRF": Instrument("STRF", "10.00% Series A Perpetual Strife Preferred Stock", "USD", D(100), D("0.10"),
                       True, "step_up", "quarterly", "USD", False, 1, (EX42, PROXY, TENQ)),
    "STRC": Instrument("STRC", "Variable Rate Series A Perpetual Stretch Preferred Stock", "USD", D(100), None,
                       True, "regular", "semimonthly", "USD", False, 2, (PROXY, TENQ)),
    "STRE": Instrument("STRE", "10.00% Series A Perpetual Stream Preferred Stock", "EUR", D(100), D("0.10"),
                       True, "step_up", "quarterly", "EUR", False, 3, (STRE_COD, TENQ)),
    "STRK": Instrument("STRK", "8.00% Series A Perpetual Strike Preferred Stock", "USD", D(100), D("0.08"),
                       True, "regular", "quarterly", "USD", True, 4, (EX42, PROXY, TENQ)),
    "STRD": Instrument("STRD", "10.00% Series A Perpetual Stride Preferred Stock", "USD", D(100), D("0.10"),
                       False, None, "quarterly", "USD", False, 5, (EX42, PROXY, TENQ)),
}

# Proposal 1 of the 2026-10-05 proxy. STRE is not part of it and stays quarterly.
# Effective times are 12:01 a.m. ET on these dates if stockholders approve on 2026-10-28.
PROPOSED_DAILY_EFFECTIVE: dict[str, dt.date] = {
    "STRC": dt.date(2026, 11, 1),
    "STRF": dt.date(2027, 1, 1),
    "STRK": dt.date(2027, 1, 1),
    "STRD": dt.date(2027, 1, 1),
}

STEP_UP_INCREMENT = D("0.01")
STEP_UP_CAP = D("0.18")

# STRK paid in Class A stock: shares = amount / (95% x daily VWAP on the 3rd VWAP trading day
# before the payment date), capped at total dividend / floor price (10-K 2025 Ex. 4.2).
STRK_STOCK_PRICE_FACTOR = D("0.95")
STRK_INITIAL_FLOOR_PRICE = D("119.03")  # initial value; adjusts with the conversion rate (not tracked)
