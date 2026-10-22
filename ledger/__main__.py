"""Offline sourced replay; approval remains an explicit scenario."""
import argparse
import csv
import json
from dataclasses import asdict
from datetime import date
from pathlib import Path

from .engine import replay
from .seed import LEDGER_START, build_events, write_jsonl
from .reconcile import run as reconcile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scenario', choices=['current', 'approved'], default='current')
    parser.add_argument('--end', type=date.fromisoformat, default=date(2027, 3, 31))
    parser.add_argument('--out', type=Path, default=Path('results/current'))
    args = parser.parse_args()
    if args.end < LEDGER_START:
        parser.error('end must be on/after 2026-06-30')
    events = build_events(args.scenario)
    led = replay(events, LEDGER_START, args.end, as_of=date(2026, 10, 21))
    args.out.mkdir(parents=True, exist_ok=True)
    write_jsonl(events, args.out / 'events.jsonl')
    rows = []
    for ticker, rec in led.payments():
        o = rec.obligation
        if o.record_date > args.end:
            continue
        rows.append(dict(ticker=ticker, currency=led.tickers[ticker].instrument.currency,
                         record_date=str(o.record_date), payment_date=str(rec.pay_date),
                         regime=o.regime, per_share=str(o.per_share), declared_per_share=str(rec.per_share),
                         record_shares=rec.record_shares, amount=str(rec.amount),
                         model_settlement=str(rec.paid), status=rec.status, basis=rec.basis,
                         source=rec.declaration.source_url if rec.declaration else ';'.join(led.tickers[ticker].instrument.sources)))
    with (args.out / 'schedule.csv').open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    summary = {'as_of': '2026-10-21', 'scenario': args.scenario,
               'status': 'Projected payments and assumed settlement of declarations, not bank evidence',
               'opening_share_date': str(LEDGER_START), 'events': len(events),
               'ending_state': {t: asdict(tl.days[-1]) for t, tl in led.tickers.items()},
               'warnings': led.warnings}
    (args.out / 'summary.json').write_text(json.dumps(summary, indent=2, default=str) + '\n')
    checks = reconcile(args.out)
    print(json.dumps({'scenario': args.scenario, 'events': len(events), 'schedule_rows': len(rows),
                      'reconciliation_matches': sum(c.within for c in checks),
                      'reconciliation_checks': len(checks), 'out': str(args.out)}, indent=2))


if __name__ == '__main__':
    main()
