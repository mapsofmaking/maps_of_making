# Story 14.6: Tile C — Update It Once, Seen Everywhere

Status: backlog — depends on 14.4 (pod branch) or 14.5 (self branch). Placeholder frames only on the
storyboard (C1): this tile is the first workbench mini-app and gets its own canvas before dev.

## Story

As a space coordinator whose space is on the map,
I want to change my opening hours once and watch every reader show the new hours,
So that I see "don't repeat yourself" happen instead of being told about it.

## Acceptance Criteria

### AC1 — One edit
**Given** the pod branch and a signed-in session
**When** the coordinator changes `mom.opening_hours` in the tile
**Then** the app writes the change to `space.ttl` (conditional write, kit `lib/conditional.ts`, since the
file has other writers: the backoffice, later Bernard)
**And** on the self branch, the tile says where to edit (their own file) and waits for the next step.

### AC2 — Picked up now, not at the next tick
**Then** the app calls `POST /api/heartbeat-space/{space_id}` so the change is ingested at once.

### AC3 — The readers, live
**Then** the workbench shows, from live sources only: the map card (rematerialized GeoJSON), the source as
the map holds it (`/api/space/{id}/raw`); no "other SpaceAPI apps" reader (dropped 2026-10-30: few
makerspaces register on SpaceAPI; a Turtle → SpaceAPI JSON export is a later, low-priority tool)
**And** Bernard's own answer is shown only if a query path to bernardo exists for the app; otherwise it
stays a labelled preview (bible §3: no query, no claim)
**And** the word "endpoint" unlocks
**And** once done, the tile stays as the shortcut for the next change ("Back to your tiles").

### AC4 — Waiting is acknowledged
**Then** the wait between write and map update uses the kit's pending line (400 ms delay, admits a long
wait after 10 s), and a failed ingest says which reader didn't update and why.

## Done gate
Live: hours changed in the tile appear on the map card and in the raw source within one minute.
