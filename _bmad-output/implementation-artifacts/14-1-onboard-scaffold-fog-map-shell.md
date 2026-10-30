# Story 14.1: Onboard Scaffold + Fog Map Shell (tree, done checks, words)

Status: backlog

## Story

As a space coordinator arriving at `home.mapsofmaking.org`,
I want to see where I stand, what I can do now and a hint of what comes after,
So that I start with one obvious step and discover the rest by doing, not by reading.

## Context

The "Onboard Storyboard" design canvas (https://claude.ai/artifact/4XunMfUzzmjBk7PVjYfjvW) is the reference for layout, copy and tile looks, built from the Maps of Making design system (https://claude.ai/artifact/XmBwSPHVtcMzxgWUgsmprN, v10: Workbench group); the dry-run artifact ("Maps of Making Dry
Run") stays the reference for behaviour. This story builds the shell for real: the map, the workbench, the
words strip, the tree. No tile does anything real yet; each
shows its preview, labelled. Stories 14.2–14.6 turn tiles real one at a time.

## Acceptance Criteria

### AC1 — App scaffold from solid-kit
**Given** solid-kit is copied, not packaged (kit ADR 004)
**When** the app is created
**Then** it is routed like genjson is today: a host rule in `infra/web/Caddyfile` (keeping `/api/` on its
own host) and a gateway vhost modelled on `08-genjson-mapsofmaking.conf`, so the page calls `/api/` on
`home.` and no CORS is added to link_handler
**And** `SESSION_ID` is unique to this app (kit CLAUDE.md: shared ids clobber tokens)
**And** a Client ID Document is served at `https://home.mapsofmaking.org/id.jsonld` listing the app's
redirect URI (kit ADR 010 point 6), for the sign-in in 14.4
**And** the app pins a kit version.

### AC1b — One app, two modes
**Then** the session decides the mode: signed out, the page is onboarding (tiles A, B, then the threshold);
signed in through the pod, the same page is the workbench. A returning coordinator never steps through
onboarding again
**And** signed out, the header carries a quiet "On the map already? Sign in"; signed in, it shows "Signed in
as <space name>" and "Sign out"
**And** the header reads `maps of making` + `home`.

### AC2 — The tree is Turtle, and lives with the app
**Given** the tile tree drafted in the session
**When** the app loads
**Then** it reads `web/home/onboarding.ttl` (published with the app) and builds tiles, requirements
(`onb:requiresAll` / `onb:requiresAny`), cues, Bernard's lines and words from it
**And** that file is the single source of every Bernard line the app speaks, tile A's form copy included
(decided 2026-10-30): forking the app for another vertical means swapping one file
**And** `onb:` is declared in that file as a draft namespace, not in solid-kit (the kit refuses
vocabularies) and not in `ontology/` (a subtree of the org's ontology repo, updated by `make
ontology-pull`); the vocabulary moves to the ontology repo once it is stable
**And** there are no levels: the designer-only `onb:level` is dropped; a tile states real consequences in
plain words instead (e.g. "Needs your network to say yes")
**And** a tree that fails to parse shows an error with a way forward, never a blank map.

### AC3 — Fog rules
**Then** a tile is open when its requirements are met, at most three at a time by `onb:prio`; the rest wait
as cues and say "ready" when only the limit holds them
**And** a tile whose requirement is open or done shows as a cue (outcome only, never mechanism)
**And** `onb:emergent` and `onb:planned` tiles never open
**And** the tally shows cleared and open counts, never a total.

### AC4 — Done is read from the pod
**Given** "the pod is the map"
**When** a signed-in coordinator returns
**Then** each tile's state comes from a done check keyed by tile id (`src/tiles/done.ts`), reading the
pod, not from stored progress
**And** `onb:doneWhen` stays in the tree as documentation; SPARQL/SHACL evaluation is out of scope
**And** with nobody signed in, state lives in memory and in genjson's draft (per OD-1)
**And** every tile after B follows one cycle (Part 2): first open = a short tutorial, plus setup if the tile
needs it; done is written in the pod; reopened later, the tile opens straight onto its tool
**And** "done" is derived from the space's own data wherever a `doneWhen` can say it (no flag, no badge);
what can't be derived (a tutorial dismissed, a hint closed) goes in one owner-only file,
`settings/home.ttl`, created on first need with `settings/README.md` (never over one already there),
written by conditional whole-document writes, the solid-backoffice pattern (`settings/collectives.ttl`);
if the profile has a private Type Index, the file is registered there for other apps; `pim:preferencesFile`
is left to the pod (decided 2026-10-30).

### AC5 — Words you've met
**Then** the words strip is hidden until a first word unlocks, and a word unlocks right after the tile that
shows what it names (`onb:unlocksWord`)
**And** words are design-system `WordChip`s (status-label sized; met = done-tint under an ink rule, not met
= dashed dots), the meaning in a tip after 1 s hover, at once on keyboard focus, on tap; never the
browser's `title`
**And** the words live under the full hex view and are hidden when it folds.

### AC6 — Previews are labelled
**Then** every tile not yet real renders its preview with "Preview · nothing is published" and the chip
COMING.

### AC7 — The hex view, as drawn
**Then** the hex view is titled "What you can do" (not "map": that is mapsofmaking.org) and draws tiles in
riso style: done = green tint printed slightly off an ink outline, with ✓; open = white, bold ink outline;
coming = dashed muted outline on paper; still to discover = halftone dots; selected = 4px outline, no
shadow. Riso red only for errors and focus
**And** desktop is 50/50: hex view and workbench side by side, both panels with the hard shadow; the hex
column holds still and only the workbench scrolls (one screen at 1600×900)
**And** on a phone, and in the signed-in workbench, the hex view folds into a row of small hexes with "+ N
to discover" (also where new features appear as they are built), "Now: <step>" and "See all ›", which opens
the full view as a sheet
**And** signed in, the folded row is the design system's `HexRow` toolbar: one 52px line, done and open
tiles carry their `TilePicto` (named by `onb:icon`), the tile name shows on hover or focus, a click opens
the tile; a tile's first open (its tutorial) keeps the full view, its tool opens folded.

## Tasks
- [ ] Scaffold from solid-kit; config, Client ID Document, vhost, compose service
- [ ] `web/home/onboarding.ttl` + namespace note; parse with N3 (pinned) at load
- [ ] Hex view, workbench, words: port from the storyboard (looks, copy) and the dry run (behaviour)
- [ ] `done.ts` registry with a stub per tile; tests for the fog rules (kit: add the test with the code)
- [ ] Live check: loads on a phone, light and dark, keyboard only

## Dev Notes
- The dry run's preview functions are the copy reference. Keep them as data where the kit pattern allows
  (kit `ux-principles.md`: concept screens as data).
- The fog map becomes a solid-kit pattern only after this slice is tested (Nicolas, 2026-10-29).
- Naming: the connector has an `/onboard/` *path* on the pod server (kit ADR 010). The app is "home"
  (`home.mapsofmaking.org`, 2026-10-30), which also removes the clash.
- Workbench vs backoffice: the backoffice is the under-the-hood file manager; the workbench is intent-led
  shortcuts for non-technical coordinators. Both write the same card through one shared write layer.
