"""Parsers for the cached primary sources in data/raw/.

Each parser takes the raw document (HTML or CSV) and returns plain values. The seed and
reconciliation modules attach the source URL and date from the cache sidecar.
"""
from __future__ import annotations

import csv
import datetime as dt
import html
import io
import re
from dataclasses import dataclass
from decimal import Decimal

TICKERS = ("STRF", "STRC", "STRE", "STRK", "STRD")
DATE_RE = r"(?:January|February|March|April|May|June|July|August|September|October|November|December) \d{1,2}, \d{4}"


def to_text(raw: bytes | str) -> str:
    """HTML to whitespace-normalised text on one line (tables become space-separated cells)."""
    s = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else raw
    s = re.sub(r"(?is)<(script|style).*?</\1>", " ", s)
    s = re.sub(r"<[^>]+>", " ", s)
    s = html.unescape(s).replace("\xa0", " ").replace("|", " ")
    return re.sub(r"\s+", " ", s)


def parse_date(text: str) -> dt.date:
    return dt.datetime.strptime(text.strip(), "%B %d, %Y").date()


def _number(text: str) -> int:
    return 0 if text.strip() in ("-", "—", "–") else int(text.replace(",", ""))


# ------------------------------------------------------------ weekly 8-Ks ----

@dataclass(frozen=True)
class PeriodTable:
    start: dt.date
    end: dt.date
    kind: str                    # "atm" (shares sold) or "repurchase" (shares repurchased)
    shares: dict[str, int]       # preferred shares by ticker


@dataclass(frozen=True)
class Funding:
    amount_usd: Decimal
    sentence: str
    includes_interest: bool


@dataclass(frozen=True)
class WeeklyUpdate:
    start: dt.date
    end: dt.date
    tables: list[PeriodTable]
    funding: list[Funding]       # amounts the 8-K says were used to fund preferred dividends

    def shares(self, kind: str) -> list[PeriodTable]:
        return [t for t in self.tables if t.kind == kind]


def weekly_update(raw) -> WeeklyUpdate | None:
    """Parse the weekly ATM / repurchase / USD Reserve update. None if the 8-K has none.

    Quarter-end weeks are split into two sub-periods, each with its own table.
    """
    text = to_text(raw)
    marks = list(re.finditer(rf"During Period ({DATE_RE}) to ({DATE_RE})", text))
    if not marks:
        return None
    tables = []
    for i, m in enumerate(marks):
        seg = text[m.end(): marks[i + 1].start() if i + 1 < len(marks) else len(text)]
        head = seg[:400]
        kind = "repurchase" if "Shares Repurchased" in head else "atm" if "Shares Sold" in head else None
        if kind is None:
            continue
        shares = {}
        for t in ("STRF", "STRC", "STRK", "STRD"):
            mm = re.search(rf"{t} Stock\s*(?:\(\d\))?\s+([\d,]+|-)\s", seg)
            if mm:
                shares[t] = _number(mm.group(1))
        tables.append(PeriodTable(parse_date(m.group(1)), parse_date(m.group(2)), kind, shares))
    start = min(parse_date(m.group(1)) for m in marks)
    end = max(parse_date(m.group(2)) for m in marks)
    for kind, verb in (("repurchase", "purchase any shares under its share repurchase"),
                       ("atm", "sell any shares under its at-the-market")):
        nothing = re.search(rf"between ({DATE_RE}) and ({DATE_RE}), Strategy did not {verb}", text)
        if nothing:
            tables.append(PeriodTable(parse_date(nothing.group(1)), parse_date(nothing.group(2)), kind,
                                      {t: 0 for t in ("STRF", "STRC", "STRK", "STRD")}))
    funding = []
    for mm in re.finditer(r"\$([\d.,]+) (million|billion)([^.;]{0,160}?fund[^.;]{0,30}?dividends[^.;]{0,120})", text):
        scale = Decimal(10) ** (6 if mm.group(2) == "million" else 9)
        funding.append(Funding(Decimal(mm.group(1).replace(",", "")) * scale, mm.group(0),
                               "interest" in mm.group(3)))
    return WeeklyUpdate(start, end, tables, funding)


# --------------------------------------------------------- declarations ----

@dataclass(frozen=True)
class DeclaredRow:
    ticker: str
    period: str            # "quarter", "semi-monthly", "monthly"
    period_end: dt.date
    currency: str          # "USD" or "EUR"
    per_share: Decimal


def declaration_rows(raw) -> list[DeclaredRow]:
    """Rows of the 'Cash Dividend Declaration' tables (ticker, period ending, amount)."""
    text = to_text(raw)
    rows = []
    pattern = (rf"\b({'|'.join(TICKERS)})\s+(Quarter|Semi-monthly period|Monthly period)\s*ending\s*"
               rf"({DATE_RE})\s*([$€])\s*([\d.]+)")
    for m in re.finditer(pattern, text.replace("ending", " ending ")):
        rows.append(DeclaredRow(m.group(1), m.group(2).split()[0].lower(), parse_date(m.group(3)),
                                "EUR" if m.group(4) == "€" else "USD", Decimal(m.group(5))))
    return rows


def declaration_date(raw) -> dt.date | None:
    m = re.search(rf"On ({DATE_RE}), the Company.s board of directors declared", to_text(raw))
    return parse_date(m.group(1)) if m else None


def daily_dividend_table(raw, year: int) -> list[tuple[dt.date, dt.date, Decimal]]:
    """(record date, payment date, cash per share) rows of the 2026-10-15 daily declaration."""
    text = to_text(raw)
    i = text.find("Cash Dividend Per Share")
    j = text.find("Total Attributable", i)
    chunk = text[i:j]
    rows = re.findall(r"([A-Z][a-z]+ \d{1,2}) ([A-Z][a-z]+ \d{1,2}) \$([\d.]+)", chunk)
    out = []
    for r, p, a in rows:
        record = parse_date(f"{r}, {year}")
        pay = parse_date(f"{p}, {year}")
        if pay < record:  # December record date paid in January
            pay = pay.replace(year=year + 1)
        out.append((record, pay, Decimal(a)))
    return sorted(out)


def daily_table_total(raw) -> Decimal:
    m = re.search(r"Total Attributable to [A-Za-z]+ \d{4} Record Dates \$([\d.]+)", to_text(raw))
    return Decimal(m.group(1))


def rate_announcements(raw) -> list[tuple[dt.date, Decimal, str]]:
    """STRC rate notices: (first day the rate applies, annual rate, sentence)."""
    text = to_text(raw)
    out = []
    for m in re.finditer(r"(?:maintain|increase|decrease|adjust)[^.]{0,140}regular dividend rate per annum[^.]{0,260}?"
                         rf"(?:on or after|commencing on or after) ({DATE_RE}),? (?:at|to) ([\d.]+)%", text):
        sentence = m.group(0)
        first = parse_date(m.group(1))
        if "record dates on or after" in sentence and first.day == 1:
            # Semi-monthly CoD: the first record date on/after the 1st is the 15th, which is the
            # record date of the period starting the 16th; the rate applies from that day.
            first = first.replace(day=16)
        out.append((first, Decimal(m.group(2)) / 100, sentence))
    m = re.search(rf"rate per annum on [^.]{{0,120}}for dividends with record dates from ({DATE_RE}) through "
                  rf"({DATE_RE}) will be ([\d.]+)%", text)
    if m:
        out.append((parse_date(m.group(1)), Decimal(m.group(3)) / 100, m.group(0)))
    return out


# ----------------------------------------------------------------- 10-Q ----

def tenq_shares_issued(raw) -> dict[str, int]:
    """'Shares Issued as of June 30, 2026' row of the preferred stock terms table."""
    text = to_text(raw)
    m = re.search(r"Shares Issued as of [A-Z][a-z]+ \d{1,2}, \d{4} ([\d,]+) ([\d,]+) ([\d,]+) ([\d,]+) ([\d,]+)", text)
    header = re.search(r"Trading Symbol (STR\w) (STR\w) (STR\w) (STR\w) (STR\w)", text)
    return {t: _number(n) for t, n in zip(header.groups(), m.groups())}


def tenq_cash_dividends_paid(raw) -> dict[str, tuple[int, int]]:
    """Cash dividends paid, in USD thousands: {ticker: (three months, six months)} for 2026."""
    text = to_text(raw)
    i = text.find("Cash Dividends Paid (in thousands)")
    chunk = text[i:i + 900]
    out = {}
    for t in TICKERS:
        m = re.search(rf"{t} Stock (?:\(1\) )?\$? ?([\d,]+) \$? ?(?:[\d,]+|—) \$? ?([\d,]+)", chunk)
        out[t] = (_number(m.group(1)), _number(m.group(2)))
    return out


# ------------------------------------------------------------------ ECB ----

def ecb_rates(raw) -> dict[dt.date, Decimal]:
    """ECB euro reference rates, USD per EUR, by date."""
    s = raw.decode() if isinstance(raw, bytes) else raw
    return {dt.date.fromisoformat(r["TIME_PERIOD"]): Decimal(r["OBS_VALUE"])
            for r in csv.DictReader(io.StringIO(s)) if r["OBS_VALUE"]}
