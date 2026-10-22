"""Per-share dividend schedules for the three regimes in the filings.

quarterly    STRF/STRK/STRD (original CoDs) and STRE: paid Mar 31, Jun 30, Sep 30, Dec 31
             (next Business Day if not one), record date the 15th of that month, accrual
             from and including the prior payment date to but excluding the next, 30/360.
semimonthly  STRC (A&R CoD effective 2026-06-30): periods 1st-15th and 16th-last day, paid
             on the 15th and the last day, record dates the last day of the prior month and
             the 15th. A full period is deemed 15 days: S x rate / 24.
daily        Proposed A&R CoDs: every calendar day is a record date, paid on the next
             Business Day. Each semi-monthly period accrues S x rate / 24, spread evenly over
             its calendar days with the cumulative formula
                 D_n = S x DR/24 x n/N - sum(D_0..D_{n-1})
             rounded down to the cent except on the period's last day.

Regime switches follow the filed transition: an obligation of the old regime exists only if
its accrual window ends before the new regime's effective date.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal

from .calendars import ONE_DAY, days_30_360, last_day_of_month, next_business_day

CENT = Decimal("0.01")
QUARTER_ENDS = ((3, 31), (6, 30), (9, 30), (12, 31))


@dataclass(frozen=True)
class Obligation:
    """One record date's dividend per share, before share counts are applied."""
    ticker: str
    regime: str
    window_start: dt.date   # first calendar day whose accrual this obligation carries
    window_end: dt.date     # last such day (inclusive)
    record_date: dt.date
    nominal_pay_date: dt.date
    pay_date: dt.date       # nominal date moved to the next Business Day if needed
    rate: Decimal
    per_share: Decimal      # computed from the terms (a declaration may state its own amount)

    @property
    def key(self) -> tuple[str, dt.date]:
        return (self.ticker, self.record_date)


def _quarter_windows(start: dt.date, end: dt.date):
    """(previous payment date, this payment date) pairs whose payment date is in [start, end]."""
    for year in range(start.year - 1, end.year + 2):
        for i, (m, d) in enumerate(QUARTER_ENDS):
            pay = dt.date(year, m, d)
            pm, pd = QUARTER_ENDS[i - 1]
            prev = dt.date(year - (i == 0), pm, pd)
            if start <= pay <= end:
                yield prev, pay


def quarterly(ticker, stated, rate_on, calendar, start, end):
    out = []
    for prev, pay in _quarter_windows(start, end):
        rate = rate_on(prev)
        per_share = stated * rate * days_30_360(prev, pay) / 360
        out.append(Obligation(ticker, "quarterly", prev, pay - ONE_DAY, pay.replace(day=15), pay,
                              next_business_day(pay, calendar), rate, per_share))
    return out


def _semi_month(day: dt.date) -> tuple[dt.date, dt.date]:
    if day.day <= 15:
        return day.replace(day=1), day.replace(day=15)
    return day.replace(day=16), last_day_of_month(day)


def semimonthly(ticker, stated, rate_on, calendar, start, end):
    out = []
    day = _semi_month(start)[0]
    while day <= end:
        w_start, w_end = _semi_month(day)
        record = w_start - ONE_DAY            # last day of prior month, or the 15th
        rate = rate_on(w_start)               # rate period runs 16th..15th, so constant per window
        per_share = stated * rate / 24
        if start <= w_end <= end:
            out.append(Obligation(ticker, "semimonthly", w_start, w_end, record, w_end,
                                  next_business_day(w_end, calendar), rate, per_share))
        day = w_end + ONE_DAY
    return out


def daily_amounts(stated: Decimal, rate: Decimal, n_days: int) -> list[Decimal]:
    """Per-share amounts for each record date of one semi-monthly period (proxy Annex formula)."""
    if n_days < 1 or not stated.is_finite() or not rate.is_finite() or stated < 0 or rate < 0:
        raise ValueError("invalid daily amount inputs")
    full = stated * rate / 24
    amounts: list[Decimal] = []
    for n in range(1, n_days + 1):
        due = full * n / n_days - sum(amounts, Decimal(0))
        amounts.append(due if n == n_days or due.is_nan() else due.quantize(CENT, rounding=ROUND_DOWN))
    return amounts


def daily(ticker, stated, rate_on, calendar, start, end):
    out = []
    day = _semi_month(start)[0]
    while day <= end:
        w_start, w_end = _semi_month(day)
        rate = rate_on(w_start)               # monthly rate period = calendar month of record date
        n_days = (w_end - w_start).days + 1
        for i, amount in enumerate(daily_amounts(stated, rate, n_days)):
            record = w_start + dt.timedelta(days=i)
            if start <= record <= end:
                pay = next_business_day(record, calendar, strictly_after=True)
                out.append(Obligation(ticker, "daily", record, record, record, pay, pay, rate, amount))
        day = w_end + ONE_DAY
    return out


GENERATORS = {"quarterly": quarterly, "semimonthly": semimonthly, "daily": daily}


def build_schedule(instrument, regimes, rate_on, start: dt.date, end: dt.date) -> list[Obligation]:
    """Obligations whose accrual window overlaps [start, end].

    regimes: list of (effective_date, regime) sorted by date; the first entry is the base regime
    with effective_date = date.min. rate_on(day) gives the annual rate in force on a day.
    An obligation belongs to a regime if its window starts on or after that regime's effective
    date and ends before the next regime's effective date.
    """
    margin = dt.timedelta(days=120)

    def lenient(day):  # the margin may reach days with no known rate; only kept windows must have one
        try:
            return rate_on(day)
        except ValueError:
            return Decimal("NaN")

    out: list[Obligation] = []
    for i, (effective, regime) in enumerate(regimes):
        nxt = regimes[i + 1][0] if i + 1 < len(regimes) else dt.date.max
        lo = max(start, effective)
        hi = min(end, nxt - ONE_DAY)
        if lo > hi:
            continue
        # Daily windows are single record dates; no surrounding payment-window margin is needed.
        # Generating that margin demanded rates before the daily regime even took effect.
        pad = dt.timedelta(0) if regime == "daily" else margin
        candidates = GENERATORS[regime](instrument.ticker, instrument.stated_amount, lenient,
                                        instrument.calendar, lo - pad, hi + pad)
        out.extend(o for o in candidates
                   if o.window_start >= effective and o.window_end < nxt
                   and o.window_end >= start and o.window_start <= end)
    for o in out:
        if o.rate.is_nan():
            rate_on(o.window_start)  # raises with the instrument and date
    return sorted(out, key=lambda o: (o.record_date, o.pay_date))
