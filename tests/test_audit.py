"""Behavioral checks for the publication review's explicit model boundaries."""
import datetime as dt
import unittest
from decimal import Decimal as D

from ledger.calendars import is_business_day, next_business_day
from ledger.engine import replay
from ledger.events import Event
from ledger.reconcile import run

Date = dt.date.fromisoformat


class AuditTests(unittest.TestCase):
    def test_daily_missed_dividend_is_rejected(self):
        start = Date('2026-11-01')
        events = [Event('open', 'opening_balance', 'STRC', start, shares=10),
                  Event('rate', 'rate_reset', 'STRC', start, rate=D('.12')),
                  Event('daily', 'regime_change', 'STRC', start, regime='daily'),
                  Event('miss', 'skip', 'STRC', start, record_date=start)]
        paid = replay(events[:-1], start, Date('2026-11-03'), as_of=start)
        self.assertGreater(paid.day('STRC', Date('2026-11-03')).paid_cum, 0)
        with self.assertRaisesRegex(ValueError, 'daily-regime arrears'):
            replay(events, start, Date('2026-11-03'), as_of=start)

    def test_oldest_arrears_receive_next_payment(self):
        events = [Event('open', 'opening_balance', 'STRK', Date('2026-07-01'), shares=10),
                  Event('dec', 'declaration', 'STRK', Date('2026-12-01'),
                        record_date=Date('2026-12-15'), per_share=D('2'))]
        led = replay(events, Date('2026-07-01'), Date('2026-12-31'))
        tranches = led.tickers['STRK'].tranches
        self.assertEqual([t.record_date for t in tranches],
                         [Date('2026-09-15'), Date('2026-12-15')])
        self.assertEqual(tranches[0].balance, D('.4'))
        self.assertEqual(tranches[1].balance, D('20'))
        self.assertEqual(led.day('STRK', Date('2026-12-31')).arrears, D('20.4'))

    def test_calendar_rules_at_2026_2027_boundaries(self):
        self.assertTrue(is_business_day(Date('2026-07-03'), 'USD'))  # Saturday holiday
        self.assertFalse(is_business_day(Date('2027-07-05'), 'USD'))  # Sunday substitute
        self.assertTrue(is_business_day(Date('2027-03-26'), 'USD'))
        self.assertFalse(is_business_day(Date('2027-03-26'), 'EUR'))  # Good Friday
        self.assertEqual(next_business_day(Date('2027-03-26'), 'EUR'), Date('2027-03-30'))

    def test_unresolved_checks_are_not_silently_fitted(self):
        checks = run()
        self.assertEqual(len(checks), 16)
        self.assertEqual(sum(c.within for c in checks), 11)
        gaps = [c for c in checks if not c.within]
        self.assertEqual(len(gaps), 5)
        self.assertEqual(gaps[0].delta, D('64.625'))  # USD thousands
        self.assertEqual(gaps[1].delta, D('60.125'))
        september = next(c for c in gaps if '2026-09-14..2026-09-20' in c.label)
        self.assertIn('interest', september.note)
        self.assertEqual(september.reported, D('57.4'))
