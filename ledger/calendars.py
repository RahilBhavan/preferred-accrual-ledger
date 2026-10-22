"""Business-day calendars and the 30/360 day count used by the certificates.

USD series (STRF, STRC, STRK, STRD): "Business Day" means any day other than a
Saturday, a Sunday or a day on which the Federal Reserve Bank of New York is
authorized or required to close (proxy DEF 14A, 2026-10-05, p. 11).

STRE: a Business Day must be (a) open for general business in London, (b) not a
New York Fed closure and (c) a day on which T2 settles euro payments (STRE
certificate of designations, Exhibit 3.1 to the 8-K filed 2025-11-13).

Holiday rules are encoded from published rules, not fetched lists. They are
tested against known 2026-2027 dates; extend the tests before relying on other years.
"""
from __future__ import annotations

import datetime as dt
from functools import lru_cache

Date = dt.date
ONE_DAY = dt.timedelta(days=1)


def easter_sunday(year: int) -> Date:
    """Gregorian Easter (anonymous Gregorian algorithm)."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + c + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month, day = divmod(h + l - 7 * m + 114, 31)
    return Date(year, month, day + 1)


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> Date:
    """n-th given weekday (Mon=0) of a month; n=-1 means the last one."""
    if n > 0:
        first = Date(year, month, 1)
        return first + dt.timedelta(days=(weekday - first.weekday()) % 7 + 7 * (n - 1))
    nxt = Date(year + (month == 12), month % 12 + 1, 1)
    last = nxt - ONE_DAY
    return last - dt.timedelta(days=(last.weekday() - weekday) % 7)


@lru_cache(maxsize=None)
def fed_holidays(year: int) -> frozenset[Date]:
    """Days the Federal Reserve Bank of New York is closed.

    Fixed-date holidays falling on a Sunday are observed the next Monday. When one
    falls on a Saturday the Fed stays open the Friday before, so no day is added.
    """
    fixed = [Date(year, 1, 1), Date(year, 6, 19), Date(year, 7, 4), Date(year, 11, 11), Date(year, 12, 25)]
    days = {d + ONE_DAY if d.weekday() == 6 else d for d in fixed if d.weekday() != 5}
    days |= {
        _nth_weekday(year, 1, 0, 3),   # Martin Luther King Jr. Day
        _nth_weekday(year, 2, 0, 3),   # Washington's Birthday
        _nth_weekday(year, 5, 0, -1),  # Memorial Day
        _nth_weekday(year, 9, 0, 1),   # Labor Day
        _nth_weekday(year, 10, 0, 2),  # Columbus Day
        _nth_weekday(year, 11, 3, 4),  # Thanksgiving Day
    }
    return frozenset(days)


@lru_cache(maxsize=None)
def london_bank_holidays(year: int) -> frozenset[Date]:
    """England and Wales bank holidays by rule, with weekend substitute days."""
    easter = easter_sunday(year)
    days = {
        easter - 2 * ONE_DAY,           # Good Friday
        easter + ONE_DAY,               # Easter Monday
        _nth_weekday(year, 5, 0, 1),    # Early May bank holiday
        _nth_weekday(year, 5, 0, -1),   # Spring bank holiday
        _nth_weekday(year, 8, 0, -1),   # Summer bank holiday
    }
    new_year = Date(year, 1, 1)
    days.add(new_year + dt.timedelta(days={5: 2, 6: 1}.get(new_year.weekday(), 0)))
    christmas, boxing = Date(year, 12, 25), Date(year, 12, 26)
    if christmas.weekday() == 5:      # Sat, Sun -> Mon, Tue
        days |= {Date(year, 12, 27), Date(year, 12, 28)}
    elif christmas.weekday() == 4:    # Fri, Sat -> Fri, Mon
        days |= {christmas, Date(year, 12, 28)}
    elif christmas.weekday() == 6:    # Sun, Mon -> Tue, Mon
        days |= {boxing, Date(year, 12, 27)}
    else:
        days |= {christmas, boxing}
    return frozenset(days)


@lru_cache(maxsize=None)
def t2_closures(year: int) -> frozenset[Date]:
    """TARGET2/T2 closing days: New Year, Good Friday, Easter Monday, 1 May, 25 and 26 Dec."""
    easter = easter_sunday(year)
    return frozenset({Date(year, 1, 1), easter - 2 * ONE_DAY, easter + ONE_DAY,
                      Date(year, 5, 1), Date(year, 12, 25), Date(year, 12, 26)})


def is_business_day(day: Date, calendar: str = "USD") -> bool:
    if day.weekday() >= 5 or day in fed_holidays(day.year):
        return False
    if calendar == "USD":
        return True
    if calendar == "EUR":
        return day not in london_bank_holidays(day.year) and day not in t2_closures(day.year)
    raise ValueError(f"unknown calendar {calendar!r}")


def next_business_day(day: Date, calendar: str = "USD", strictly_after: bool = False) -> Date:
    """Following convention: the day itself if a business day, otherwise the next one."""
    day = day + ONE_DAY if strictly_after else day
    while not is_business_day(day, calendar):
        day += ONE_DAY
    return day


def days_30_360(start: Date, end: Date) -> int:
    """Days from start (inclusive) to end (exclusive) on a 360-day year of twelve 30-day months.

    Bond-basis (30/360 US without the February rule): a 31st start becomes the 30th; a 31st
    end becomes the 30th when the start is the 30th or 31st. Every full quarter from a
    quarter-end payment date is therefore exactly 90 days.
    """
    d1, d2 = start.day, end.day
    if d1 == 31:
        d1 = 30
    if d2 == 31 and d1 == 30:
        d2 = 30
    return 360 * (end.year - start.year) + 30 * (end.month - start.month) + (d2 - d1)


def last_day_of_month(day: Date) -> Date:
    nxt = Date(day.year + (day.month == 12), day.month % 12 + 1, 1)
    return nxt - ONE_DAY


def daterange(start: Date, end: Date):
    """Inclusive range of calendar days."""
    day = start
    while day <= end:
        yield day
        day += ONE_DAY
