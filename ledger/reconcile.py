"""Reconcile ledger amounts against figures Strategy reported.

Three kinds of check:
  1. per-share: the terms' computed amounts against declared amounts (8-K tables);
  2. quarter totals: ledger cash paid against the 10-Q's cash dividends paid (Q1, Q2 2026);
  3. weekly funding: ledger payments against the 8-K sentences that say how much was used
     to fund preferred dividends that week.

Weekly buybacks are reported per period, not per day, so each ledger figure that depends on a
record-date share count is shown as a range: buybacks dated at the period's start (fewest
shares) to its end (most shares).
"""
from __future__ import annotations

import datetime as dt
import json
from dataclasses import asdict, dataclass
from decimal import Decimal

from . import filings as F
from .engine import replay
from .events import Event
from .fetch import RAW
from .schedule import build_schedule
from .seed import DAILY_DECLARATION, LEDGER_START, _meta, build_events
from .terms import INSTRUMENTS, TENQ

D = Decimal
ECB_FILE = RAW / "ecb" / "eurusd-20260301-20261020.csv"


@dataclass
class Check:
    label: str
    source_url: str
    as_of: str
    reported: Decimal
    ledger_low: Decimal
    ledger_high: Decimal
    unit: str
    note: str = ""
    rounding_uncertainty: Decimal | None = None

    @property
    def within(self) -> bool:
        return self.ledger_low - self.tolerance <= self.reported <= self.ledger_high + self.tolerance

    @property
    def tolerance(self) -> Decimal:
        """Half a unit of the reported figure's last digit (rounding in the filing)."""
        if self.rounding_uncertainty is not None:
            return self.rounding_uncertainty
        exp = self.reported.as_tuple().exponent
        return D(5) * D(10) ** (exp - 1) if exp < 0 else D("0.5") * D(10) ** exp

    @property
    def delta(self) -> Decimal:
        """Reported minus the nearest ledger bound (0 when inside the range)."""
        if self.reported < self.ledger_low:
            return self.reported - self.ledger_low
        if self.reported > self.ledger_high:
            return self.reported - self.ledger_high
        return D(0)

    def row(self) -> dict:
        d = asdict(self)
        d.update(within=self.within, delta=self.delta)
        return {k: (str(v) if isinstance(v, Decimal) else v) for k, v in d.items()}


def ecb() -> dict[dt.date, Decimal]:
    return F.ecb_rates(ECB_FILE.read_bytes())


def ecb_on_or_before(rates, day: dt.date) -> Decimal:
    if not rates or day < min(rates):
        raise ValueError("no ECB observation on or before date")
    while day not in rates:
        day -= dt.timedelta(days=1)
    return rates[day]


# ------------------------------------------------------------ per share ----

def november_daily_table() -> tuple[list[dict], Check]:
    """Terms-computed STRC daily amounts and pay dates against the 2026-10-15 8-K table."""
    raw = DAILY_DECLARATION.read_bytes()
    table = F.daily_dividend_table(raw, 2026)
    ins = INSTRUMENTS["STRC"]
    sched = {o.record_date: o for o in build_schedule(
        ins, [(dt.date.min, "semimonthly"), (dt.date(2026, 11, 1), "daily")],
        lambda d: D("0.12"), dt.date(2026, 11, 1), dt.date(2026, 11, 30)) if o.regime == "daily"}
    rows = []
    for record, pay, amount in table:
        o = sched[record]
        rows.append({"record": record.isoformat(), "filed_pay": pay.isoformat(), "ledger_pay": o.pay_date.isoformat(),
                     "filed": str(amount), "ledger": str(o.per_share.quantize(D("0.0001")))})
    total = sum(o.per_share for o in sched.values())
    check = Check("STRC November 2026 daily dividends, total per share", _meta(DAILY_DECLARATION)["url"],
                  "2026-10-15", F.daily_table_total(raw), total, total, "USD per share",
                  f"{sum(r['filed'] == str(D(r['ledger']).quantize(D('0.01'))) and r['filed_pay'] == r['ledger_pay'] for r in rows)}"
                  f" of {len(rows)} rows match amount and pay date")
    return rows, check


# ---------------------------------------------------------- 10-Q totals ----

def tenq_quarter_checks() -> list[Check]:
    """Q1 and Q2 2026 cash paid for STRF, STRK, STRD, STRE (USD at the ECB rate on the pay date).

    Uses the 10-Q's 2026-06-30 share counts for both quarters (assumption: no change in the
    count between the record dates and quarter end for these four series).
    """
    raw = (RAW / "edgar" / "10q-20260630.htm").read_bytes()
    shares = F.tenq_shares_issued(raw)
    paid = F.tenq_cash_dividends_paid(raw)
    rates = ecb()
    out = []
    for quarter, pay_day, pick in (("Q1 2026", dt.date(2026, 3, 31), lambda t: paid[t][1] - paid[t][0]),
                                   ("Q2 2026", dt.date(2026, 6, 30), lambda t: paid[t][0])):
        start = pay_day.replace(day=1)
        events = [Event(f"open-{t}", "opening_balance", t, start, shares=shares[t])
                  for t in ("STRF", "STRK", "STRD", "STRE")]
        led = replay(events, start, pay_day, as_of=start)  # projection: amounts from the terms
        for t in ("STRF", "STRK", "STRD", "STRE"):
            rec = next(r for r in led.tickers[t].obligations if r.pay_date == pay_day)
            amount = rec.paid
            note = f"{rec.per_share} per share x {rec.record_shares:,} shares"
            if t == "STRE":
                fx = ecb_on_or_before(rates, pay_day)
                amount = amount * fx
                note += f"; EUR {rec.paid:,.0f} x ECB {fx} on {pay_day} (the 10-Q uses the rate at payment)"
            out.append(Check(f"{t} cash dividends paid {quarter}, USD thousands", TENQ, "2026-08-03",
                             D(pick(t)), (amount / 1000), (amount / 1000), "USD thousands", note, D(1) if quarter == "Q1 2026" else D("0.5")))
    return out


# --------------------------------------------------------- weekly funding ----

FUNDING_MAP = [
    # (8-K file stem prefix, tickers and nominal pay dates the sentence funds, note)
    ("2026-08-03", [("STRC", dt.date(2026, 7, 31))], "bitcoin sale proceeds used to fund dividends"),
    ("2026-08-17", [("STRC", dt.date(2026, 8, 15))], "MSTR sale proceeds used to fund STRC dividends; "
                                                     "Aug 15 is a Saturday, paid Aug 17"),
    ("2026-08-31", [("STRC", dt.date(2026, 8, 31))], "MSTR sale proceeds used to fund STRC dividends"),
    ("2026-09-21", [("STRC", dt.date(2026, 9, 15))], "USD Reserve; figure includes debt interest, not modeled"),
    ("2026-09-28", [("STRE", dt.date(2026, 9, 30))], "USD Reserve; STRE funded ahead of the 2026-09-30 euro payment"),
    ("2026-10-05", [(t, dt.date(2026, 9, 30)) for t in ("STRF", "STRC", "STRK", "STRD")],
     "USD Reserve; figure includes debt interest, not modeled"),
    ("2026-10-19", [("STRC", dt.date(2026, 10, 15))], "USD Reserve"),
]


def weekly_funding_checks() -> list[Check]:
    end = dt.date(2026, 10, 21)
    ledgers = {d: replay(build_events("approved", d), LEDGER_START, end, as_of=end) for d in ("start", "end")}
    rates = ecb()
    paths = {p.name[:10]: p for p in (RAW / "edgar" / "8k").glob("*.htm") if F.weekly_update(p.read_bytes())}
    out = []
    for prefix, targets, note in FUNDING_MAP:
        path = paths[prefix]
        week = F.weekly_update(path.read_bytes())
        (funding,) = week.funding
        totals = {}
        for dating, led in ledgers.items():
            total = D(0)
            for ticker, nominal in targets:
                rec = next(r for r in led.tickers[ticker].obligations if r.obligation.nominal_pay_date == nominal)
                amount = rec.paid
                if ticker == "STRE":
                    lo, hi = (min(v for k, v in rates.items() if week.start <= k <= week.end),
                              max(v for k, v in rates.items() if week.start <= k <= week.end))
                    amount = amount * (lo if dating == "start" else hi)
                total += amount
            totals[dating] = total / 10**6
        label = f"{', '.join(sorted({t for t, _ in targets}))} dividends funded {week.start}..{week.end}, USD millions"
        if any(t == "STRE" for t, _ in targets):
            note += "; range uses the week's lowest and highest ECB EUR/USD"
        out.append(Check(label, _meta(path)["url"], prefix, funding.amount_usd / 10**6,
                         min(totals.values()), max(totals.values()), "USD millions",
                         note + ("" if not funding.includes_interest else "; reported figure includes interest")))
    return out


def declared_vs_terms() -> list[Check]:
    """Every seeded declaration's per-share amount against the amount the terms compute."""
    led = replay(build_events("approved"), LEDGER_START, dt.date(2026, 12, 31), as_of=dt.date(2026, 10, 21))
    out = []
    for ticker, tl in led.tickers.items():
        for rec in tl.obligations:
            if rec.declaration is None:
                continue
            o = rec.obligation
            out.append(Check(f"{ticker} record {o.record_date} declared per share", rec.declaration.source_url,
                             rec.declaration.as_of, rec.declaration.per_share, o.per_share, o.per_share,
                             "per share (instrument currency)", o.regime))
    return out


def run(write_to=None) -> list[Check]:
    rows, nov = november_daily_table()
    checks = [nov] + tenq_quarter_checks() + weekly_funding_checks()
    if write_to is not None:
        write_to.mkdir(parents=True, exist_ok=True)
        (write_to / "reconciliation.json").write_text(json.dumps(
            {"checks": [c.row() for c in checks], "november_daily_rows": rows,
             "declared_vs_terms": [c.row() for c in declared_vs_terms()]}, indent=1) + "\n")
    return checks
