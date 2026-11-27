#!/usr/bin/env python3
"""Check the cart reported on a Chrome order click against Ricardo's latest approval."""
from decimal import Decimal
import json
from pathlib import Path
import re
import sys

import _hookfail

BROWSER = 'mcp__claude-in-chrome__'
ORDER = re.compile(r'\b(?:place (?:your )?order|buy now|complete purchase)\b', re.I)
CHECKOUT = '\nCheckout: '
ORDER_ACTIONS = {'click', 'left_click', 'double_click', 'triple_click', 'key', 'submit',
                 'form', 'form_action', 'form_input', 'form_submit'}


def order_carts(event):
    tool = event.get('tool_name', '')
    if not tool.startswith(BROWSER):
        return
    action = tool[len(BROWSER):]
    data = event['tool_input']
    if action == 'browser_batch':
        for step in data['actions']:
            yield from order_carts({'tool_name': BROWSER + step['name'].removeprefix(BROWSER),
                                    'tool_input': step['input']})
    elif data.get('action', action) in ORDER_ACTIONS:
        summary, _, cart = data.get('action_summary', '').partition(CHECKOUT)
        if any(ORDER.search(str(value)) for value in
               (summary, data.get('summary', ''), data.get('target', ''), data.get('label', ''))):
            yield cart


def names(value):
    if not isinstance(value, list) or not value or any(not isinstance(n, str) or not n.strip() for n in value):
        raise ValueError('expected a nonempty list of item names')
    return [n.strip() for n in value]


def amount(value):
    if type(value) not in (int, Decimal) or not Decimal(value).is_finite() or value < 0:
        raise ValueError('expected a finite, nonnegative amount')
    return Decimal(value)


def latest_approval():
    path = Path.home() / '.local/state/purchase-approvals.jsonl'
    last = ''
    with path.open() as stream:
        for line in stream:
            if line.strip():
                last = line
    row = json.loads(last, parse_float=Decimal)
    if not all(isinstance(row[key], str) and row[key].strip() for key in ('utc', 'approved_by')):
        raise ValueError('approval metadata missing')
    return [item.casefold() for item in names(row['items'])], amount(row['max_total'])


def body(event):
    for cart in order_carts(event):
        try:
            approved, cap = latest_approval()
        except (OSError, ValueError, KeyError, TypeError):
            _hookfail.decide('deny', "Get Ricardo's approval and have him record the items and maximum total "
                             'in ~/.local/state/purchase-approvals.jsonl before placing the order.')
            return
        try:
            row = json.loads(cart, parse_float=Decimal)
            items, total = names(row['items']), amount(row['total'])
        except (ValueError, KeyError, TypeError):
            _hookfail.decide('deny', 'Read the current checkout and add its full item list and total to '
                             'action_summary as a new line: Checkout: {"items":["item"],"total":10.00}')
            return
        extra = [item for item in items if not any(
            item.casefold() in name or name in item.casefold() for name in approved)]
        reasons = []
        if extra:
            listed = ', '.join(extra)
            reasons.append(f"Remove {listed} from the cart, or get Ricardo's approval for {listed}.")
        if total > cap:
            reasons.append(f"Bring the total {total} down to {cap} or less, or get Ricardo's approval for {total}.")
        if reasons:
            _hookfail.decide('deny', ' '.join(reasons))
            return


def triage(raw, event):
    if event is not None:
        return str(event.get('tool_name', '')).startswith(BROWSER) and bool(ORDER.search(raw))
    return True


if __name__ == '__main__':
    sys.exit(_hookfail.run('purchase-approval-gate.py', body, triage, guards='placing a browser order', timeout=5))
