"""Dated explanations for raw gaps; sensitivities never change check outcomes."""
from __future__ import annotations

import datetime as dt
import re
from decimal import Decimal as D

from . import filings as F
from .engine import replay
from .events import Event
from .fetch import RAW
from .seed import LEDGER_START, _meta, build_events
from .terms import TENQ


def component(label, kind, low, high, inputs, source_urls):
    return dict(label=label, kind=kind, low=low, high=high,
                inputs=inputs, source_urls=source_urls)


def finish_bridge(check, bridge_id, scale, components, dates, unknowns, diagnostics=None):
    """All bridge amounts are USD. Signed residuals retain the full range, not just its gap."""
    low = sum((c['low'] for c in components), D(0))
    high = sum((c['high'] for c in components), D(0))
    reported = check.reported * scale
    return dict(id=bridge_id, check_label=check.label, unit='USD', source_url=check.source_url,
                source_as_of=check.as_of, financial_cutoff='2026-10-21',
                reported=reported, reported_measure='cash dividends' if bridge_id.startswith('stre') else 'funding',
                raw_within=check.within, raw_delta=check.delta * scale,
                rounding_uncertainty=check.tolerance * scale,
                status='sensitivity_only' if any(c['kind'] == 'sensitivity' for c in components) else 'unresolved',
                components=components, total_low=low, total_high=high,
                residual_low=reported - high, residual_high=reported - low,
                dates=dates, unknown_inputs=unknowns, diagnostics=diagnostics or {},
                settlement_verified=False)


def fx_bridge(check):
    from .reconcile import ECB_FILE, ecb, ecb_on_or_before
    pay = dt.date(2026, 3 if 'Q1' in check.label else 6, 31 if 'Q1' in check.label else 30)
    raw = (RAW / 'edgar/10q-20260630.htm').read_bytes()
    shares = F.tenq_shares_issued(raw)['STRE']
    start = pay.replace(day=1)
    led = replay([Event('open', 'opening_balance', 'STRE', start, shares=shares)], start, pay, as_of=start)
    rec = next(r for r in led.tickers['STRE'].obligations if r.pay_date == pay)
    rates = ecb()
    observation = max(day for day in rates if day <= pay)
    fx = ecb_on_or_before(rates, pay)
    euro = rec.amount
    paid = F.tenq_cash_dividends_paid(raw)['STRE']
    inputs = dict(reported_q2_usd_thousands=paid[0], reported_h1_usd_thousands=paid[1],
                  record_shares=shares, per_share_eur=rec.per_share, entitlement_eur=euro,
                  share_balance_date='2026-06-30', ecb_usd_per_eur=fx, ecb_observation_date=str(observation))
    comp = component('STRE entitlement translated at ECB reference FX', 'model', euro * fx, euro * fx,
                     inputs, [TENQ, _meta(ECB_FILE)['url']])
    return finish_bridge(check, f'stre-{pay:%Y-%m}', D(1000), [comp],
                         dict(record_date=str(rec.obligation.record_date), nominal_payment_date=str(rec.obligation.nominal_pay_date),
                              adjusted_payment_date=str(pay)),
                         ['Actual payment-time company FX', 'Actual earlier record-date shares; June closing shares assumed'],
                         dict(implied_usd_per_eur=check.reported * 1000 / euro,
                              implied_fx_basis='Diagnostic from reported USD / assumed EUR entitlement; not observed FX',
                              reported_basis='Q1 = six-month less Q2 rounded totals' if pay.month == 3 else 'Direct Q2 rounded total'))


def september_coupons():
    raw = (RAW / 'edgar/10q-20260630.htm').read_bytes()
    out = []
    for debt in F.tenq_debt_terms(raw):
        if (9, 15) not in debt.coupon_month_days or not debt.annual_rate:
            continue
        coupon = debt.principal_usd * debt.annual_rate / 2
        out.append(component(debt.name + ' assumed regular coupon', 'sensitivity', coupon, coupon,
                             dict(principal_usd=debt.principal_usd, principal_date='2026-06-30',
                                  annual_rate=debt.annual_rate, payments_per_year=2,
                                  contractual_coupon_date='2026-09-15',
                                  assumption='June principal held constant; regular interest only; cash date unverified'), [TENQ]))
    return out


def reconciliation_bridges(checks):
    """Build only unresolved historical checks; preserve their original measures and outcomes."""
    out = []
    ledgers = {dating: replay(build_events('current', dating), LEDGER_START, dt.date(2026, 10, 21),
                              as_of=dt.date(2026, 10, 21)) for dating in ('start', 'end')}
    from .reconcile import FUNDING_MAP  # avoids a module initialization cycle
    for check in checks:
        if check.within:
            continue
        if check.label.startswith('STRE cash'):
            out.append(fx_bridge(check))
            continue
        targets = next(targets for prefix, targets, _ in FUNDING_MAP if prefix == check.as_of)
        components = []
        dates = {}
        for ticker, nominal in targets:
            records = [next(r for r in led.tickers[ticker].obligations
                            if r.obligation.nominal_pay_date == nominal) for led in ledgers.values()]
            a, b = records
            components.append(component(f'{ticker} modeled dividend', 'model', min(r.paid for r in records),
                                        max(r.paid for r in records),
                                        dict(start_dated_record_shares=a.record_shares,
                                             end_dated_record_shares=b.record_shares,
                                             per_share_usd=a.per_share,
                                             share_balance_source=TENQ,
                                             share_changes_evidence='Replay attributed events.jsonl with start/end weekly dating',
                                             share_dating='Weekly buybacks at start/end; sensitivities, not guaranteed cash bounds'),
                                        list(dict.fromkeys([u for r in records for u in
                                             ([r.declaration.source_url] if r.declaration else [])]))))
            dates = dict(record_date=str(a.obligation.record_date), nominal_payment_date=str(nominal),
                         adjusted_payment_date=str(a.pay_date))
        unknowns = ['Exact record-date shares and intraweek share changes',
                    'Funding allocation/timing relative to actual settlement; no bank feed']
        if check.as_of == '2026-09-21':
            components.extend(september_coupons())
            unknowns += ['September debt principal after conversions/repurchases',
                         'Actual cash coupon dates and additional/special interest']
        # The reported period is distinct from the mapped dividend payment date.
        period = re.search(r'(\d{4}-\d{2}-\d{2}\.\.\d{4}-\d{2}-\d{2})', check.label).group(1)
        dates.update(funding_period_start=period.split('..')[0], funding_period_end=period.split('..')[1])
        out.append(finish_bridge(check, f'strc-funding-{check.as_of}', D(10)**6,
                                 components, dates, unknowns))
    return out


def display(value):
    if isinstance(value, (D, int)) and not isinstance(value, bool):
        return format(value, ',f').rstrip('0').rstrip('.') if isinstance(value, D) and value.as_tuple().exponent < 0 else format(value, ',')
    return str(value)


def render_report(bridges):
    """Plain text supports terminal readers without a new visual surface or dependencies."""
    lines = ['Five raw gaps remain; bridges explain components, not settlement.',
             'Financial cutoff: 2026-10-21. All bridge amounts: USD.',
             'Residual = reported minus component total; rounding is separate.',
             'Sensitivity overlap never upgrades a raw check.\n']
    for b in bridges:
        lines += [f"{b['id']} | {b['status']}", b['check_label'],
                  f"  Reported {b['reported_measure']}: {display(b['reported'])} USD; rounding +/- {display(b['rounding_uncertainty'])}",
                  f"  Raw gap: {display(b['raw_delta'])} USD; raw within: {b['raw_within']}"]
        lines.extend(f'  {k}: {v}' for k, v in b['dates'].items())
        for c in b['components']:
            lines.append(f"  {c['label']} [{c['kind']}]: {display(c['low'])} .. {display(c['high'])} USD")
            lines.extend(f'    {k}: {display(v)}' for k, v in c['inputs'].items())
            lines.extend(f'    Source: {url}' for url in c['source_urls'])
        lines += [f"  Component total: {display(b['total_low'])} .. {display(b['total_high'])} USD",
                  f"  Unknown residual: {display(b['residual_low'])} .. {display(b['residual_high'])} USD"]
        lines.extend(f'  {k}: {v}' for k, v in b['diagnostics'].items())
        lines.extend(f'  Unknown: {s}' for s in b['unknown_inputs'])
        lines += [f"  Report source ({b['source_as_of']}): {b['source_url']}",
                  '  Settlement verified: False\n']
    return '\n'.join(lines) + '\n'
