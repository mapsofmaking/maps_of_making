# Story 14.2: Tile A — Describe Your Space (genjson tiers 0–2)

Status: ready-for-dev — OD-1 resolved: home copies genjson

## Story

As a space coordinator,
I want to describe my space and see its card as a visitor will,
So that I have something worth keeping before anyone asks me to keep it.

## Context

genjson already is tile A: tiers 0 (name + address → coordinates), 1 (SpaceAPI core), 2 (`mom:` fields),
Nominatim proxy, localStorage draft and resume, Bernard's copy (`bernard_copy.yaml`), schema validation.
OD-1 (2026-10-29): home **copies** it. The wizard's code, copy, fonts and schema move into the home
app as tile A's workbench; genjson is then retired (Story 14.8).

## Acceptance Criteria

### AC1 — No account to begin
**Then** tile A asks for nothing but the space: no email, no password, no sign-up.

### AC2 — genjson's fields and voice, unchanged
**Then** the fields, hints, tier gates, geocoding and Bernard's lines are genjson's
(bible §5: Bernard names themselves once, on entry).

### AC3 — The card preview
**When** tier 0 is complete
**Then** the workbench shows the space's card as the map will render it, built from the draft, labelled
"Preview · nothing is published", plus the profile facts (description, hours, next event)
**And** Bernard names the stakes and gives one way out, no menu: "That's you, the way a visitor will see
it. For now it only lives in this browser. Nobody else can see it." then "Want it out there for real?",
with "Publish it →" and a plain "Fix something first"
**And** tile A is done; tile B opens.

### AC4 — The draft survives
**Then** the draft keeps genjson's key and shape (`genjson_draft`) on the home origin, so resume works
as it does in genjson today.

### AC5 — One copy of Bernard
**Then** genjson's `bernard_copy.yaml` is carried into `web/home/onboarding.ttl` (14.1 AC2: the app's single
source for Bernard's lines); no YAML or generated JSON copy remains in the app
**And** `tests/test_bernard_voice_completeness.py` reads the Turtle
**And** the Playwright gate from Story 9.3 (`test_wizard_tier0_tier1_export`) runs against home.

## Dev Notes
- Bernard's tile A line in the dry run was cut (2026-10-29, too much): the wizard intro and genjson's own
  floor-gate beats carry tile A; the tree has no `onb:say` for it.
- `machines`/equipment is a tier 3 field (Story 9.10, deferred). The dry run no longer asks for it.
- The export shape is genjson's: `doc.mom = { opening_hours, memberOf }`, never the flat CURIE key
  (Story 9.6 key-shape contract).
