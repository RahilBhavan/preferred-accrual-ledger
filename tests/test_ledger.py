import datetime as dt
import random
import tempfile
import unittest
from decimal import Decimal as D
from pathlib import Path

from ledger.calendars import is_business_day, next_business_day
from ledger.engine import Tranche, replay
from ledger.events import DuplicateEventError, Event, append_jsonl, load_jsonl
from ledger.reconcile import Check, november_daily_table
from ledger.schedule import build_schedule, daily_amounts
from ledger.seed import LEDGER_START, build_events
from ledger.terms import INSTRUMENTS

Date = dt.date.fromisoformat


def opening(ticker, shares=10):
    return Event('open-' + ticker, 'opening_balance', ticker, Date('2026-07-01'), shares=shares)


class LedgerTests(unittest.TestCase):
    def test_real_sources_all_five(self):
        events = build_events()
        self.assertEqual({e.ticker for e in events}, set(INSTRUMENTS))
        self.assertTrue(all(e.source_url and e.as_of for e in events))
        self.assertEqual(len(events), 37)

    def test_current_default(self):
        self.assertFalse(any(e.kind == 'regime_change' or e.id.endswith('-daily') for e in build_events()))
        self.assertFalse(any(e.id == 'rate-STRC-2026-11-01' for e in build_events()))

    def test_approval_is_explicit(self):
        events = build_events('approved')
        self.assertEqual(sum(e.kind == 'regime_change' for e in events), 4)
        self.assertFalse(any(e.ticker == 'STRE' and e.kind == 'regime_change' for e in events))

    def test_conditional_filed_schedule(self):
        rows, check = november_daily_table()
        self.assertEqual(len(rows), 30)
        self.assertTrue(check.within)
        self.assertTrue(all(D(r['filed']) == D(r['ledger']) and r['filed_pay'] == r['ledger_pay'] for r in rows))

    def test_daily_conserves_semimonthly_total(self):
        for n in range(1, 32):
            for r in (D('.08'), D('.10'), D('.115'), D('.12')):
                amounts = daily_amounts(D(100), r, n)
                self.assertLess(abs(sum(amounts) - 100 * r / 24), D('1e-25'))
                self.assertTrue(all(a >= 0 for a in amounts))
                self.assertTrue(all(a == a.quantize(D('.01')) for a in amounts[:-1]))

    def test_daily_bad_input(self):
        for n, r in ((0, D('.1')), (15, D('NaN')), (15, D('-.1'))):
            with self.assertRaises(ValueError):
                daily_amounts(D(100), r, n)

    def test_quarter_schedules_all_five(self):
        for t, ins in INSTRUMENTS.items():
            rows = build_schedule(ins, [(dt.date.min, ins.base_regime)], lambda d: ins.fixed_rate or D('.12'),
                                  Date('2026-07-01'), Date('2026-09-30'))
            rows = [r for r in rows if Date('2026-07-01') <= r.window_end <= Date('2026-09-30')]
            self.assertEqual(len(rows), 6 if t == 'STRC' else 1)
            self.assertTrue(all(is_business_day(r.pay_date, ins.calendar) for r in rows))
            self.assertTrue(all(r.record_date < r.pay_date for r in rows))

    def test_order_invariance(self):
        events = build_events()
        shuffled = events.copy()
        random.Random(6).shuffle(shuffled)
        a = replay(events, LEDGER_START, Date('2026-10-21'))
        b = replay(shuffled, LEDGER_START, Date('2026-10-21'))
        self.assertEqual(a, b)

    def test_duplicate_rejected(self):
        with self.assertRaises(DuplicateEventError):
            replay([opening('STRF')] * 2, Date('2026-07-01'), Date('2026-09-30'))

    def test_jsonl_restart_retry(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'events.jsonl'
            events = build_events()
            self.assertEqual(append_jsonl(path, events), (len(events), 0))
            self.assertEqual(append_jsonl(path, events), (0, len(events)))
            self.assertEqual(replay(load_jsonl(path), LEDGER_START, Date('2026-10-21')),
                             replay(events, LEDGER_START, Date('2026-10-21')))
            with self.assertRaises(DuplicateEventError):
                append_jsonl(path, [Event(events[0].id, 'opening_balance', 'STRF', LEDGER_START, shares=1)])

    def test_cumulative_vs_noncumulative(self):
        for t in ('STRF', 'STRE', 'STRK', 'STRD'):
            led = replay([opening(t)], Date('2026-07-01'), Date('2026-10-01'))
            state = led.tickers[t].days[-1]
            if t == 'STRD':
                self.assertEqual(state.arrears, 0)
                self.assertEqual(state.forfeited_cum, 25)
            else:
                self.assertGreater(state.arrears, 0)
                self.assertEqual(state.forfeited_cum, 0)

    def test_strd_declared_unpaid_not_forfeited(self):
        decl = Event('decl', 'declaration', 'STRD', Date('2026-08-01'),
                     record_date=Date('2026-09-15'), per_share=D('2.5'))
        skip = Event('skip', 'skip', 'STRD', Date('2026-09-30'), record_date=Date('2026-09-15'))
        s = replay([opening('STRD'), decl, skip], Date('2026-07-01'), Date('2026-10-01')).tickers['STRD'].days[-1]
        self.assertEqual(s.overdue_declared, 25)
        self.assertEqual(s.forfeited_cum, 0)
        self.assertEqual(s.arrears, 0)

    def test_entitlement_fixed_at_record(self):
        events = [opening('STRF'), Event('issue', 'issuance', 'STRF', Date('2026-09-16'), shares=100)]
        led = replay(events, Date('2026-07-01'), Date('2026-09-30'), as_of=Date('2026-07-01'))
        rec = next(r for r in led.tickers['STRF'].obligations if r.obligation.record_date == Date('2026-09-15'))
        self.assertEqual(rec.record_shares, 10)
        self.assertEqual(rec.paid, 25)

    def test_step_up_cap(self):
        t = Tranche(Date('2026-03-15'), Date('2026-03-31'), D(100), Date('2026-03-31'))
        ins = INSTRUMENTS['STRF']
        self.assertEqual(t.rate(ins, D('.1')), D('.11'))
        for year in range(2026, 2030):
            for month, day in ((6, 30), (9, 30), (12, 31)):
                t.compound(ins, D('.1'), dt.date(year, month, day))
                self.assertLessEqual(t.rate(ins, D('.1')), D('.18'))
        self.assertGreater(t.balance, 100)

    def test_regular_compounding(self):
        t = Tranche(Date('2026-03-15'), Date('2026-03-31'), D(100), Date('2026-03-31'))
        t.compound(INSTRUMENTS['STRK'], D('.08'), Date('2026-06-30'))
        self.assertEqual(t.balance, 102)

    def test_business_day_currencies(self):
        self.assertEqual(next_business_day(Date('2026-12-25'), 'USD'), Date('2026-12-28'))
        self.assertEqual(next_business_day(Date('2026-12-25'), 'EUR'), Date('2026-12-29'))

    def test_invalid_event_payloads(self):
        for payload in ({'rate': D('NaN')}, {'rate': D('-.1')}):
            with self.assertRaises(ValueError):
                Event('bad', 'rate_reset', 'STRC', LEDGER_START, **payload)
        with self.assertRaises(ValueError):
            Event('bad', 'opening_balance', 'STRF', LEDGER_START, shares=1.5)

    def test_unknown_ticker(self):
        with self.assertRaises(ValueError):
            replay([opening('BAD')], Date('2026-07-01'), Date('2026-09-30'))

    def test_overbuyback(self):
        with self.assertRaises(ValueError):
            replay([opening('STRF'), Event('buy', 'buyback', 'STRF', Date('2026-07-02'), shares=11)],
                   Date('2026-07-01'), Date('2026-09-30'))

    def test_invalid_scenario(self):
        with self.assertRaises(ValueError):
            build_events('enacted')
        with self.assertRaises(ValueError):
            build_events(buyback_dating='tomorrow')

    def test_rounding_precision(self):
        c = Check('test', '', '', D('1.00'), D('1.02'), D('1.02'), 'USD')
        self.assertEqual(c.tolerance, D('.005'))
        self.assertFalse(c.within)

    def test_invalid_range(self):
        with self.assertRaises(ValueError):
            replay([], Date('2026-10-01'), Date('2026-07-01'))
