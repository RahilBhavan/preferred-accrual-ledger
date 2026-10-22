"""Ledger events and an append-only JSONL event store.

Every event has a unique id, a ticker, a date, a source URL and the as-of date of that
source. The ledger state is a pure function of the event set (see engine.replay).
"""
from __future__ import annotations

import datetime as dt
import json
import pathlib
from dataclasses import asdict, dataclass, field, fields
from decimal import Decimal

KINDS = ("opening_balance", "issuance", "buyback", "rate_reset", "regime_change",
         "declaration", "payment", "skip")


@dataclass(frozen=True)
class Event:
    id: str
    kind: str
    ticker: str
    date: dt.date                 # the day the event takes effect (see each kind below)
    source_url: str = ""
    as_of: str = ""               # date of the source document
    note: str = ""
    # payload, used per kind:
    shares: int | None = None             # opening_balance, issuance, buyback: effective close of `date`
    rate: Decimal | None = None           # rate_reset: annual rate for accrual days on/after `date`
    regime: str | None = None             # regime_change: new regime for windows starting on/after `date`
    record_date: dt.date | None = None    # declaration, payment, skip: which obligation
    pay_date: dt.date | None = None       # declaration: stated payment date (checked against the terms)
    per_share: Decimal | None = None      # declaration: declared amount; payment: amount actually paid
    stock_fraction: Decimal = Decimal(0)  # declaration (STRK): share of the amount paid in Class A stock
    condition: str = ""                   # declaration: text of any contingency (display only)
    cash_usd: Decimal | None = None       # payment: reported USD cash, for reconciliation only

    def __post_init__(self):
        if not self.id or not self.ticker:
            raise ValueError("event id and ticker are required")
        if self.regime is not None and self.regime not in ("quarterly", "semimonthly", "daily"):
            raise ValueError("unknown regime")
        for name in ("rate", "per_share", "stock_fraction", "cash_usd"):
            value = getattr(self, name)
            if value is not None and (not value.is_finite() or value < 0):
                raise ValueError(f"{self.id}: invalid {name}")
        if self.stock_fraction > 1:
            raise ValueError("stock_fraction must be in [0,1]")
        if self.shares is not None and (not isinstance(self.shares, int) or isinstance(self.shares, bool)):
            raise ValueError("shares must be an integer")
        if self.kind not in KINDS:
            raise ValueError(f"unknown event kind {self.kind!r}")
        needs = {
            "opening_balance": ("shares",), "issuance": ("shares",), "buyback": ("shares",),
            "rate_reset": ("rate",), "regime_change": ("regime",),
            "declaration": ("record_date", "per_share"), "payment": ("record_date",),
            "skip": ("record_date",),
        }[self.kind]
        missing = [n for n in needs if getattr(self, n) is None]
        if missing:
            raise ValueError(f"{self.id}: {self.kind} needs {missing}")
        if self.shares is not None and self.shares < 0:
            raise ValueError(f"{self.id}: negative share count")

    def to_json(self) -> str:
        out = {}
        for k, v in asdict(self).items():
            if v is None or v == "" or (k == "stock_fraction" and v == 0):
                continue
            out[k] = v.isoformat() if isinstance(v, dt.date) else str(v) if isinstance(v, Decimal) else v
        return json.dumps(out, sort_keys=True)

    @classmethod
    def from_dict(cls, raw: dict) -> "Event":
        kw = {}
        types = {f.name: f.type for f in fields(cls)}
        for k, v in raw.items():
            if k not in types:
                raise ValueError(f"unknown field {k!r} in event {raw.get('id')}")
            t = str(types[k])
            if "dt.date" in t and v is not None:
                v = dt.date.fromisoformat(v)
            elif "Decimal" in t and v is not None:
                v = Decimal(str(v))
            kw[k] = v
        return cls(**kw)


class DuplicateEventError(ValueError):
    pass


@dataclass
class EventLog:
    """In-memory event set keyed by id. Adding an id twice raises DuplicateEventError."""
    events: dict[str, Event] = field(default_factory=dict)

    def add(self, event: Event) -> None:
        if event.id in self.events:
            raise DuplicateEventError(f"duplicate event id {event.id!r}")
        self.events[event.id] = event

    def extend(self, events) -> None:
        for e in events:
            self.add(e)

    def __iter__(self):
        return iter(self.events.values())

    def __len__(self):
        return len(self.events)


def load_jsonl(path: pathlib.Path) -> list[Event]:
    out = []
    for n, line in enumerate(path.read_text().splitlines(), 1):
        if line.strip():
            try:
                out.append(Event.from_dict(json.loads(line)))
            except (ValueError, TypeError) as exc:
                raise ValueError(f"{path}:{n}: {exc}") from exc
    return out


def append_jsonl(path: pathlib.Path, events) -> tuple[int, int]:
    """Append events not already stored. Identical re-appends are skipped (idempotent);
    a different event under an existing id raises DuplicateEventError. Returns (added, skipped)."""
    existing = {e.id: e for e in load_jsonl(path)} if path.exists() else {}
    added = skipped = 0
    lines = []
    for e in events:
        if e.id in existing:
            if existing[e.id] != e:
                raise DuplicateEventError(f"event id {e.id!r} already stored with different content")
            skipped += 1
            continue
        existing[e.id] = e
        lines.append(e.to_json())
        added += 1
    if lines:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a") as fh:
            fh.write("\n".join(lines) + "\n")
    return added, skipped
