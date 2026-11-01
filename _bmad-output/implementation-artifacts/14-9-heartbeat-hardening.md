# Story 14.9: Heartbeat Hardening

Status: draft — written 2026-11-01 from a read of production (see Evidence); what counts as a change moved to 14.10

## Story

As the operator of the map,
I want the heartbeat to refuse addresses inside our own network, fetch only what changed, write only what
changed, and tell a blip from an outage,
So that the map's freshness signals are true and nobody can use it to read our internal services.

## Context

The heartbeat fetches every claimed space every 10 minutes (`config.yaml` `heartbeat_interval_seconds: 600`,
`heartbeat_concurrency: 24`), through `source.fetch_source` since Story 14.7 (shared with register), then
rebuilds `spaces.geojson` for the whole corpus. It is simple and bounded. Reading production on 2026-11-01
showed one security hole and four kinds of waste or false signal.

### Evidence (production, 2026-11-01, `docker logs maps-link-handler`, 5 ticks)
- 216 claimed spaces; a tick takes ~46 s including the rebuild of 3193 features; link-handler 145/384 MiB.
- Last tick: 204 fetched, 10 unreachable (ConnectError, ConnectTimeout, ReadTimeout, Cloudflare 521/523),
  8 "changed", 196 unchanged.
- The 8 "changes" are 4 spaces changing every tick on volatile values: `mainframe` (power-sensor readings,
  "Value changed 0 sec. ago"), two spaces' `lastchange` counter, one space's `ext_state.message` timestamp.
  Their `mom:updatedAt` moves every 10 minutes.
- `mom:openNow` is deleted and rewritten for all 204 fetched spaces every tick.
- 4 spaces (`superlab-engineering`, `6bf3a0cf49e3`, `7ca885df4da7`, `b63fbf8d0c07`) "backfill" payload fields
  every tick: the absence check looks for a field their file never has.
- No conditional request is sent: ETag and Last-Modified are stored, never sent back; the 304 path
  (`snapshot_store.advance_observed_at`) has no caller. Every tick downloads every file whole (~30k a day).
- `spaces.geojson`: 4.61 MB written with `indent=2` (`main.py` `_rematerialize_geojson`), 3.08 MB compact;
  423 KB on the wire (Caddy `encode zstd gzip`, `no-cache` + ETag), so the wire side is fine.

## Acceptance Criteria

### AC1 — Our own network is not reachable through a space URL
**Given** a URL given to `register-url` / `validate-url`, or fetched by the heartbeat
**Then** its host is resolved and refused when any address is loopback, private (RFC 1918), link-local
(169.254/16, fe80::/10), unique-local (fc00::/7), CGNAT (100.64/10), unspecified, or a single-label name
(`oxigraph`, `maps-web`, `mak-link-handler`: Docker service names)
**And** the connection goes to the address that was checked (no second lookup between check and connect:
DNS rebinding), and every redirect hop is checked the same way (the heartbeat follows redirects; register
does not)
**And** a refused URL says why ("That address points inside a private network.") and is never stored, so
`/api/space/{id}/raw` can never serve an internal answer
**And** tests cover each range, a public name that resolves to a private address, and a redirect to one.

### AC2 — The endpoint IRI is checked before it is written
**Then** `register_url` refuses a URL that cannot be written as a SPARQL `<…>` (the characters
`<>"{}|\^\`` and whitespace; `spaceapi_extract.turtle.safe_iri` already holds the rule) with 422, before
any update is built; the same check guards every place an endpoint URL is interpolated.

### AC3 — Fetch only what changed
**Then** the heartbeat sends `If-None-Match` (stored ETag) and `If-Modified-Since` (stored Last-Modified);
a 304 advances `observed_at` (`advance_observed_at`), counts as unchanged and downloads nothing
**And** the stored validators are dropped when the representation changes (media type differs from the
snapshot's, or the Accept header changes), so a stale ETag can never hide a real update (the trap in
memory `heartbeat_303_staleness_fix`)
**And** a server that answers 304 wrongly cannot freeze a space: a full fetch is forced at least once a day.

### AC4 — Write only what changed
**Then** `mom:openNow` / `mom:lastOpenChange` are written only when their value differs from the previous
snapshot's (or the graph lacks them)
**And** the payload-field backfill checks for the fields this space's source can actually produce, so it
runs once, not every tick.

### AC5 — A blip is not an outage
**Then** consecutive failures are counted per space (snapshot store); the card shows "unreachable" from the
third consecutive failure (~30 minutes), the reason of the last failure kept; one success resets the count
**And** `observed_at` is never re-stamped by a failure (unchanged).

### AC6 — The map file
**Then** `spaces.geojson` is written compact (`separators=(",", ":")`)
**And** the rebuild is skipped when, in a tick, no space changed content, fetch status or open state.

### AC7 — One line per tick
**Then** each tick logs one summary: dispatched, fetched, not modified (304), changed, unreachable,
skipped, rebuild done or skipped, duration. (Also the first number the analytics design can use.)

## What counts as a change: decided, a tile of its own (Nicolas, 2026-11-01)

Not this story's to settle: it becomes a tile in home's workbench, next to tile C (story 14.10). The
coordinator decides what counts, not the map:
- a change the coordinator makes counts: editing their own file (self-hosted JSON) or saving in tile C;
- values an outside automation changes (sensors, counters, timestamps) count only for the fields the
  coordinator opts in, in that tile.

This replaces the 2026-06-10 deferral (memory `project_stewardship_vs_liveness_tracks`: no sifting by us;
a coordinator opt-in later). The Evidence shows why it matters now: 4 spaces' `mom:updatedAt` moves every
10 minutes on sensor values, counters and timestamps.

Until 14.10 is built, nothing in 14.9 changes how a change is counted. Note one asymmetry that already exists:
since 14.7 a Turtle space is diffed on the fields the map keeps (its snapshot holds only those), a JSON
space on its whole payload. 14.10 makes both follow the coordinator's choice.

## Out of scope
- The GeoJSON render set (markers get id, position, `observed_at`, filter keys; card details fetched on
  demand): `deferred-work.md`, Epic 3 retro ("spaces.geojson payload-slimming"). It changes `web/app.js` and
  needs a read API: its own map story. Measured 2026-11-01, the card-only fields are about half the property
  bytes (specialties 12.9%, address 10.6%, endpoint_url 10.2%, geolocationNote 10.0%, website 6.5%), and `uri`
  repeats `id` (9.5%).

## Dev Notes
- Order: AC1 + AC2 first (security, existing hole), then AC3 + AC4 (load), AC5, AC6, AC7. Each a slice,
  reviewed, with a test against a local Oxigraph where it writes.
- Files: `infra/link_handler/source.py` (AC1 belongs in `fetch_source`: one place for register and
  heartbeat), `pipeline.py` (`fetch_snapshot`, `write_open_now`, `_payload_fields_absent`, `run_space_pipeline`),
  `snapshot_store.py` (fail count), `main.py` (`register_url`, `_rematerialize_geojson`, `run_heartbeat_tick`).
- `httpx` resolves names itself; AC1's "connect to the checked address" needs a custom transport (or resolve,
  check, and connect by IP with the Host header and SNI kept). Check before writing it.
- Memory to read first: `heartbeat_303_staleness_fix`, `project_three_token_freshness_model`,
  `ops_payload_field_backfill`, `project_stewardship_vs_liveness_tracks`.
