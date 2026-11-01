# Story 14.4: Tile B, Pod Door — First Publish (sign in, write, make public, register)

Status: backlog — depends on 14.2, 14.3 and 14.7 (the map must read Turtle); its sign-in step follows the
flow observed in 14.0 (`14-0-spike-report.md`)

## Story

As a space coordinator whose pod was just created,
I want my space's file written there, public, and on the map,
So that I leave tile B with my space live on the map.

## Acceptance Criteria

### AC1 — Sign in through the provider, once
**When** the account exists
**Then** the app signs in with Solid-OIDC using its Client ID Document; the provider's consent page names
`home.mapsofmaking.org` (kit ADR 010 point 6). The consent is for this app, which writes the profile; the
map never asks, it only reads the public file
**And** OD-2 (14.0, 2026-10-31): with the account-API login of 14.3 AC3, the coordinator sees only the
consent page (Authorize); a coordinator who comes back later, or a browser that drops the cookie (Safari
unverified), sees the provider's login first. Bernard's line before the redirect covers both (14.3 AC2).

### AC2 — The file
**Then** the app writes `space.ttl` at the pod root from the tile A draft (decided 2026-10-30: the pod is
linked-data native, so later tiles read and write links without JSON parsing). The mapping is the Turtle
column of [`docs/reference/space-file.md`](../../docs/reference/space-file.md) and must satisfy 14.7's
validation (a name, coordinates)
**And** the file is not the WebID document: `/profile/` holds the account's identity and sign-in data, and
the space can change hands or gain managers. The WebID document links to the space file (predicate to
settle in the tree).

### AC3 — Public by default, and only that
**Then** the app writes a resource ACL giving public read on `space.ttl` alone, hand-written Turtle
(kit ADR 003); the rest of the pod stays private
**And** a read without credentials returns 200 before the next step runs
**And** this per-resource ACL is the mechanism tile C reuses for an uploaded logo (14.6 AC6): one file, public read,
the rest private. Write it as a helper that takes the resource, not as code that only knows `space.ttl`.

### AC4 — On the map
**Then** the app calls `POST /api/register-url` with the file's address, through its own `/api/` proxy
**And** link_handler registers it as any endpoint (no special case for pods; `follow_redirects=False` holds
because pod URLs answer directly)
**And** registration is automatic: the coordinator never copies an address into the map (the analytics
baseline lost almost everyone at that step); the manual paste stays for the self-host door and the map's
drawer.

### AC4b — The threshold: "You're on the map"
**Then** the workbench shows, signed in (the account was just made): Bernard, "There you are. Anyone looking
for a workshop in <locality> can find you now."; the pin and its popup **read back from the map** (live,
labelled so, never a drawing); the file's address as plain text (not boxed like a field), a design-system
`Copyable` (the text is the button, with the copy icon); and one button, "See it on the map ↗", opening `https://mapsofmaking.org/?space=<id>` in a new
tab, focused on the pin with its card open
**And** Bernard closes by pointing at the next tile: "That's the hard part done. But hours change, stuff happen:
when something's different, update it once. Here, or later at home.mapsofmaking.org." with "Update it
once →" as the primary button to tile C ("See it on the map ↗" steps back to a plain button) (decided 2026-10-30: "come back and sign in" gave no cue what to do next).
**And** the word "pod" unlocks.

### AC5 — Each step can fail on its own
**Then** sign-in, write, ACL and register each report their own failure with a way forward, and a retry
resumes from the failed step (a written file is not rewritten; a registered URL dedups by endpoint, see
`_find_graph_by_endpoint`).

### AC — The writer is held to the map's reading
**Then** the Turtle the app writes is tested against `tests/fixtures/space/atelier-du-canal.ttl`
(maps_of_making; copy it into mom-home pinned to a commit, like the design system): the same draft values
give the same file, and the map's parser reads it to the statements in `atelier-du-canal.json`
(Story 14.7's parity test, `tests/test_space_turtle.py`).

## Done gate
A new coordinator, on a phone, goes from tile A to their pin opened on the map, against
`pod.mapsofmaking.org`, without copying anything.
