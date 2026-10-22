"""Offline sourced replay; approval remains an explicit scenario.

With --from/--to or --next-days, stdout lists only the rows whose payment date falls in
that window (as CSV); the full outputs are still written and the run summary goes to stderr.
"""
import argparse
import csv
import json
import sys
from dataclasses import asdict
from datetime import date, timedelta
from pathlib import Path

from .engine import replay
from .seed import LEDGER_START, build_events, write_jsonl
from .reconcile import run as reconcile

AS_OF = date(2026, 10, 21)
SCHEDULE_FIELDS = ('ticker', 'currency', 'record_date', 'payment_date', 'regime', 'per_share',
                   'declared_per_share', 'record_shares', 'amount', 'model_settlement',
                   'status', 'basis', 'source', 'payment_form',
                   'share_change_since_prior_record', 'share_change_basis', 'share_change_sources')
WINDOW_FIELDS = ('ticker', 'currency', 'record_date', 'payment_date', 'record_shares', 'amount',
                 'status', 'basis', 'payment_form')


def payment_form(instrument, rec) -> str:
    """cash, stock, cash_and_stock or election_unknown, from the terms and any declaration."""
    if not instrument.stock_payment_allowed:
        return 'cash'                                # terms permit cash dividends only
    if rec.declaration is None:
        return 'election_unknown'                    # STRK: cash or Class A stock at the company's election
    fraction = rec.declaration.stock_fraction        # seeded declarations come from cash declaration tables
    return 'cash' if fraction == 0 else 'stock' if fraction == 1 else 'cash_and_stock'


def share_changes(events, ticker, after, through):
    """Net issuance minus buybacks dated in (after, through], with the filings that report them."""
    picked = [e for e in events if e.ticker == ticker and e.kind in ('issuance', 'buyback')
              and after < e.date <= through]
    net = sum(e.shares if e.kind == 'issuance' else -e.shares for e in picked)
    buybacks = sum(e.kind == 'buyback' for e in picked)
    issues = len(picked) - buybacks
    if not picked:
        basis = 'no reported share change'
    else:
        basis = (f'{buybacks} repurchase and {issues} ATM sale periods in weekly 8-Ks; '
                 'each dated at period end (assumption)')
    return net, basis, ';'.join(dict.fromkeys(e.source_url for e in picked))


def schedule_rows(events, led, end):
    rows = []
    for ticker, tl in led.tickers.items():
        ins = tl.instrument
        previous = LEDGER_START
        for rec in tl.obligations:
            o = rec.obligation
            if o.record_date > end:
                continue
            net, basis, sources = share_changes(events, ticker, previous, o.record_date)
            previous = o.record_date
            rows.append(dict(ticker=ticker, currency=ins.currency,
                             record_date=str(o.record_date), payment_date=str(rec.pay_date),
                             regime=o.regime, per_share=str(o.per_share), declared_per_share=str(rec.per_share),
                             record_shares=rec.record_shares, amount=str(rec.amount),
                             model_settlement=str(rec.paid), status=rec.status, basis=rec.basis,
                             source=rec.declaration.source_url if rec.declaration else ';'.join(ins.sources),
                             payment_form=payment_form(ins, rec),
                             share_change_since_prior_record=net, share_change_basis=basis,
                             share_change_sources=sources))
    return rows


def window(args, parser):
    if args.next_days is not None:
        if args.start or args.stop:
            parser.error('--next-days cannot be combined with --from/--to')
        if args.next_days < 1:
            parser.error('--next-days must be at least 1')
        return AS_OF + timedelta(days=1), AS_OF + timedelta(days=args.next_days)
    if args.start is None and args.stop is None:
        return None
    start, stop = args.start or LEDGER_START, args.stop or date.max
    if start > stop:
        parser.error('--from must be on/before --to')
    return start, stop


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--scenario', choices=['current', 'approved'], default='current')
    parser.add_argument('--end', type=date.fromisoformat, default=date(2027, 3, 31),
                        help='last record date to replay (default 2027-03-31)')
    parser.add_argument('--out', type=Path, default=Path('results/current'))
    parser.add_argument('--from', dest='start', type=date.fromisoformat,
                        help='print rows with payment date on/after this ISO date')
    parser.add_argument('--to', dest='stop', type=date.fromisoformat,
                        help='print rows with payment date on/before this ISO date')
    parser.add_argument('--next-days', type=int,
                        help=f'print rows paid in the N days after the {AS_OF} financial cutoff')
    args = parser.parse_args()
    if args.end < LEDGER_START:
        parser.error('end must be on/after 2026-06-30')
    span = window(args, parser)
    events = build_events(args.scenario)
    led = replay(events, LEDGER_START, args.end, as_of=AS_OF)
    args.out.mkdir(parents=True, exist_ok=True)
    write_jsonl(events, args.out / 'events.jsonl')
    rows = schedule_rows(events, led, args.end)
    with (args.out / 'schedule.csv').open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=SCHEDULE_FIELDS)
        w.writeheader()
        w.writerows(rows)
    summary = {'as_of': str(AS_OF), 'scenario': args.scenario,
               'status': 'Projected payments and assumed settlement of declarations, not bank evidence',
               'opening_share_date': str(LEDGER_START), 'events': len(events),
               'ending_state': {t: asdict(tl.days[-1]) for t, tl in led.tickers.items()},
               'warnings': led.warnings}
    (args.out / 'summary.json').write_text(json.dumps(summary, indent=2, default=str) + '\n')
    checks = reconcile(args.out)
    report = json.dumps({'scenario': args.scenario, 'events': len(events), 'schedule_rows': len(rows),
                         'reconciliation_matches': sum(c.within for c in checks),
                         'reconciliation_checks': len(checks), 'out': str(args.out)}, indent=2)
    if span is None:
        print(report)
        return
    print(report, file=sys.stderr)
    picked = sorted((r for r in rows if span[0] <= date.fromisoformat(r['payment_date']) <= span[1]),
                    key=lambda r: (r['payment_date'], r['ticker'], r['record_date']))
    w = csv.DictWriter(sys.stdout, fieldnames=WINDOW_FIELDS, extrasaction='ignore', lineterminator='\n')
    w.writeheader()
    w.writerows(picked)
    if span[1] != date.max and span[1] > args.end:
        print(f'note: rows stop at record date {args.end}; raise --end to see later payments', file=sys.stderr)


if __name__ == '__main__':
    main()
