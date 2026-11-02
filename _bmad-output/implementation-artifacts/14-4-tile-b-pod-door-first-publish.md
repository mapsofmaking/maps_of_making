# Story 14.4: Tile B, Pod Door — First Publish (sign in, write, make public, register)

Status: ready-for-dev (2026-11-03). Its dependencies are live: 14.2 (tile A), 14.3 (account, pod, sign-in; in
`review`, flow B and Safari/iOS still to test), 14.7 (the map reads Turtle). Sign-in follows the flow observed in
14.0 (`14-0-spike-report.md`).

## Story

As a space coordinator whose pod was just created,
I want my space's file written there, public, and on the map,
So that I leave tile B with my space live on the map.

## Context: where 14.3 leaves us

14.3 (live 2026-11-02, `mom-home` `sha-cd34baa`) creates the account and the pod, signs the coordinator in
through the pod server, and brings them back to home signed in with tile B saying "the pod is ready, nothing is
written in it yet". **This story starts there.** What 14.3 did not do, and this story must:

- **Nothing is written.** The description typed in tile A is still only in this browser (`mom-home:draft`, 30
  days, handed to the workbench). 14.3 review: it is the only copy until this story writes it, so it is cleared
  only after the file is written and read back.
- **The hexes still say tile A is not done** after sign-in (the done checks read the pod, and the pod has
  nothing). `src/main.ts` passes `space: null` to `readDone` ("the lookup and the card come with 14.3/14.4",
  `src/tiles/done.ts`). Writing the file and registering it in the Type Index closes the gap (AC6).
- **"Pod ready" is a one-shot tab marker** (`lib/handoff.ts`), not derived from the pod: the review deferred it
  here. After AC6 the pod itself tells.

What is reusable as it stands (read before writing anything new):
- `src/lib/auth.ts` `authFetch`, `getSession`; `src/lib/pod.ts` `getPrimaryPodUrl`, `ensureContainer`, `slugify`;
- `src/lib/conditional.ts` `readWithEtag`, `writeIfMatch`, `updateDocument` (read, change, `If-Match`, one PUT);
- `src/settings/home.ts`: the pattern for a first write (file, then README, then Type Index), `findPrivateTypeIndex`,
  `registerInTypeIndex`, `registrationTurtle`; the settings 404 on a brand-new pod is expected and handled;
- `src/lib/read.ts` `readTurtle` (ETag-revalidated reads), `src/lib/draft.ts`, `src/lib/handoff.ts`;
- the page's state pattern (`page.ts`: `creating`, `made`, `pod`, in-place messages, tile navigation blocked while a
  request is in flight): the same rules hold for the publish steps (14.3 review).

## Acceptance Criteria

### AC1 — Signed in, and one button
**When** the coordinator is back on home signed in, with the pod just made (14.3 AC6)
**Then** tile B offers one primary action, "Put it on the map" (words in the tree), which runs AC2 to AC4b in
order and shows each step as it goes (a step list, same idiom as the storyboard's B2 right column, each step
done, working or failed)
**And** the sign-in itself belongs to 14.3 (the pod server as issuer, consent page naming `home.mapsofmaking.org`,
kit ADR 010 point 6); OD-2 (14.0): consent only after the account-API login (flow A), the provider's login first
when the browser drops the cookie (flow B, still to test; Safari unverified). A session that has expired mid-way
says so and signs in again from the failed step (AC5), never from the start.

### AC2 — The file
**Then** the app writes `space.ttl` at the pod root from the tile A draft (decided 2026-10-30: the pod is
linked-data native, so later tiles read and write links without JSON parsing). The mapping is the Turtle
column of [`docs/reference/space-file.md`](../../docs/reference/space-file.md) and must satisfy 14.7's
validation (a name, coordinates); the subject is `<space.ttl#space>`, typed `mom:Space, schema:Place`
**And** the file is created with `If-None-Match: *`: a second press never overwrites a file the coordinator (or
tile C) already edited; an existing file is read and, when it already says the same, left alone
**And** the draft's values are normalised the way the file needs them: website and logo only `http(s)` IRIs (a
`javascript:` or `data:` value is dropped with a message, 14.2 review), Matrix as the `matrix.to` link, the
address node flattened as 14.7 reads it, and a country that came from the geocoder or was typed by hand
(14.2 review: a draft whose geocoder answer had no country hides the typed one: fix it where the draft is read)
**And** the file is not the WebID document: `/profile/` holds the account's identity and sign-in data, and the
space can change hands or gain managers. **How other apps find it** (decision to confirm, replaces "the WebID
document links to the space file"): a Type Index registration, `solid:forClass mom:Space`, `solid:instance
<…/space.ttl#space>`, the same mechanism `settings/mom-home.ttl` already uses; no write to the WebID document.

### AC3 — Public by default, and only that
**Then** the app writes a resource ACL giving public read on `space.ttl` alone, hand-written Turtle
(kit ADR 003, whose four rules hold: the target is the file's own name, never `./`; the owner block with Read,
Write and Control is always re-emitted; an ACL the app does not understand is refused, not rewritten; WebIDs are
validated before they are spliced in); the rest of the pod stays private
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
**Then** sign-in, write, ACL, the anonymous check, register and the Type Index each report their own failure
with a way forward (Bernard's voice, red only for errors, one action), and a retry resumes from the failed step:
each step first asks the pod or the map whether it is already done (the file exists and says the same, the ACL
grants public read, the URL is registered: `register-url` dedups by endpoint, see `_find_graph_by_endpoint`)
**And** one press at a time (a second press while a step runs does nothing), the way "Create it" is held in 14.3;
tile navigation waits while a step is in flight, so an answer never lands on a replaced screen (14.3 review)
**And** a 401 or 403 from the pod is told apart from a missing resource (`isAuthError`): an expired token means
"sign in again", never "the file is missing".

### AC6 — Done is read from the pod, never stored (closes 14.3's gap)
**Then** `src/main.ts` finds the space through the Type Index (`solid:forClass mom:Space`) and passes it to
`readDone` as `space`; `keep` is done when the space file is registered there and readable, `describe` when the
file says a name and an address (`src/tiles/done.ts`, replacing the two stubs `ctx.space !== null`); tile A and
tile B show done after sign-in, on any browser, with the tab's marker gone
**And** the one-shot "pod ready" panel (14.3) gives way to the threshold of AC4b the first time, and to the
workbench afterwards
**And** the word "pod" unlocks from this (it unlocks after tile B is done, `onb:unlocksWord`).

### AC — The writer is held to the map's reading
**Then** the Turtle the app writes is tested against `tests/fixtures/space/atelier-du-canal.ttl`
(maps_of_making; copy it into mom-home pinned to a commit, like the design system): the same draft values
give the same file, and the map's parser reads it to the statements in `atelier-du-canal.json`
(Story 14.7's parity test, `tests/test_space_turtle.py`).

## Tasks

Built in `mom-home` (`/var/home/nicolas/github/mom-home`), one vertical slice at a time, each reviewed live by
Nicolas before the next (feedback: review each slice). Tests with each slice; `npm run verify` is the gate. Run
vitest with `--root` (a wrong root scans the whole disk and runs out of memory). Slices land as small PRs; Nicolas
merges, then the image is deployed by bumping `HOME_TAG` on the VPS.

- [ ] **S1 The file.** `lib/spacefile.ts`: draft → Turtle (the normalisers of AC2, deterministic, no clock), tested
  against `tests/fixtures/space/atelier-du-canal.ttl` copied into mom-home pinned to a maps_of_making commit (the
  same draft values give the same file; the map's parser reads it to `atelier-du-canal.json`'s statements, 14.7's
  parity test). The "Put it on the map" button on the signed-in tile B view writes `space.ttl` (`If-None-Match: *`),
  reads it back, and shows the step. AC1, AC2.
- [ ] **S2 Public read.** `lib/acl.ts`: a helper that takes a resource (14.6 reuses it for a logo), hand-written WAC
  Turtle per ADR 003; writes `space.ttl.acl`; then an anonymous `fetch` (`credentials: "omit"`) must return 200
  before the next step. AC3. Test the four ADR rules and the refusal.
- [ ] **S3 On the map.** `POST /api/register-url` through home's own `/api/` proxy; the response's `space_uri`
  (`urn:mak:space/<slug>`) gives the id for `https://mapsofmaking.org/?space=<slug>`; the threshold view (pin read
  back from the map, labelled live; the file's address as a `Copyable`; "See it on the map ↗"; Bernard's closing line
  and "Update it once →" to tile C); the "pod" word unlocks. AC4, AC4b.
- [ ] **S4 Done from the pod.** Type Index registration of the space, the lookup in `main.ts`, the two done checks,
  the draft cleared after the file is written and read back, the tab marker retired. AC6.
- [ ] **S5 Failures and resume.** The step list with each failure message in the tree, resume from the failed step,
  expired session, one press at a time; tests for every row of AC5. AC5.
- [ ] **S6 Live run on production** against `pod.mapsofmaking.org` with a throwaway account (flow A in Chromium,
  Firefox, WebKit; flow B, deferred from 14.3, run here first), phone width, then the polish pass Nicolas planned at
  the end of this story (the small details of 14.3 and 14.4 together).

## Dev Notes

- **Order of the steps, and why:** file, ACL, anonymous check, register, Type Index. The map fetches the file
  without credentials, so the anonymous 200 must precede `register-url` (`follow_redirects=False` holds because a
  pod answers directly). The Type Index goes last: it makes the pod say "published", so it must not say it before
  the map has the space.
- **The map's id:** `register-url` answers `{status, space_uri, space_name, ...}`; the deep link is
  `https://mapsofmaking.org/?space=<s.id>` (`web/app.js`), and `s.id` is the slug after `urn:mak:space/`. The
  initial heartbeat and the geojson rematerialize run after the response (background): the pin may take a moment,
  so "read back from the map" polls briefly (bounded) and says "on its way" rather than drawing a pin that isn't
  there.
- **Writes use `authFetch` with `cache: "no-store"`;** one document, one conditional PUT. The `.acl` is its own
  document next to the file; creating it needs Control on the pod, which the owner has.
- **CSS specifics:** a new pod's root ACL is owner-only; the per-resource `.acl` overrides inheritance for that file
  only. `Content-Type: text/turtle` on every PUT. A PUT on a missing container creates its parents.
- **The draft is data, not progress:** it is the source of the file, never what says "done" (14.3 review).
- **Words:** every line the steps show lives in `public/onboarding.ttl` (`onb:ui*`, `onb:say*`); a voice test reads
  them (no em-dash, no cheering); a new line is an edit to the tree, never to code. Bernard's AC4b lines are already
  in the tree (`saidDone`, `sayNext`).
- **What not to do:** do not write the WebID document; do not make the ACL public on a container; do not retry
  `register-url` automatically on a 4xx; do not keep any secret (there is none to keep here: the session holds the
  access).
- **Carried here by earlier reviews:** 14.2 (validate website/logo schemes at the write; the resumed-draft country
  quirk), 14.3 (pod ready from the pod, not the marker; the draft prefilled for another WebID's workbench moves to the
  pod; typed passphrases dropped on tile navigation, a polish item). Heartbeat and `/.account/` hardening are 14.9's.

### Open questions for Nicolas (not blocking S1)
1. **Type Index, not a WebID-document link** (AC2): confirm. It keeps `/profile/` untouched, which is the safer
   write, and `settings/mom-home.ttl` already does it.
2. **After a successful publish, is the draft cleared from the browser?** Proposed: yes, once the file is read back;
   "Start over" in tile A then reads the pod.
3. **The closing line:** AC4b's Bernard text says "stuff happen" (decided 2026-10-30): fix the grammar to "stuff
   happens"?

## Done gate
A new coordinator, on a phone, goes from tile A to their pin opened on the map, against
`pod.mapsofmaking.org`, without copying anything.
