import csv
import datetime as dt
import io
import subprocess
import sys
import tempfile
import unittest
from decimal import Decimal as D
from pathlib import Path

from ledger.engine import replay
from ledger.events import Event
from ledger.reconcile import weekly_funding_checks

Date = dt.date.fromisoformat


def cli(*args):
    with tempfile.TemporaryDirectory() as folder:
        result = subprocess.run([sys.executable, '-m', 'ledger', '--out', folder, *args],
                                capture_output=True, text=True)
        schedule = (Path(folder) / 'schedule.csv').read_text() if result.returncode == 0 else ''
    return result, list(csv.DictReader(io.StringIO(schedule)))


class ReaderOutputTests(unittest.TestCase):
    def test_paid_requires_payment_evidence(self):
        base = [Event('open', 'opening_balance', 'STRF', Date('2026-07-01'), shares=10),
                Event('decl', 'declaration', 'STRF', Date('2026-09-01'),
                      record_date=Date('2026-09-15'), per_share=D('2.5'))]
        assumed = replay(base, Date('2026-07-01'), Date('2026-10-01'))
        self.assertEqual(assumed.tickers['STRF'].obligations[0].status, 'assumed_settled')
        evidenced = replay(base + [Event('pay', 'payment', 'STRF', Date('2026-09-30'),
                                         record_date=Date('2026-09-15'), per_share=D('2.5'))],
                           Date('2026-07-01'), Date('2026-10-01'))
        self.assertEqual(evidenced.tickers['STRF'].obligations[0].status, 'paid')

    def test_seeded_schedule_never_claims_paid(self):
        result, rows = cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual({r['status'] for r in rows}, {'assumed_settled'})
        strf = next(r for r in rows if r['ticker'] == 'STRF' and r['record_date'] == '2026-12-15')
        self.assertEqual((strf['status'], strf['basis']), ('assumed_settled', 'projected'))

    def test_payment_form(self):
        _, rows = cli()
        forms = {(r['ticker'], r['record_date']): r['payment_form'] for r in rows}
        self.assertEqual(forms['STRK', '2026-09-15'], 'cash')            # Aug 31 cash declaration
        self.assertEqual(forms['STRK', '2026-12-15'], 'election_unknown')
        self.assertEqual({f for (t, _), f in forms.items() if t != 'STRK'}, {'cash'})

    def test_share_changes_explain_strc_record_counts(self):
        _, rows = cli()
        strc = [r for r in rows if r['ticker'] == 'STRC']
        for prev, cur in zip(strc, strc[1:]):
            self.assertEqual(int(cur['record_shares']) - int(prev['record_shares']),
                             int(cur['share_change_since_prior_record']))
        self.assertEqual(sum(int(r['share_change_since_prior_record']) for r in strc), 85982656 - 104894705)
        drops = [r for r in strc if int(r['share_change_since_prior_record']) < 0]
        self.assertTrue(all(r['share_change_sources'].startswith('https://www.sec.gov/') for r in drops))

    def test_payment_window(self):
        result, _ = cli('--from', '2026-12-01', '--to', '2026-12-31')
        self.assertEqual(result.returncode, 0, result.stderr)
        rows = list(csv.DictReader(io.StringIO(result.stdout)))
        self.assertEqual(len(rows), 6)
        self.assertTrue(all('2026-12-01' <= r['payment_date'] <= '2026-12-31' for r in rows))
        self.assertIn('"schedule_rows": 30', result.stderr)
        result, _ = cli('--next-days', '30')
        rows = list(csv.DictReader(io.StringIO(result.stdout)))
        self.assertEqual([(r['ticker'], r['payment_date']) for r in rows],
                         [('STRC', '2026-11-02'), ('STRC', '2026-11-16')])

    def test_window_rejects_bad_input(self):
        for args in (('--next-days', '0'), ('--next-days', '5', '--from', '2026-11-01'),
                     ('--from', '2026-12-31', '--to', '2026-12-01')):
            result, _ = cli(*args)
            self.assertEqual(result.returncode, 2, args)

    def test_funding_labels_use_filing_wording(self):
        labels = {c.as_of: c.label for c in weekly_funding_checks()}
        self.assertTrue(labels['2026-09-21'].startswith(
            'Funding of dividends on preferred stock and interest on outstanding indebtedness 2026-09-14..'))
        self.assertIn('vs modeled STRC dividends', labels['2026-09-21'])
        self.assertTrue(labels['2026-10-19'].startswith('Funding of dividends on preferred stock 2026-10-12..'))


if __name__ == '__main__':
    unittest.main()
