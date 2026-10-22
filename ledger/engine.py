"""Replay events into a per-instrument, per-day ledger.

State is a pure function of (events, start, end, as_of). Events are ordered by a fixed
key, so the input order does not matter, and ids must be unique.

Day processing order (all at close of business):
  1. share events dated that day (opening balance, issuance, buyback)
  2. record dates that day fix the entitlement: per-share amount x shares outstanding
  3. compounding dates that day roll arrears tranches forward
  4. payment dates that day settle: payments go to the oldest arrears first, then to the
     current dividend; any shortfall becomes arrears (cumulative) or is forfeited (STRD)

Days after `as_of` are a projection: an obligation with no declaration is assumed to be
declared and paid at the amount the terms give, unless a skip event says otherwise.
Without a payment event, a settled obligation has status "assumed_settled", never "paid".
"""
from __future__ import annotations

import datetime as dt
from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal

from .calendars import ONE_DAY, days_30_360, last_day_of_month
from .events import Event, EventLog
from .schedule import Obligation, build_schedule
from .terms import INSTRUMENTS, STEP_UP_CAP, STEP_UP_INCREMENT, Instrument

ZERO = Decimal(0)
KIND_ORDER = {"opening_balance": 0, "regime_change": 1, "rate_reset": 2, "issuance": 3, "buyback": 4,
              "declaration": 5, "skip": 6, "payment": 7}


def event_sort_key(e: Event):
    return (e.ticker, e.date, KIND_ORDER[e.kind], e.id)


# ---------------------------------------------------------------- arrears ----

def is_compounding_date(ins: Instrument, day: dt.date) -> bool:
    if ins.ticker == "STRC":                       # semi-monthly: the 15th and the month end
        return day.day == 15 or day == last_day_of_month(day)
    return (day.month, day.day) in {(3, 31), (6, 30), (9, 30), (12, 31)}


def periods_per_year(ins: Instrument) -> int:
    return 24 if ins.ticker == "STRC" else 4


@dataclass
class Tranche:
    """An unpaid cumulative dividend and the compounded dividends on it."""
    record_date: dt.date
    anchor: dt.date            # first compounding date on/after the missed nominal payment date
    balance: Decimal           # value at `since`
    since: dt.date             # last compounding date (or anchor, or last partial payment)
    periods: int = 0           # compounding periods completed

    def rate(self, ins: Instrument, base_rate: Decimal) -> Decimal:
        if ins.compounding == "step_up":
            return min(base_rate + STEP_UP_INCREMENT * (self.periods + 1), STEP_UP_CAP)
        return base_rate

    def value(self, ins: Instrument, base_rate: Decimal, day: dt.date) -> Decimal:
        """Balance plus compounded dividends accrued since the last compounding date."""
        if day <= self.since or day < self.anchor:
            return self.balance
        start = max(self.since, self.anchor)
        if ins.ticker == "STRC":
            # deemed 15-day periods; pro-rate the open period by calendar days
            period_days = 15
            elapsed = min((day - start).days, period_days)
        else:
            period_days = 90
            elapsed = min(days_30_360(start, day), period_days)
        frac = Decimal(elapsed) / period_days
        return self.balance * (1 + self.rate(ins, base_rate) / periods_per_year(ins) * frac)

    def compound(self, ins: Instrument, base_rate: Decimal, day: dt.date) -> None:
        if day <= self.anchor or day <= self.since:
            return
        self.balance = self.value(ins, base_rate, day)
        self.since = day
        self.periods += 1


def compounding_anchor(ins: Instrument, nominal_pay: dt.date) -> dt.date:
    day = nominal_pay
    while not is_compounding_date(ins, day):
        day += ONE_DAY
    return day


# ------------------------------------------------------------------ state ----

@dataclass
class ObligationRecord:
    obligation: Obligation
    status: str = "scheduled"        # scheduled, fixed, paid, assumed_settled, partial, missed,
    #                                  declared_unpaid, forfeited. "paid" needs a payment event;
    #                                  "assumed_settled" is the model's settlement assumption.
    basis: str = ""                  # declared, projected, terms
    per_share: Decimal = ZERO        # amount used (declared amount if declared)
    record_shares: int | None = None
    amount: Decimal = ZERO           # per_share x record_shares, in the instrument currency
    paid: Decimal = ZERO
    paid_stock: Decimal = ZERO       # STRK: part of `paid` delivered as Class A stock
    declaration: Event | None = None
    payment: Event | None = None
    skipped: bool = False
    pay_date: dt.date | None = None  # declared date if one was stated, else the terms' date


@dataclass
class DayState:
    date: dt.date
    ticker: str
    shares: int
    rate: Decimal
    regime: str
    accrued: Decimal          # earned on windows not yet paid
    declared_unpaid: Decimal  # record date passed, declared, payment date not reached
    paid_cum: Decimal         # cash and stock paid since the ledger start
    paid_stock_cum: Decimal
    arrears: Decimal          # unpaid cumulative dividends incl. compounded dividends
    forfeited_cum: Decimal    # non-cumulative dividends not declared (STRD)
    overdue_declared: Decimal = ZERO  # STRD declared but unpaid; not forfeited


@dataclass
class TickerLedger:
    instrument: Instrument
    obligations: list[ObligationRecord]
    days: list[DayState]
    tranches: list[Tranche]
    warnings: list[str] = field(default_factory=list)


@dataclass
class Ledger:
    tickers: dict[str, TickerLedger]
    start: dt.date
    end: dt.date
    as_of: dt.date

    def day(self, ticker: str, day: dt.date) -> DayState:
        tl = self.tickers[ticker]
        return tl.days[(day - self.start).days]

    def payments(self):
        """All obligations with a payment date in the ledger range, as (ticker, record)."""
        for tl in self.tickers.values():
            for rec in tl.obligations:
                yield tl.instrument.ticker, rec

    @property
    def warnings(self) -> list[str]:
        return [w for tl in self.tickers.values() for w in tl.warnings]


def _rate_lookup(ins: Instrument, resets: list[Event]):
    if ins.fixed_rate is not None:
        if resets:
            raise ValueError(f"{ins.ticker} has a fixed rate; rate_reset events are invalid")
        return lambda day: ins.fixed_rate
    points = sorted((e.date, e.rate) for e in resets)

    def rate_on(day: dt.date) -> Decimal:
        rate = None
        for eff, r in points:
            if eff <= day:
                rate = r
            else:
                break
        if rate is None:
            raise ValueError(f"no {ins.ticker} rate known for {day}; add a rate_reset event")
        return rate
    return rate_on


def replay(events, start: dt.date, end: dt.date, as_of: dt.date | None = None,
           instruments: dict[str, Instrument] = INSTRUMENTS) -> Ledger:
    if start > end:
        raise ValueError("start must not follow end")
    log = EventLog()
    log.extend(events)                       # raises DuplicateEventError on a repeated id
    as_of = end if as_of is None else as_of
    by_ticker: dict[str, list[Event]] = defaultdict(list)
    for e in sorted(log, key=event_sort_key):
        if e.ticker not in instruments:
            raise ValueError(f"{e.id}: unknown ticker {e.ticker}")
        by_ticker[e.ticker].append(e)
    return Ledger({t: _replay_ticker(instruments[t], by_ticker.get(t, []), start, end, as_of)
                   for t in instruments if t in by_ticker}, start, end, as_of)


def _replay_ticker(ins: Instrument, events: list[Event], start, end, as_of) -> TickerLedger:
    warnings: list[str] = []
    of = lambda kind: [e for e in events if e.kind == kind]
    openings = of("opening_balance")
    if len(openings) != 1 or openings[0].date != start:
        raise ValueError(f"{ins.ticker}: exactly one opening balance dated at replay start is required")
    regimes = [(dt.date.min, ins.base_regime)] + sorted((e.date, e.regime) for e in of("regime_change"))
    rate_on = _rate_lookup(ins, of("rate_reset"))
    schedule = [o for o in build_schedule(ins, regimes, rate_on, start, end) if o.record_date >= start]
    records = {o.record_date: ObligationRecord(o) for o in schedule}

    for kind, attr in (("declaration", "declaration"), ("payment", "payment")):
        for e in of(kind):
            rec = records.get(e.record_date)
            if rec is None:
                warnings.append(f"{ins.ticker} {kind} {e.id}: no obligation with record date "
                                f"{e.record_date} under the replayed regime ({e.condition or 'unconditional'})")
                continue
            if getattr(rec, attr) is not None:
                raise ValueError(f"{ins.ticker}: two {kind}s for record date {e.record_date}")
            setattr(rec, attr, e)
            if kind == "declaration" and e.pay_date not in (None, rec.obligation.pay_date,
                                                             rec.obligation.nominal_pay_date):
                warnings.append(f"{ins.ticker} {e.id}: declared pay date {e.pay_date} differs from "
                                f"terms ({rec.obligation.pay_date}); using the declared date")
    for e in of("skip"):
        if e.record_date in records:
            records[e.record_date].skipped = True
        else:
            warnings.append(f"{ins.ticker} skip {e.id}: no obligation with record date {e.record_date}")

    pay_on = defaultdict(list)
    declared_on = defaultdict(list)
    starts = defaultdict(list)
    for rec in records.values():
        decl = rec.declaration
        declared_other = decl and decl.pay_date and decl.pay_date != rec.obligation.nominal_pay_date
        rec.pay_date = decl.pay_date if declared_other else rec.obligation.pay_date
        if decl is not None:
            if decl.date > rec.pay_date:
                raise ValueError(f"{ins.ticker} {decl.id}: declaration date follows payment date; "
                                 "late declarations are outside v1")
            declared_on[decl.date].append(rec)
        if rec.payment is not None and rec.payment.date != rec.pay_date:
            raise ValueError(f"{ins.ticker} {rec.payment.id}: payment date must equal {rec.pay_date}; "
                             "early/late settlement is outside v1")
        pay_on[rec.pay_date].append(rec)
        starts[max(rec.obligation.window_start, start)].append(rec)
    open_recs: list[ObligationRecord] = []

    share_events = defaultdict(list)
    for e in events:
        if e.kind in ("opening_balance", "issuance", "buyback"):
            share_events[e.date].append(e)

    shares: int | None = None
    tranches: list[Tranche] = []
    days: list[DayState] = []
    paid_cum = paid_stock_cum = forfeited_cum = ZERO
    day = start
    while day <= end:
        for e in share_events.get(day, []):
            if e.kind == "opening_balance":
                shares = e.shares
            elif shares is None:
                raise ValueError(f"{ins.ticker} {e.id}: share event before an opening balance")
            else:
                shares += e.shares if e.kind == "issuance" else -e.shares
                if shares < 0:
                    raise ValueError(f"{ins.ticker} {e.id}: buyback exceeds shares outstanding")

        rec = records.get(day)
        if rec is not None:
            if shares is None:
                raise ValueError(f"{ins.ticker}: record date {day} before an opening balance")
            if rec.declaration is not None and rec.declaration.date <= day:
                rec.per_share, rec.basis = rec.declaration.per_share, "declared"
            else:
                rec.per_share = rec.obligation.per_share
                rec.basis = "projected" if rec.obligation.pay_date > as_of else "terms"
            rec.record_shares = shares
            rec.amount = rec.per_share * shares
            rec.status = "fixed"

        for rec in declared_on.get(day, []):
            if rec.record_shares is not None:
                rec.per_share, rec.basis = rec.declaration.per_share, "declared"
                rec.amount = rec.per_share * rec.record_shares

        if is_compounding_date(ins, day):
            for t in tranches:
                t.compound(ins, rate_on(day), day)

        for rec in pay_on.get(day, []):
            if rec.status != "fixed":
                continue
            projected = day > as_of
            if rec.skipped:
                per_share_paid = ZERO
            elif rec.payment is not None and rec.payment.per_share is not None:
                per_share_paid = rec.payment.per_share
            elif rec.declaration is not None or projected:
                per_share_paid = rec.per_share
            else:
                per_share_paid = ZERO                    # pay date passed with no declaration
            cash = per_share_paid * rec.record_shares
            stock_frac = rec.declaration.stock_fraction if rec.declaration else ZERO
            if stock_frac and not ins.stock_payment_allowed:
                raise ValueError(f"{ins.ticker} cannot pay dividends in stock")
            # oldest arrears first (cumulative series only)
            remaining = cash
            if ins.cumulative:
                for t in tranches:
                    if remaining <= 0:
                        break
                    owed = t.value(ins, rate_on(day), day)
                    pay_now = min(owed, remaining)
                    t.balance, t.since, remaining = owed - pay_now, day, remaining - pay_now
                tranches = [t for t in tranches if t.balance > Decimal("1e-9")]
            applied_current = min(remaining, rec.amount) if ins.cumulative else remaining
            if ins.cumulative and remaining > rec.amount:
                warnings.append(f"{ins.ticker} {day}: payment exceeds all amounts owed by {remaining - rec.amount}")
            shortfall = rec.amount - applied_current
            rec.paid = cash
            rec.paid_stock = cash * stock_frac
            paid_cum += cash
            paid_stock_cum += rec.paid_stock
            if shortfall > 0 and rec.obligation.regime == "daily":
                raise ValueError("daily-regime arrears are outside v1; daily scenario supports paid schedules only")
            if shortfall <= 0:
                rec.status = "paid" if rec.payment is not None else "assumed_settled"
            elif ins.cumulative:
                rec.status = "partial" if applied_current > 0 else "missed"
                anchor = compounding_anchor(ins, rec.obligation.nominal_pay_date)
                tranches.append(Tranche(rec.obligation.record_date, anchor, shortfall, anchor))
            elif rec.declaration is not None:
                rec.status = "declared_unpaid"
            else:
                rec.status = "forfeited"
                forfeited_cum += shortfall

        rate = rate_on(day)
        regime = [r for eff, r in regimes if eff <= day][-1]
        accrued = declared_unpaid = ZERO
        open_recs = [r for r in open_recs + starts.get(day, []) if day < r.pay_date]
        for r in open_recs:
            per_share = r.per_share if r.record_shares is not None else r.obligation.per_share
            entitlement_shares = r.record_shares if r.record_shares is not None else (shares or 0)
            accrued += _accrued_fraction(r.obligation, day) * per_share * entitlement_shares
            if r.basis == "declared" and r.record_shares is not None:
                declared_unpaid += r.amount
        arrears = sum((t.value(ins, rate, day) for t in tranches), ZERO)
        days.append(DayState(day, ins.ticker, shares or 0, rate, regime, accrued, declared_unpaid,
                             paid_cum, paid_stock_cum, arrears, forfeited_cum,
                             sum((r.amount - r.paid for r in records.values() if r.status == "declared_unpaid"), ZERO)))
        day += ONE_DAY

    return TickerLedger(ins, sorted(records.values(), key=lambda r: r.obligation.record_date),
                        days, tranches, warnings)


def _accrued_fraction(o: Obligation, day: dt.date) -> Decimal:
    if day >= o.window_end:
        return Decimal(1)
    if o.regime == "quarterly":
        return Decimal(days_30_360(o.window_start, day + ONE_DAY)) / days_30_360(o.window_start,
                                                                                o.window_end + ONE_DAY)
    return Decimal((day - o.window_start).days + 1) / ((o.window_end - o.window_start).days + 1)
