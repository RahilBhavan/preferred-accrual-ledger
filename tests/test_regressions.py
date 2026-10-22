import datetime as dt
import csv
import subprocess
import sys
import tempfile
import unittest
from decimal import Decimal as D
from pathlib import Path
from unittest.mock import patch

from ledger.engine import replay
from ledger.events import Event, append_jsonl, load_jsonl
from scripts import validate

Date = dt.date.fromisoformat


class ReplayRegressionTests(unittest.TestCase):
    def test_validation_hashes_only_its_eight_required_outputs(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for scenario in ('current', 'approved'):
                out = root / 'results' / scenario
                out.mkdir(parents=True)
                for name in ('events.jsonl', 'schedule.csv', 'summary.json', 'reconciliation.json'):
                    (out / name).write_text('fixture')
            (root / 'results/unrelated.txt').write_text('unrelated')
            with patch.object(validate, 'ROOT', root):
                self.assertEqual(len(validate.hashes()), 8)
                (out / 'schedule.csv').unlink()
                with self.assertRaises(FileNotFoundError):
                    validate.hashes()

    def test_late_declaration_cannot_backdate_settlement(self):
        for ticker, amount in (('STRD', '2.5'), ('STRK', '2')):
            events = [Event('open', 'opening_balance', ticker, Date('2026-07-01'), shares=10),
                      Event('decl', 'declaration', ticker, Date('2026-10-15'),
                            record_date=Date('2026-09-15'), per_share=D(amount))]
            with self.assertRaisesRegex(ValueError, 'declaration date'):
                replay(events, Date('2026-07-01'), Date('2026-10-21'))

    def test_declaration_becomes_visible_on_its_date(self):
        events = [Event('open', 'opening_balance', 'STRD', Date('2026-07-01'), shares=10),
                  Event('decl', 'declaration', 'STRD', Date('2026-09-20'),
                        record_date=Date('2026-09-15'), per_share=D('3'))]
        led = replay(events, Date('2026-07-01'), Date('2026-09-30'))
        self.assertEqual(led.day('STRD', Date('2026-09-16')).declared_unpaid, 0)
        self.assertEqual(led.day('STRD', Date('2026-09-20')).declared_unpaid, 30)
        self.assertEqual(led.day('STRD', Date('2026-09-30')).paid_cum, 30)

    def test_opening_balance_is_unique_and_at_start(self):
        start = Date('2026-07-01')
        for events in (
            [Event('open', 'opening_balance', 'STRF', Date('2026-07-02'), shares=10)],
            [Event('open', 'opening_balance', 'STRF', start, shares=10),
             Event('reset', 'opening_balance', 'STRF', Date('2026-07-02'), shares=1)],
        ):
            with self.assertRaisesRegex(ValueError, 'opening balance'):
                replay(events, start, Date('2026-09-30'))

    def test_corrupt_store_is_rejected_without_appending(self):
        a = Event('a', 'opening_balance', 'STRF', Date('2026-07-01'), shares=10)
        conflict = Event('a', 'opening_balance', 'STRF', Date('2026-07-01'), shares=11)
        b = Event('b', 'issuance', 'STRF', Date('2026-07-02'), shares=1)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'events.jsonl'
            for text in (a.to_json() + '\n' + conflict.to_json() + '\n', a.to_json() + '\n{"id":'):
                path.write_text(text)
                with self.assertRaises(ValueError):
                    append_jsonl(path, [b])
                self.assertEqual(path.read_text(), text)

    def test_append_after_complete_line_without_newline(self):
        a = Event('a', 'opening_balance', 'STRF', Date('2026-07-01'), shares=10)
        b = Event('b', 'issuance', 'STRF', Date('2026-07-02'), shares=1)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'events.jsonl'
            path.write_text(a.to_json())
            self.assertEqual(append_jsonl(path, [b]), (1, 0))
            self.assertEqual(load_jsonl(path), [a, b])

    def test_cli_empty_schedule_has_header(self):
        with tempfile.TemporaryDirectory() as folder:
            result = subprocess.run([sys.executable, '-m', 'ledger', '--end', '2026-06-30',
                                     '--out', folder], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            with (Path(folder) / 'schedule.csv').open() as f:
                rows = csv.DictReader(f)
                self.assertIn('record_date', rows.fieldnames)
                self.assertEqual(list(rows), [])

    def test_payment_date_cannot_be_silently_moved(self):
        for day in ('2026-09-29', '2026-10-05'):
            events = [Event('open', 'opening_balance', 'STRF', Date('2026-07-01'), shares=10),
                      Event('pay', 'payment', 'STRF', Date(day),
                            record_date=Date('2026-09-15'), per_share=D('2.5'))]
            with self.assertRaisesRegex(ValueError, 'payment date'):
                replay(events, Date('2026-07-01'), Date('2026-10-06'))

    def test_zero_entitlement_stays_zero_after_issuance(self):
        events = [Event('open', 'opening_balance', 'STRF', Date('2026-07-01'), shares=0),
                  Event('issue', 'issuance', 'STRF', Date('2026-09-16'), shares=100)]
        led = replay(events, Date('2026-07-01'), Date('2026-09-29'))
        state = led.day('STRF', Date('2026-09-16'))
        self.assertEqual(state.accrued, 0)
        self.assertEqual(led.tickers['STRF'].obligations[0].record_shares, 0)
