"""Dump recent in-memory telemetry events to a workspace file for easier collection.

Usage:
  - Run after reproducing the issue with the app running (so infra.telemetry has events).
  - From the repo root: python tools/dump_telemetry.py

This script attempts to import infra.telemetry and will write the most recent events
to ./telemetry_dump.jsonl (JSONL). If telemetry was not initialized it will still
write any in-memory buffer contents.
"""
import json
import os
from pathlib import Path

out_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'telemetry_dump.jsonl'))

records = []

# 1) Try to capture in-memory buffer (only works if running in same process)
try:
    from infra import telemetry
    try:
        mem = telemetry.get_recent(500)
        if mem:
            records.extend(mem)
            print(f"Collected {len(mem)} in-memory telemetry records")
    except Exception as e:
        print(f"Could not read telemetry buffer: {e}")
except Exception:
    # infra.telemetry not importable in this process (normal if app is running separately)
    pass

# 2) Look for on-disk telemetry.log files in common locations
candidate_paths = []
progdata = os.getenv('PROGRAMDATA')
if progdata:
    candidate_paths.append(os.path.join(progdata, 'Katcam', 'logs', 'telemetry', 'telemetry.log'))
# workspace-local fallbacks
wk = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
candidate_paths.append(os.path.join(wk, 'logs', 'telemetry', 'telemetry.log'))
candidate_paths.append(os.path.join(wk, 'telemetry', 'telemetry.log'))
candidate_paths.append(os.path.join(wk, 'telemetry.log'))

found = 0
for p in candidate_paths:
    try:
        if os.path.exists(p):
            found += 1
            with open(p, 'r', encoding='utf-8', errors='replace') as f:
                lines = f.read().splitlines()
            # take up to last 1000 lines to avoid huge dumps
            tail = lines[-1000:]
            for l in tail:
                try:
                    records.append(json.loads(l))
                except Exception:
                    # if not JSON, wrap as raw
                    records.append({'ts': None, 'type': 'raw_line', 'line': l, 'source': p})
            print(f"Read {len(tail)} lines from: {p}")
    except Exception as e:
        print(f"Failed to read candidate telemetry file {p}: {e}")

if found == 0:
    print("No on-disk telemetry.log found in common locations. If the app was run, check ProgramData path or enable telemetry in that process.")

try:
    with open(out_path, 'w', encoding='utf-8') as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"Wrote {len(records)} telemetry records to: {out_path}")
except Exception as e:
    print(f"Failed to write telemetry dump: {e}")
    raise
