# Story 14.3: Tile B, Pod Door — One-Step Account, Password, WebID and Pod

Status: backlog — 14.0 spike done (report `14-0-spike-report.md`, 2026-10-31)

## Story

As a space coordinator who chose "We look after it, you hold the key",
I want to give an address, an email and a passphrase, and nothing else,
So that my space has a home of its own without a sign-up form.

## Context

pocpod0 (`backoffice/pod-api.js`, `Solid.registerAccount`, branch `vps-mode`) proved the sequence against
CSS's account API: create the account → add the password login → create the pod (which creates the WebID).
Port it, with its live-found guards, into the app (later into solid-kit as `lib/register.ts`).

## Acceptance Criteria

### AC1 — Two equal doors, and a real "not now"
**Then** tile B ("Publish it") shows "Take the file, look after it yourself" and "We look after it, you
hold the key" with the same weight, no badge (bible §3: never rank the user's choices); the choice is who
looks after the file, never the technology
**And** "Not now" is a real answer: "Fine too. It stays in this browser until you clear it. Nothing was
sent."

### AC2 — Only what's missing
**When** the coordinator picks the pod door
**Then** three fields show: the space's address (suggested from the space name, slugged, accents folded,
editable, the full `https://<name>.pod.mapsofmaking.org` shown live), the email (prefilled from tier 1
`contact.email`, hint: the space's mailbox, so the space can change hands), and a passphrase typed twice,
with a Show toggle (eight characters minimum, no spaces; example `Rock-Paper-Scissors-Lizard-Spock`; hint:
"A few ordinary words joined by dashes beat one clever password.")
**And** nothing else is asked
**And** the address is checked as it is typed (after a short pause) and when the field is left, and the
suggested one as soon as the form opens: "taken" or a bad format shows on that field before the
passphrase is reached, and a free address says so beside the live URL (decided 2026-10-30: a taken name
found only after "Create it" makes the coordinator redo the passphrase). **14.0 found CSS 7.2 cannot
answer "is this name free" without creating anything**: a HEAD on `https://<name>.pod.mapsofmaking.org/`
answers `401` for free and taken names alike (wildcard), and the account API has no check. Until the
provider offers one (solid-css-overlay), the format is checked live and "taken" shows after "Create it",
on the address field, with the passphrase kept (the next line; fallback accepted by Nicolas, 2026-10-31); "Create it" handles a name taken in
between either way
**And** no error clears a field: errors update in place, the passphrase fields keep what was typed.
**And** before "Create it", Bernard warns about the consent page: the pod's own page will ask whether
`home.mapsofmaking.org` may use the pod; that is this app asking to write the profile, and the answer is
yes. Wording (Nicolas, 2026-10-31, after 14.0), `onb:sayConsent`: "Your pod opens its own page now. If it asks for your passphrase, use the one you just made. Then press Authorize for home.mapsofmaking.org." It holds for both flows 14.0
observed (consent only, or log in then consent); the pod's pages say "passphrase" too
(solid-css-overlay #27).

### AC3 — One step, resumable
**When** they submit
**Then** the app calls the account API in order (create account → password → pod) with the account token
CSS returns at creation, then **logs in through the account API** (`controls.password.login`, with
`credentials: "include"`): that login, not the creation, sets the `css-account` cookie, which spares the
coordinator the provider's login page (14.0: flow A in Chromium, Firefox and WebKit with it, flow B without),
keeps the half-built account for the session (not per pod name: after "taken", the
retry uses another name on the same account; pocpod0 keys it per pod name, which orphans an account) so a
retry resumes rather than duplicates, and never stores, shows or resends the passphrase
**And** an empty pod name never reaches the network (CSS treats it as "claim the pod root", found live
2026-07-22).

### AC4 — The provider says whether it takes accounts
**Given** kit ADR 010 point 1 and the `register` entry (amendment point 9)
**When** the instance does not offer account creation
**Then** tile B says so before any field, and offers the self-host door.

### AC5 — Failures with a way forward
**Then** a taken address, a refused email, a weak passphrase, an unreachable provider and a half-finished
creation each have their own message (Bernard voice, red only for errors) and one action.

## Dev Notes
- Same-site is the boundary (kit ADR 010 point 3): this only works because `home.` and `pod.` share
  `mapsofmaking.org`.
- Gateway rate limiting on `/.account/` before the door is public (amendment, risks).
