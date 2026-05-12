#!/usr/bin/env python3
"""Merge tags_used from a worker result into a used-tags JSON file.
Usage: merge_used.py <used_in.json> <result.json> <used_out.json>
"""
import sys, json

used = json.load(open(sys.argv[1]))
result = json.load(open(sys.argv[2]))
used.extend(result.get('tags_used', []))
# dedup but preserve order
seen = set()
out = []
for t in used:
    if t not in seen:
        seen.add(t)
        out.append(t)
json.dump(out, open(sys.argv[3], 'w'))
print(f'merge_used: input={len(used)} output={len(out)}', file=sys.stderr)
