#!/bin/bash
# Variant of local-runner.sh that takes a list of acct INDICES instead of a
# contiguous range. Used by orchestrator.sh which picks N fresh indices from
# accounts.json each cycle.
#
# Usage: local-runner-orch.sh <items_per_run> <idx1> <idx2> ...
set -e

ITEMS=$1
shift
INDICES=("$@")

if [ -z "$ITEMS" ] || [ ${#INDICES[@]} -eq 0 ]; then
    echo "usage: $0 <items_per_run> <idx1> [idx2 ...]" >&2
    exit 1
fi

ACCTS_FILE=/tmp/ia-signup/accounts.json
WORKER=/tmp/ia-uploader/worker.py
LOG_DIR=/tmp/ia-uploader/local-logs
mkdir -p "$LOG_DIR"

IPS=(51.38.147.246 51.38.151.248 51.38.151.249 51.77.50.113 51.77.52.213)
N_IPS=${#IPS[@]}
ts=$(date -u +%Y%m%dT%H%M%SZ)

echo "[$ts] orch-batch start: items=${ITEMS} accts=${#INDICES[@]} (${INDICES[*]})"
PIDS=()
i=0
for IDX in "${INDICES[@]}"; do
    # Single python call extracts all 3 fields (access, secret, screenname)
    read -r ACCESS SECRET SCREEN <<<"$(python3 -c "
import json
a = json.load(open('$ACCTS_FILE'))['accounts'][$IDX]
k = a.get('keys', {})
# fallback for screenname: derive from email local part (warm.js does the same
# for recovered accts that have screenname=null)
sn = a.get('screenname') or (a.get('email','') or '').split('@')[0]
print(k.get('access',''), k.get('secret',''), sn)
" 2>/dev/null)"
    if [ -z "$ACCESS" ] || [ -z "$SECRET" ]; then
        echo "  skip idx=$IDX (no keys)"
        i=$((i+1))
        continue
    fi
    LABEL="acct$((IDX+1))"
    IP="${IPS[$((i % N_IPS))]}"
    LOG="$LOG_DIR/orch-${LABEL}-${ts}.log"
    # -u: unbuffered stdout so tail-able in real time
    SOURCE_IP="$IP" IA_ACCESS="$ACCESS" IA_SECRET="$SECRET" \
        ACCOUNT_LABEL="$LABEL" ACCOUNT_SCREENNAME="$SCREEN" \
        ITEMS_PER_RUN="$ITEMS" \
        python3 -u "$WORKER" >"$LOG" 2>&1 &
    PIDS+=($!)
    i=$((i+1))
    # 5s stagger between worker spawns
    sleep 5
done

echo "[$(date -u +%FT%TZ)] ${#PIDS[@]} workers spawned, waiting..."
wait
echo "[$(date -u +%FT%TZ)] orch-batch done"
