"""Trigger one heartbeat cycle inside maps-link-handler, retrying until it succeeds.

Piped over stdin (`docker exec -i maps-link-handler python3 - < scripts/heartbeat_run.py`)
so it needs no volume mount. Right after a full stack restart, link-handler's /health
answers before Oxigraph accepts connections, and the first heartbeat 500s with
httpx.ConnectError — leaving spaces.geojson stale. Retry instead, and exit non-zero
if it never succeeds so `make publish` cannot report success over a failed rebuild.
"""
import sys
import time

import httpx

URL = "http://localhost:8000/api/heartbeat/run"
ATTEMPTS = 6
DELAY_SECONDS = 10

for attempt in range(1, ATTEMPTS + 1):
    try:
        r = httpx.post(URL, timeout=300)
        print(f"heartbeat: {r.status_code} (attempt {attempt}/{ATTEMPTS})")
        if r.status_code == 200:
            sys.exit(0)
    except httpx.HTTPError as e:
        print(f"heartbeat: {type(e).__name__} (attempt {attempt}/{ATTEMPTS})")
    if attempt < ATTEMPTS:
        time.sleep(DELAY_SECONDS)

print("heartbeat: FAILED — spaces.geojson not rebuilt", file=sys.stderr)
sys.exit(1)
