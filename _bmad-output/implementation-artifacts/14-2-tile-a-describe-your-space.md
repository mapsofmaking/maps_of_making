# Story 14.2: Tile A — Describe Your Space

Status: done (live 2026-10-31, mom-home `sha-537450a`)

## Story

As a space coordinator,
I want to describe my space and see its card as a visitor will,
So that I have something worth keeping before anyone asks me to keep it.

## Context

genjson (`web/genjson/`) built tiers 0 and 1 only. Tier 2 is a "Go deeper →" teaser: Stories 9.6 (hours,
networks, SDGs) and 9.10 (space type, equipment) were superseded on 2026-06-16 and never built. So tile A
takes genjson's tier 0 as its gate and its tier 1 as optional fields, with genjson's keyboard flow and
geocoding; tier 2 doesn't move as a block, each field goes to the tile that uses it:

| Field | Goes to |
|---|---|
| opening hours | tile C's first time (14.6) |
| networks | the join tile (a handshake, not a typed field) |
| SDGs, and what a network asks for | tile C's tool, under "Asked by <network>" |
| space type, equipment (tier 3) | the vertical's own tree, or a network's request |

The fields, and how tile B writes them (Turtle for the pod, JSON for self-hosting), are in
[`docs/reference/space-file.md`](../../docs/reference/space-file.md).

## Acceptance Criteria

### AC1 — No account to begin
**Then** tile A asks for nothing but the space: no email to sign up, no password.

### AC2 — A familiar form, no guide yet
**Then** tile A has no Bernard line (2026-10-31: a familiar form needs no guide; Bernard enters at A2, the
call, and names themselves there, once)
**And** a plain lead says what this is, for someone who lands on home without the map's context: "Maps of
Making is a map of the places where people make things together: fablabs, hackerspaces, repair cafés,
community workshops. Add yours. A name and a town are enough to start, and you see your card before
anything goes public." with a link "See the map ↗" (phone: a shorter lead, storyboard A1 on a phone)
**And** the lead comes from the tree (`onb:lead` on `:describe`, a new term; system voice, no em-dash).

### AC3 — The bedrock: name, then where
**Then** the fields are, in order: space name; street address (optional, hint "Optional. Without it, the
pin sits in the town's centre."); city (required)
**And** after the pin, under the label "Optional · change it any time": description, contact email, Matrix
room, website, logo URL (genjson's hints, `bernard_copy.yaml` `field_hints`, carried into the tree)
**And** on a phone the optional fields fold behind "Add more: description, contact, website, logo".

### AC4 — genjson's keyboard flow
**Then** the name commits on Tab or Enter (only when not empty; empty, Tab moves on as usual) or on leaving
the field, and focus goes to the street; Enter in street goes to city; Enter in an optional field goes to
the next one
**And** fields not yet reached are `inert`, so focus can't land in them early
**And** one hint, under the name only: "Tab or Enter to move on."
**And** on a phone, `enterkeyhint` says next/done.

### AC5 — Geocoding: a city is enough, and the place found is shown
**Given** a city (with or without a street)
**When** street or city is committed (Tab, Enter, leaving the field; never per keystroke; the same
street|city pair never asked twice)
**Then** the app geocodes through the map's proxy (`POST /api/geocode`) and shows the pin line with the
place the geocoder found: "Dropping the pin here: 50.8391, 4.3297 · Anderlecht, Brussels · 1070 · BE", so
a wrong match shows (live, 2026-10-31: "Canal, Springfield" lands on a garage in Long Eaton, UK)
**And** postcode and country are filled from the answer; country is required: when the answer has none,
a two-letter field appears; when there is no answer, latitude and longitude fields appear, everything typed
kept
**And** the wait shows genjson's meter (at least 2.3 s, so the pin reads as worked out, not magicked).

### AC6 — The card preview
**When** name, city, country and coordinates are in
**Then** "Show me my card" opens the card as the map will render it, built from the draft, labelled
"Preview · nothing is published", plus the profile facts (description, hours, next event; hours and event
show "—" until their tiles)
**And** Bernard enters, names themselves once, then the stakes (tree: `onb:saidDone`): "Hi, I'm Bernard
(they/them), from Mother Sand. That's you, the way a visitor will see it. For now it only lives in this
browser. Nobody else can see it." then "Want it out there for real?", with "Publish it →" and a plain "Fix
something first"
**And** tile A is done; tile B opens.

### AC7 — The draft survives
**Then** the draft is kept with the kit's `makeDraftStore` on the home origin, for 30 days (genjson's never
expired; the kit's 24 h default is too short for a coordinator who comes back next week)
**And** genjson's `genjson_draft` key is not carried over: it lives on the map's origin, which home can't
read.

### AC8 — One copy of the words
**Then** every line tile A shows (lead, labels, hints, geocoding messages, Bernard's A2 lines) is in
`onboarding.ttl` (14.1 AC2: the app's single source); no YAML or generated JSON copy in the app
**And** the voice check reads the Turtle: mom-home `src/tree/voice.test.ts` (2026-10-31: the check
lives with the tree it reads; maps_of_making's `tests/test_bernard_voice_completeness.py` keeps checking
genjson's YAML until 14.8 retires both) carries genjson's forbidden phrases, no em-dash, and checks every
line tile A uses is in the tree and nothing unused is.

## Tasks

Built in mom-home, one vertical slice at a time, each reviewed live by Nicolas before the next.

- [x] S1 `dd84e41`: tile A's fields from genjson; `onb:lead` instead of a Bernard line (AC1, AC2, AC3);
  Bernard introduces themselves at the card (`onb:saidDone`, AC6)
- [x] S2 `b7714fa`: the keyboard flow, one beat at a time, `inert` until reached (AC4)
- [x] S3 `674d1e4`: geocoding through home's own `/api/geocode`, city fallback with a note, manual
  country and coordinates, genjson's meter (AC5); focus lands on "Publish it"; no "Done" chip
- [x] S4–S6 `537450a`:
  - draft kept with the kit's `makeDraftStore`, 30 days, key `mom-home:draft:space`, resumed with its
    pin and no new geocoder call; "Start over" asks in the page (AC7)
  - genjson's visible normalisers (`https://`, Matrix `#`; a `matrix.to` link is left alone)
  - phone: slim folded strip (six hexes, +N, See all), "Add more" fold, `enterkeyhint`, `onb:leadShort`
    (AC2, AC3, AC4)
  - tile A's words in the tree: `onb:field` nodes and `onb:ui*` lines; voice and completeness check in
    mom-home `src/tree/voice.test.ts` (AC8)
  - example: Weld Done, Rue de l'Étincelle 12 (fictional), Marolles, Bruxelles

### Live check (2026-10-31)

`home.mapsofmaking.org` at `sha-537450a`, Playwright against production: the example geocodes through the
street fallback to 50.8371, 4.3458 · Marolles, Pentagone, Bruxelles · BE; the normalisers add and say;
after a reload the form and pin come back with no geocoder call; Start over empties the form and the
stored draft. Locally (same build), Chromium and Firefox at 390×844: strip shown and toolbar hidden,
Enter in city goes to "Add more", the strip unfolds and Fold returns focus to it, no horizontal scroll.
mom-home `npm run verify`: 259 tests, 54 audit checks.

### Review Findings

Code review 2026-10-31 of S4–S6 (medium). Fixed in `537450a`: a late geocoder answer restored a cleared
draft; a `matrix.to` link got a `#`; Enter-submit skipped the normalisers; a malformed stored draft could
break the page; one words reader per page (warn once); hex markup shared by toolbar and strip.

Not fixed, deferred:
- [ ] Non-http schemes in website/logo are kept as typed. The card doesn't render them as links today;
  validate at the pod write → Story 14.3
- [ ] A resumed draft whose geocoder answer had no country (country typed by hand) hides the typed
  country, and one with an empty place name reads as "set by hand". Rare (Nominatim sends both) →
  Story 14.3, when the draft is written
- [ ] The folded row's own words ("Show all", "See all ›", "+ N to discover") and the preview labels are
  14.1 page chrome, still in code; AC8 covers tile A → move them to the tree with the tile that next
  changes them

## How home reaches the geocoder

Same origin, through the gateway (decided 2026-10-31): `home.mapsofmaking.org/api/*` already goes to the
map's `maps-web` (vps-infra `gateway/sites/mom-home.caddy`), so the page calls `POST /api/geocode` on its
own origin and link_handler needs no CORS. Checked live 2026-10-31: a city alone returns Anderlecht, BE,
1070. (The map's apex answers no CORS, so never call it cross-origin.)

## Dev Notes

- Not carried from genjson: the 4 s intro wait; Export JSON and the progress strip (tile B's self-host
  door, 14.5); the GitLab walkthrough (14.5); `confirm()` on clear (in-page instead); the schema check
  (only top-level `required`; useful for the self-host JSON only).
- The proxy is rate-limited (1 req/s, nginx 2 req/s/IP). The example ("Fill in an example") must geocode:
  14.1's "Rue du Canal 12, Anderlecht" has no street-level match; with the city fallback it lands on
  Anderlecht.
- Kept from genjson: the visible normalisers (`https://` on website and logo, `#` on a Matrix room, the
  hint turns amber until the field is edited).
- Write `schema:addressLocality` from the city field, never parse it back out of a free-text address
  (SpaceAPI spaces lack it and `find()` misses them).
- Done check stays `schema:name` + `schema:address`.
- The Playwright gate from Story 9.3 (`test_wizard_tier0_tier1_export`) doesn't port as is (no export in
  tile A); a home test covers AC4 and AC5 instead.
