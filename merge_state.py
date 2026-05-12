#!/usr/bin/env python3
"""Merge per-matrix-job result.json files into state.json.

Usage: merge_state.py <results_dir> <state_path>
"""
import sys, os, json, glob, time

results_dir = sys.argv[1]
state_path  = sys.argv[2]

state = json.load(open(state_path)) if os.path.exists(state_path) else {
    'items': [], 'acct_stats': {}, 'run_count': 0
}
state.setdefault('items', [])
state.setdefault('acct_stats', {})

merged_items = 0
for f in sorted(glob.glob(os.path.join(results_dir, '**/*.json'), recursive=True)):
    try:
        r = json.load(open(f))
    except Exception:
        continue
    if not r.get('ok'):
        continue
    for it in r.get('items', []):
        state['items'].append({
            'id':           it['id'],
            'band':         it.get('band'),
            'title':        it.get('title'),
            'target':       it.get('target'),
            'kw':           it.get('kw'),
            'ts':           time.strftime('%Y-%m-%dT%H:%M:%S'),
            'details_url':  f'https://archive.org/details/{it["id"]}',
        })
        merged_items += 1
    for lbl, s in r.get('per_acct', {}).items():
        agg = state['acct_stats'].setdefault(lbl, {'ok': 0, 'fail': 0})
        agg['ok']   += s.get('ok', 0)
        agg['fail'] += s.get('fail', 0)

state['items']     = state['items'][-10000:]
state['run_count'] = state.get('run_count', 0) + 1
state['last_run']  = time.strftime('%Y-%m-%d %H:%M:%S')
json.dump(state, open(state_path, 'w'), indent=2)
print(f'merged {merged_items} items; total in state: {len(state["items"])}')
