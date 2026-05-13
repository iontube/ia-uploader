#!/usr/bin/env python3
"""Pick N fresh acct indices from /tmp/ia-signup/accounts.json.
'Fresh' = has keys, NOT banned, last_burst_at NULL OR older than <cooldown_h>.
Prints space-separated indices on success, empty line if not enough."""
import sys, json, time
from datetime import datetime

BATCH = int(sys.argv[1]) if len(sys.argv) > 1 else 25
COOLDOWN_H = int(sys.argv[2]) if len(sys.argv) > 2 else 22

threshold = time.time() - COOLDOWN_H * 3600
s = json.load(open('/tmp/ia-signup/accounts.json'))
fresh = []
for i, a in enumerate(s['accounts']):
    if not a.get('keys', {}).get('access'):
        continue
    if a.get('banned'):
        continue
    # No warmed_at gate: worker.py runs an inline warmup_one_txt() as its
    # very first action before the doorway loop, so any acct picked here
    # will receive its benign notes-<screen>-<date> upload before doorways.
    lb = a.get('last_burst_at')
    if lb:
        try:
            t = datetime.fromisoformat(lb.replace('Z', '+00:00')).timestamp()
            if t > threshold:
                continue
        except Exception:
            pass
    fresh.append(i)
    if len(fresh) >= BATCH:
        break

if len(fresh) < BATCH:
    print("")
else:
    print(" ".join(str(x) for x in fresh))
