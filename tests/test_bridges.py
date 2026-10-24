"""Bridges retain unknowns and conserve amounts without promoting sensitivities."""
import json
import tempfile
import unittest
from decimal import Decimal as D
from pathlib import Path

from ledger.bridges import finish_bridge, reconciliation_bridges, component, render_report
from ledger.filings import proxy_preferred_outstanding, tenq_debt_terms, tenq_subsequent_repurchases
from ledger.fetch import RAW
from ledger.reconcile import Check, run


class BridgeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.checks = run()
        cls.bridges = reconciliation_bridges(cls.checks)
        cls.by_id = {b['id']: b for b in cls.bridges}

    def test_five_raw_gaps_keep_balances_and_unknowns(self):
        self.assertEqual(len(self.bridges), 5)
        self.assertEqual(sum(c.within for c in self.checks), 11)
        for b, c in zip(self.bridges, (c for c in self.checks if not c.within)):
            scale = D(1000) if c.unit == 'USD thousands' else D(10)**6
            modeled = [p for p in b['components'] if p['kind'] == 'model']
            self.assertEqual(sum(p['low'] for p in modeled), c.ledger_low * scale)
            self.assertEqual(sum(p['high'] for p in modeled), c.ledger_high * scale)
            self.assertEqual(b['reported'], b['total_low'] + b['residual_high'])
            self.assertEqual(b['reported'], b['total_high'] + b['residual_low'])
            self.assertEqual(b['raw_delta'], c.delta * scale)
            self.assertFalse(b['raw_within'])
            self.assertFalse(b['settlement_verified'])
            self.assertTrue(b['unknown_inputs'])
            self.assertTrue(all(p['source_urls'] for p in b['components']))

    def test_fx_is_diagnostic_not_a_fitted_component(self):
        for month, fx, residual, tolerance in [('03', '1.1498', '64625', '1000'),
                                               ('06', '1.1394', '60125', '500')]:
            b = self.by_id['stre-2026-' + month]
            self.assertEqual(len(b['components']), 1)
            p = b['components'][0]['inputs']
            self.assertEqual(p['entitlement_eur'], D('19375000'))
            self.assertEqual(p['ecb_usd_per_eur'], D(fx))
            self.assertEqual(p['record_shares'], 7750000)
            self.assertEqual(p['ecb_observation_date'], b['dates']['adjusted_payment_date'])
            self.assertEqual(b['residual_low'], D(residual))
            self.assertEqual(b['rounding_uncertainty'], D(tolerance))
            self.assertEqual(b['diagnostics']['implied_usd_per_eur'], b['reported'] / p['entitlement_eur'])
        self.assertEqual(self.by_id['stre-2026-03']['reported'], D(44478 - 22136) * 1000)

    def test_funding_dates_do_not_become_record_or_settlement_dates(self):
        for prefix, record, nominal, adjusted in [
            ('08-17', '07-31', '08-15', '08-17'),
            ('09-21', '08-31', '09-15', '09-15'),
            ('10-19', '09-30', '10-15', '10-15'),
        ]:
            b = self.by_id['strc-funding-2026-' + prefix]
            self.assertEqual(b['reported_measure'], 'funding')
            for key, value in [('record_date', record), ('nominal_payment_date', nominal),
                               ('adjusted_payment_date', adjusted)]:
                self.assertEqual(b['dates'][key], '2026-' + value)
            self.assertEqual(b['rounding_uncertainty'], D(50000))
            p = b['components'][0]
            self.assertEqual(p['low'], p['inputs']['start_dated_record_shares'] * p['inputs']['per_share_usd'])
            self.assertEqual(p['high'], p['inputs']['end_dated_record_shares'] * p['inputs']['per_share_usd'])
        august = self.by_id['strc-funding-2026-08-17']['dates']
        self.assertLess(august['funding_period_end'], august['adjusted_payment_date'])
        october = self.by_id['strc-funding-2026-10-19']
        self.assertEqual(october['components'][0]['inputs']['start_dated_record_shares'], 90594215)
        self.assertEqual(october['residual_low'], D('202892.5'))

    def test_september_regular_interest_is_only_a_sensitivity(self):
        b = self.by_id['strc-funding-2026-09-21']
        coupons = b['components'][1:]
        self.assertEqual([p['low'] for p in coupons], [D('3156250'), D('2500000'), D('2641008.125')])
        self.assertEqual(sum(p['low'] for p in coupons), D('8297258.125'))
        self.assertEqual(b['total_high'], D('57379509.625'))
        self.assertEqual(b['residual_low'], D('20490.375'))
        self.assertEqual(b['residual_high'], D('925932.875'))
        self.assertLess(b['residual_low'], b['rounding_uncertainty'])
        self.assertEqual(b['status'], 'sensitivity_only')
        self.assertFalse(b['raw_within'])
        for p in coupons:
            self.assertEqual(p['kind'], 'sensitivity')
            i = p['inputs']
            self.assertEqual(i['principal_date'], '2026-06-30')
            self.assertEqual(i['contractual_coupon_date'], '2026-09-15')
            self.assertEqual(p['low'], i['principal_usd'] * i['annual_rate'] / i['payments_per_year'])

    def test_debt_parser_requires_complete_evidence_and_uses_closing_principal(self):
        raw = (RAW / 'edgar/10q-20260630.htm').read_bytes()
        terms = tenq_debt_terms(raw)
        self.assertEqual(len(terms), 6)
        debt = next(t for t in terms if t.name.startswith('2031'))
        self.assertEqual(debt.principal_usd, D(603659000))  # not inception 603750000
        self.assertEqual(debt.coupon_month_days, ((3, 15), (9, 15)))
        text = __import__('ledger.filings', fromlist=['to_text']).to_text(raw)
        for broken in [text.replace('Stated Interest Rate (2)', 'missing'),
                       text.replace('2031 Convertible Notes 603,659', 'missing'),
                       text.replace('0.875 %', 'missing')]:
            with self.assertRaisesRegex(ValueError, 'debt|principal'):
                tenq_debt_terms(broken)

    def test_every_gap_stays_open_with_a_one_line_reason(self):
        for b in self.bridges:
            self.assertFalse(b['raw_within'])
            self.assertTrue(b['open_reason'])
            self.assertNotIn('\n', b['open_reason'])
        self.assertEqual(self.by_id['strc-funding-2026-09-21']['filed_evidence'], [])

    def test_q1_10q_direct_stre_figure_disagrees_with_june_10q(self):
        b = self.by_id['stre-2026-03']
        shares, cash = b['filed_evidence']
        for e in (shares, cash):
            self.assertEqual((e['form'], e['accession'], e['filing_date']),
                             ('10-Q', '0001050446-26-000031', '2026-05-06'))
        self.assertEqual(shares['filed'], 7750000)
        self.assertTrue(shares['consistent'])
        self.assertEqual(cash['filed'], D(22895000))
        self.assertFalse(cash['consistent'])
        self.assertIn('553,000 USD', cash['note'])
        self.assertEqual(b['reported'], D(22342000))  # raw check keeps the June 10-Q derivation

    def test_july_repurchases_cap_entitled_shares_below_reported_funding(self):
        b = self.by_id['strc-funding-2026-08-17']
        (e,) = b['filed_evidence']
        self.assertEqual((e['form'], e['accession'], e['filing_date']),
                         ('10-Q', '0001050446-26-000044', '2026-08-03'))
        self.assertEqual(e['filed'], 288930)
        self.assertTrue(e['consistent'])
        most = 104894705 - 288930
        self.assertIn(f'{most:,} shares', e['note'])
        self.assertLess(most * D('0.5'), b['reported'] - b['rounding_uncertainty'])

    def test_proxy_september_share_count_sits_inside_modeled_range(self):
        (e,) = self.by_id['strc-funding-2026-10-19']['filed_evidence']
        self.assertEqual((e['form'], e['accession'], e['filing_date']),
                         ('DEF 14A', '0001193125-26-413159', '2026-10-05'))
        self.assertEqual(e['filed'], 94558175)
        self.assertEqual((e['model_low'], e['model_high']), (93161913, 94933151))
        self.assertTrue(e['consistent'])

    def test_new_filing_parsers_reject_missing_evidence(self):
        with self.assertRaisesRegex(ValueError, 'share basis'):
            proxy_preferred_outstanding('<p>no table</p>')
        with self.assertRaisesRegex(ValueError, 'repurchase'):
            tenq_subsequent_repurchases('<p>no sentence</p>', 'STRC')

    def test_signed_residuals_do_not_clamp_or_absorb_rounding(self):
        c = Check('synthetic', 'fixture', '2026-01-01', D(10), D(20), D(30), 'USD')
        b = finish_bridge(c, 'fixture', D(1), [component('example', 'model', D(20), D(30), {}, [])], {}, ['Unknown'])
        self.assertEqual((b['residual_low'], b['residual_high']), (D(-20), D(-10)))
        self.assertEqual(b['reported'], b['total_high'] + b['residual_low'])

    def test_standard_run_writes_readable_and_machine_reports(self):
        with tempfile.TemporaryDirectory() as folder:
            run(Path(folder))
            data = json.loads((Path(folder) / 'reconciliation.json').read_text())
            self.assertEqual(len(data['bridges']), 5)
            self.assertEqual(sum(c['within'] for c in data['checks']), 11)
            report = (Path(folder) / 'reconciliation.txt').read_text()
            self.assertEqual(report, render_report(self.bridges))
            self.assertIn('Unknown residual: 20,490.375 .. 925,932.875 USD', report)
            self.assertIn('Settlement verified: False', report)
            self.assertIn('not observed FX', report)
            self.assertEqual(report.count('  Open: '), 5)
            self.assertIn('Filed (DEF 14A 0001193125-26-413159, 2026-10-05)', report)
