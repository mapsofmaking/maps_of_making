# Story 14.6: Tile C — Update It Once, Seen Everywhere

Status: backlog — depends on 14.4 (pod branch) or 14.5 (self branch). Designed 2026-10-30: the dry run
plays the cycle, the storyboard's tile C row draws it (C1 first time, C2 saving, C3 done, C4 the tool, C5 a move).

## Story

As a space coordinator whose space is on the map,
I want to change my opening hours once and watch every reader show the new hours,
So that I see "don't repeat yourself" happen instead of being told about it.

## Acceptance Criteria

### AC0 — The tile's cycle (14.1 AC4)
**Given** a signed-in session
**When** the tile opens for the first time
**Then** it is a short tutorial, with the hex view still unfolded (continuity with onboarding): one field
(opening hours) and Save; below, the file then the card, read left to right the way a change travels
(your `space.ttl` → the card the map draws from it), the hours line marked; saving an unchanged value
is refused with a plain hint
**When** it is done and reopened on a later visit
**Then** the hexes fold into the row and the tile opens straight onto the tool (AC0b)
**And** there is no "First time" or "Done" badge: which mode opens is read from the pod (AC5), the
coordinator doesn't need to see the switch.

### AC0b — The tool: fields left, preview fixed right
**Then** the whole profile is one form on the left (the same fields as tile A: name, street address,
description, contact email, opening hours), under the design system's `Finder` ("Find a field": matches labels and
values, results grouped by section, ↑↓ / Enter / Esc, "/" to focus) because the profile grows as networks ask for more fields; the field column scrolls on its own
**And** the preview holds still on the right (file → card), follows what is typed, and says "Not saved
yet"; Save sits under the preview, right-aligned, disabled until something changed, with a live summary
beside it ("1 change: Street Address. The pin moves with it.")
**And** after Save, the left column shows the steps ticking (AC4), then Bernard's line, the "was" lines
and "Back to your tiles"; the right column shows the result.

### AC1 — One edit
**Given** the pod branch and a signed-in session
**When** the coordinator saves
**Then** the app writes the change to `space.ttl` (conditional write, kit `lib/conditional.ts`, since the
file has other writers: the backoffice, later Bernard)
**And** on the self branch, the tile says where to edit (their own file) and waits for the next step.

### AC1b — A space can move
**When** the street address changed (rare, but spaces move)
**Then** the address is geocoded automatically before the write, as genjson does today (its Nominatim
proxy; decided 2026-10-30 to keep this as the default behaviour), and the new coordinates are written
with the address in the same write: the address and the pin move together, or neither does
**And** an address the geocoder can't place is refused before anything is written, naming the geocoder,
with everything typed kept
**And** the result names the move ("Street Address was …. The pin moved with it").

### AC2 — Picked up now, not at the next tick
**Then** the app calls `POST /api/heartbeat-space/{space_id}` after the write, so the map ingests the
file and rebuilds its data at once (the endpoint exists since Story 3.1: it fetches, ingests and
rematerializes before answering), and "The map read it" ticks only on its answer
**And** the endpoint's 60 s cooldown is handled: a 429 shows "The map reads it in N s" from
`retry_after_seconds` and retries once, never an error
**And** after it ticks, a plain hint says "Map open in another tab? Reload it to see the change." (an
open map page doesn't refetch by itself; drop the hint once the map refetches on tab focus, see Dev
Notes).

### AC3 — The card and the file
**Then** the result shows two views of one thing, file first then card, from live sources only: the file
as saved (the lines of `space.ttl` the tile touches, changed lines
marked), then the card as the map draws it (rematerialized GeoJSON); while the map hasn't read it yet,
the card shows the old values (the split is the lesson); each changed field gets a "was …" line
**And** no Bernard reader (decided 2026-10-30: asking the bot is a tile still to discover, "Let it
answer for you"; showing it here first confuses), and no "other SpaceAPI apps" reader (dropped
2026-10-30: few makerspaces register on SpaceAPI; a Turtle → SpaceAPI JSON export is a later,
low-priority tool)
**And** the word "endpoint" unlocks
**And** once done, the tile stays as the shortcut for the next change ("Back to your tiles").

### AC4 — Waiting is acknowledged
**Then** the wait is shown as steps that tick ("Found the new address" when it moved, "Written to your
pod", "The map read it"), using the kit's pending line (400 ms delay, admits a long
wait after 10 s), and a failed ingest says which reader didn't update and why.

### AC5 — No progress flag
**Then** tile C's done is derived from the pod's data (`onb:doneWhen`: hours modified after creation),
never written as a flag; app preferences that can't be derived (none for this tile) go in
`settings/home.ttl` (see 14.1 AC4).

## Done gate
Live: hours changed in the tile appear on the map card and in the raw source within one minute.

## Dev Notes
- **The first fold happens here** (14.1 AC7, decided 2026-10-31): at the end of tile C's tutorial the page
  calls `foldForFirstTime()` (mom-home `src/workbench/page.ts`). No animation (tried and dropped,
  Nicolas: "unconvincing and cheap visually"; the hexes are the cue, the fold is sharp and fast).
  Bernard's voice closes the gap instead: one line in `onboarding.ttl` on `:change`, said as the hexes
  fold, naming the toggle (draft: "I'll fold the map up here. It's one click away, top right: Show
  all."). The line is Nicolas's to word.
- Map follow-up (outside Epic 14, → backlog): `web/app.js` refetches `/data/spaces.geojson` on
  `visibilitychange` when the tab comes back after > 30 s hidden. Then a coordinator who keeps the map in
  another tab sees the change on switching back, and AC2's reload hint can go. Home and the map are on
  different origins, so BroadcastChannel can't carry it.
- Address changes geocode through genjson's proxy (`/api/geocode`, Nominatim, 1 req/s).
