"""Build the event set from the cached filings in data/raw/.

Opening balances come from the 10-Q (shares as of 2026-06-30). Buybacks and ATM sales come
from the weekly 8-Ks, STRC rates and declarations from the 8-Ks, and the regime change from
the 2026-10-05 proxy. Each event carries its source URL and the filing date.

Assumptions (labelled on the events and in docs/assumptions.md):
  * A buyback reported for a period is dated at the period's last day ("end") by default.
    `buyback_dating="start"` dates it at the first day instead; the two bound the share
    count on any record date inside the period.
  * scenario="approved" adds the proposed regime changes, as if the 2026-10-28 vote passes and
    the amended certificates take effect on the filed dates. scenario="rejected" leaves the
    current schedules in place.
"""
from __future__ import annotations

import datetime as dt
import json
import pathlib
import re

from . import filings as F
from .events import Event
from .fetch import RAW
from .schedule import QUARTER_ENDS
from .terms import PROPOSED_DAILY_EFFECTIVE, PROXY

LEDGER_START = dt.date(2026, 6, 30)
DAILY_DECLARATION = RAW / "edgar" / "8k" / "2026-10-16-000119312526423400.htm"  # 8-K dated 2026-10-15
VOTE_NOTE = "assumes Proposal 1 passes at the 2026-10-28 special meeting (vote pending as of 2026-10-21)"


def _meta(path: pathlib.Path) -> dict:
    return json.loads(path.with_name(path.name + ".meta.json").read_text())


def _filing_date(path: pathlib.Path) -> str:
    m = re.match(r"(\d{4}-\d{2}-\d{2})", path.name)
    return m.group(1) if m else _meta(path)["fetched_utc"][:10]


def weekly_paths() -> list[pathlib.Path]:
    return sorted((RAW / "edgar" / "8k").glob("*.htm"))


def record_date_for(row: F.DeclaredRow) -> dt.date:
    """Map a declared 'period ending' row to the record date of that obligation."""
    if row.period == "quarter":
        assert (row.period_end.month, row.period_end.day) in QUARTER_ENDS
        return row.period_end.replace(day=15)
    if row.period == "semi-monthly":
        window_start = row.period_end.replace(day=1 if row.period_end.day == 15 else 16)
        return window_start - dt.timedelta(days=1)
    raise ValueError(f"no record-date rule for {row.period} periods")


def build_events(scenario: str = "current", buyback_dating: str = "end",
                 start: dt.date = LEDGER_START) -> list[Event]:
    if scenario not in ("approved", "current", "rejected"):
        raise ValueError("scenario must be current, approved or rejected")
    if buyback_dating not in ("start", "end"):
        raise ValueError("buyback_dating must be start or end")
    events: list[Event] = []

    tenq = RAW / "edgar" / "10q-20260630.htm"
    for ticker, shares in F.tenq_shares_issued(tenq.read_bytes()).items():
        events.append(Event(f"open-{ticker}-2026-06-30", "opening_balance", ticker, start, _meta(tenq)["url"],
                            "2026-08-03", "shares issued and outstanding at 2026-06-30 per 10-Q Note 10",
                            shares=shares))

    rates: dict[dt.date, Event] = {}
    for path in weekly_paths():
        raw = path.read_bytes()
        url, filed = _meta(path)["url"], _filing_date(path)
        week = F.weekly_update(raw)
        for table in week.tables if week else []:
            if table.end < start:
                continue
            for ticker, n in table.shares.items():
                if not n:
                    continue
                kind = "buyback" if table.kind == "repurchase" else "issuance"
                day = table.end if buyback_dating == "end" else table.start
                events.append(Event(f"{kind}-{ticker}-{table.start}-{table.end}", kind, ticker, day, url, filed,
                                    f"{table.kind} {table.start}..{table.end}; dated at period {buyback_dating} "
                                    "(assumption)", shares=n))
        for first_day, rate, sentence in F.rate_announcements(raw):
            if first_day not in rates:
                rates[first_day] = Event(f"rate-STRC-{first_day}", "rate_reset", "STRC", first_day, url, filed,
                                         sentence[:200], rate=rate)
        declared_on = F.declaration_date(raw)
        for row in F.declaration_rows(raw):
            record = record_date_for(row)
            if record < start:
                continue
            conditional = row.ticker == "STRC" and row.period_end == dt.date(2026, 11, 15)
            events.append(Event(
                f"decl-{row.ticker}-{record}", "declaration", row.ticker, declared_on or dt.date.fromisoformat(filed),
                url, filed, f"{row.period} period ending {row.period_end}; {row.currency}",
                record_date=record, pay_date=row.period_end, per_share=row.per_share,
                condition="payable only if the daily-dividend amendments do not take effect" if conditional else ""))
    events.extend(rates.values())

    daily = DAILY_DECLARATION
    for record, pay, amount in F.daily_dividend_table(daily.read_bytes(), 2026):
        events.append(Event(f"decl-STRC-{record}-daily", "declaration", "STRC", dt.date(2026, 10, 15),
                            _meta(daily)["url"], "2026-10-16", "daily declaration, November 2026",
                            record_date=record, pay_date=pay, per_share=amount,
                            condition="payable only if the daily-dividend amendments are approved and "
                                      "effective by 2026-11-01 12:01 a.m. ET"))

    if scenario == "approved":
        for ticker, effective in PROPOSED_DAILY_EFFECTIVE.items():
            events.append(Event(f"regime-{ticker}-{effective}-daily", "regime_change", ticker, effective, PROXY,
                                "2026-10-05", VOTE_NOTE, regime="daily"))
    return [e for e in events if not (scenario != "approved" and (e.id.endswith("-daily") or e.id == "rate-STRC-2026-11-01"))]


def write_jsonl(events, path: pathlib.Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(e.to_json() + "\n" for e in sorted(events, key=lambda e: e.id)))
