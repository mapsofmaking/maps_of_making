# Story 14.3: Tile B, Pod Door — One-Step Account, Password, WebID and Pod

Status: ready-for-dev (2026-11-02; 14.0 spike done, report `14-0-spike-report.md`; 14.7 live, so 14.4 can follow)

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
retry resumes rather than duplicates, and never stores or shows the passphrase (it is sent twice, once to add the login and once to the login that sets the cookie, both to the same server and neither kept: ADR 010 point 8 says "once", which this story's own login step needs; to be reconciled in the kit's ADR)
**And** an empty pod name never reaches the network (CSS treats it as "claim the pod root", found live
2026-07-22).

### AC4 — The provider says whether it takes accounts
**Given** kit ADR 010 point 1 and the `register` entry (amendment point 9)
**When** the instance does not offer account creation
**Then** tile B says so before any field, and offers the self-host door.

### AC5 — Failures with a way forward
**Then** a taken address, a refused email, a weak passphrase, an unreachable provider and a half-finished
creation each have their own message (Bernard voice, red only for errors) and one action.

### AC6 — The hand-off to 14.4
**When** the pod exists
**Then** the app signs in with Solid-OIDC (`loginWithIdentifier`, the pod server as the issuer, not the new WebID: a pod seconds old has no profile to read yet; redirect back to home), after `onb:sayConsent`
**And** back on home, signed in, tile B says the pod is ready and nothing has been written yet (new tree line, system voice or Bernard's, Nicolas picks the wording at review); "Publish it" itself is 14.4
**And** the draft is still there (14.2 AC7, 30 days), and tile B's state is not stored as progress: the signed-in WebID and its pod root show it (`getPrimaryPodUrl`)
**And** the `keep` done check stays as it is: a pod proves nothing about publication (done.ts comment); 14.4 owns it.

## Prerequisites outside this repo (slice S0)

Found 2026-11-02 against production, not in the story's first draft:

- **The descriptor has no `register` entry.** `https://pod.mapsofmaking.org/.well-known/css/provider.json`
  (version 7.2.0-12) lists `account`, `onboard`, `connector` only. ADR 010 point 9 says the entry is written
  when registration is on; `solid-css-overlay` has no code for it yet (grep of `overlay/`, `docs/`, CHANGELOG).
  Until it ships, AC4 always says "no". Work: solid-css-overlay adds `register` (+ `scripts/check-overrides.sh`
  check), new image, `mom-pods` updated (vps-infra).
- **No rate limit on `/.account/`.** `vps-infra/gateway/sites/mom-pods.caddy` has none; ADR 010 point 11
  requires one before `register` is listed publicly, and `account.create` is anonymous and unconditional (every
  POST makes an account). Work: Caddy rate limit on `/.account/` creation paths, per client IP.
- **Credentialed CORS on production.** The spike proved `access-control-allow-origin: https://home.mapsofmaking.org`
  + `allow-credentials: true` on `pod-test` (7.2.0-9); production was at 7.2.0-11/-12 since. Re-check on
  `pod.mapsofmaking.org` before S2 (one `curl -i -H 'Origin: https://home.mapsofmaking.org'`).
- Both overlay and infra changes are Nicolas's call to deploy; this story does not deploy them.

## Tasks

Built in mom-home, one vertical slice at a time, each reviewed live by Nicolas before the next (feedback: review each slice).

- [x] S0 prerequisites above, live 2026-11-02: solid-css-overlay 7.2.0-13 (PR #29, tag `v7.2.0-13`, `mom-pods`
  updated, `OPEN_REGISTRATION=true` in `/srv/mom-pods/instance-template/.env`); `provider.json` lists
  `register` `{path: /.account/, podNames: subdomain}`; gateway rebuilt with caddy-ratelimit (vps-infra PR #11),
  `account_create` 5/h and `account_build` 20/h per IP, live-tested (20 pass, then 429 + Retry-After);
  CORS from the home origin re-checked. The `account_build` paths (`account/<id>/login/password/`,
  `account/<id>/pod/`) are still checked only against CSS conventions: S5 confirms them with a real account.
  Side effect: the test used this workstation's `account_build` bucket for an hour.
- [x] S1 (live 2026-11-02: mom-home PR #3, `sha-547f61f`; the first cut overrode the design system's door markup in `home.css`, so it looked bare next to storyboard B1; S2 restores B1's title / description / where, see Review notes) Tile B's two doors and "Not now" (AC1, AC4): new tile B view in `src/workbench/` (follow `describe.ts` / `step.ts`); the descriptor read (`/.well-known/css/provider.json`, new `src/lib/provider.ts`, unknown or unreachable = "no", with its own message); words in `public/onboarding.ttl` as `onb:field` / `onb:ui*` nodes, never in code (14.2 AC8; the voice test in `src/tree/voice.test.ts` extends to them). Doors get equal weight, no badge, no default focus on either.
- [x] S2 (live 2026-11-02: mom-home PR #4, `sha-f381274`; 306 tests, 54 audit checks; sends nothing, "Create it" validates and says creation comes next) The pod form (AC2): address suggested from the space name with `slugify` (`src/lib/pod.ts`), live URL, email prefilled from the draft's `contact.email`, passphrase twice with Show; format checked as typed (debounced) and on blur with the server's rules (`PodNameGuard`: `^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$`, reserved names are the server's, its answer wins); "taken" shows after "Create it" (14.0: no free-name check exists); fields keep what was typed on every error; `onb:sayConsent` shown before the button.
- [x] S3 (live 2026-11-02 with S4: mom-home PR #5, `sha-33dae4e`; built as `33745fc` on branch `epic-14-14-3-s3-register`; 323 tests, 54 audit checks; until S4, success says the pod is ready and stops; live probe 2026-11-02 from Node against `pod.mapsofmaking.org`: `nicolas-test` answered 400 "Pod creation failed: There already is a resource at …" → `name-taken`, the retry reused the same account (no second passphrase POST), the pod was made, the account-API login answered 200; throwaway accounts `zz-s3-probe-*` and one orphan from a rate-limited try, both gone with the pre-launch wipe; the cookie itself is checked in a browser in S5) `src/lib/register.ts` (AC3, AC5): copy of solid-backoffice `src/lib/css-account.ts` (`createAccount`; the TypeScript port of pocpod0's `registerAccount`, already resuming on the same account for the page's life and tested against a real CSS 7 by `npm run test:pods`; pocpod0 is retired, and solid-css-overlay is the server, whose own sign-up page is CSS's stock flow). Check and add what it lacks: resume state keyed by session, not pod name; login through the account API right after the pod (`controls.password.login`, `credentials: "include"`) to set `css-account`; passphrase never stored, logged or kept after the POST. Empty name throws before any fetch. One error type per AC5 case (taken, email refused, weak passphrase, unreachable, half-finished), each with one action.
- [x] S4 (live 2026-11-02, mom-home PR #5, `sha-33dae4e`; 333 tests; tab-only marker `mom-home:pod-made` holds WebID + pod; tile A is NOT marked done from the browser draft, so until 14.4 the hexes show A open while the step shows B's hand-off) Hand-off (AC6): sign-in redirect, the return state, tile B "pod ready" view; check the draft survives the round trip.
- [~] S5, run 2026-11-02 on production (`home.` `sha-33dae4e`, `pod.` 7.2.0-13, gateway with the CORS 429), Playwright 1.64.1:
  - Chromium, flow A: "Taken. Try nicolas-test-anderlecht." on the address, email locked, consent only (no login page),
    Authorize, back home signed in, tile B says the pod is ready; marker spent. 11.4 s.
  - WebKit (Playwright's Ubuntu image), flow A: the same, consent only. 16.0 s.
  - Firefox (same image), flow A: the same, consent only. 11.7 s. Failed requests on the way: the expected 400 on the taken
    name, and `404 GET <pod>/settings/mom-home.ttl` (home reading its settings file on a brand-new pod, handled: the
    fold falls back to the width).
  - Not yet: flow B (the cookie really cleared before the provider's page). Two attempts: the first dropped the wrong
    thing (`route.fetch` shares the cookie jar), the second (`s5b.py`, `context.clear_cookies` on the first provider
    document) hit the rate limit (5 creations per IP per hour) before reaching the form. Rerun after the window.
  - Safari on iOS and macOS: deferred, nobody on the project has a device (`mom-home` `docs/manual-tests.md` §12).
  - Throwaway accounts made: `zz-s5-*` (Chromium, WebKit, Firefox, the flow B attempts), `zz-s3-probe-*`, one orphan from a
    rate-limited try; all go with the pre-launch wipe.
- [ ] S5 (decided 2026-11-02: on `pod.mapsofmaking.org` itself, with throwaway accounts; the instance is wiped before launch, it holds only `nicolas-test` today) Live check on production, Playwright, Chromium + Firefox (+ WebKit image if available): name taken, name free, email refused, retry on the same account, flow A (cookie kept) and flow B (cookie cleared); then the manual-tests entry (`docs/manual-tests.md`) for Safari on iOS, which 14.0 could not verify.

## Review notes

- **Storyboard vs story (2026-11-02).** The Onboard Storyboard (B1, B2, S2-Error) is the layout and copy reference;
  where it disagrees with this story, the story wins (its decisions are dated after 14.0):
  - consent: the tree's `onb:sayConsent` (Nicolas, 2026-10-31), not B2's "Heads up…";
  - B2's two-step list ("Say yes… One click" / "Your profile is written, public, and on the map") is not built:
    step 2 is 14.4's outcome (this story ends at "pod ready, nothing written", AC6) and "one click" is false in flow B;
  - B2's "Strong." passphrase label is not built: nothing measures strength, the rule is eight characters, no spaces;
  - no "free" message beside the address: nothing can check availability (14.0), so only the live URL and the format.
- **S1's first cut overrode the design system's door markup** in `home.css` and looked bare next to B1; S2 uses
  `.wb-door-title / -desc / -where` as B1 does and drops the override.
- **Form state:** the address and email live in the page (`pod`), flagged `touched` once typed so a later change to the
  description no longer overwrites them; the passphrase only in its input, never in page state, the draft or storage.
  The form never submits natively (a GET would put the passphrase in the URL); tests cover Enter.
- **Left for S3:** the account calls, "taken" and the other AC5 messages, `lib/register.ts`.

### Review Findings

Patched 2026-11-02 in mom-home PR #6 (`60f2409`, 353 tests) and vps-infra PR #13 (gateway: slash-less paths, IPv6 /64, 429 CORS to the home origin only; the /64 grouping is validated as config only).

Code review 2026-11-02 (Blind Hunter, Edge Case Hunter, Acceptance Auditor in parallel) of mom-home S1-S4 + PR #6,
solid-css-overlay #29, vps-infra #11/#12. 41 raw findings; 17 patch, 1 decision, 10 defer, 13 dismissed.

- [x] [Review][Decision] (Nicolas, 2026-11-02: option (a), email recovery stays the safety net) A pod made in this tab, then the provider page abandoned: coming back signed out shows the empty form, and "Create it" with another email makes a SECOND undeletable account (same email says "email taken", which is the right recovery). Options: (a) show "You made a pod here: <address>. Sign in to it." with a Sign in action while the tab marker is unread, form behind "make another"; (b) accept: deliberate action, bounded by the rate limit. [register.ts, main.ts, handoff.ts]
- [x] [Review][Patch] `markPodMade` / `takePodMade` evaluate `globalThis.sessionStorage` in a default parameter, outside the try: blocked storage throws after the pod exists (shown as "account exists, pod isn't made", sign-in never starts) and throws in main.ts (error screen) [handoff.ts:22,30]
- [x] [Review][Patch] Unguarded `.json()` calls and `pending` set only after the token parses: a non-JSON body at account creation leaves an orphan and the retry makes a second account; at the pod step it keeps `pending` after the pod exists. Parse safely, set `pending` the moment the token is known, clear it when the pod exists [register.ts:172,176,187,220]
- [x] [Review][Patch] "Nothing was created" is claimed when the request failed with no answer (the server may have created the account before the reply was lost): reword `uiUnreachable` without the claim [onboarding.ttl, register.ts]
- [x] [Review][Patch] A stale or refused account token (401/403 on the controls call) loops on "press Create it again": clear `pending` and say the account can't be continued here (sign in at the pod with the email, or use another) [register.ts:187]
- [x] [Review][Patch] A server refusal at the passphrase step becomes `provider` ("half done, press again", a retry that cannot succeed): map email and passphrase refusals to `bad-email` / `bad-password` (AC5) [register.ts:~196]
- [x] [Review][Patch] A redraw during an in-flight create (tile click, offers answering) loses the outcome: success skips the hand-off marker and sign-in, errors vanish. Ignore tile navigation and offers-redraws while creating; finish the success path whether or not the form is still on the page [page.ts:create, select]
- [x] [Review][Patch] After `made`, a redrawn form says "Create it" but signs in: render "Sign in" from `made`; the held email stays read-only across redraws (store it in the form state) [page.ts, podform.ts]
- [x] [Review][Patch] `podReady` is passed on every draw: tile B is stuck on "pod ready" for the page's life. Show it once; leaving tile B clears it [page.ts, step.ts]
- [x] [Review][Patch] Hand-off marker: expire after 15 minutes; a different WebID's sign-in must not consume it; `pod` from storage must be an https URL before it becomes an href [handoff.ts, threshold.ts]
- [x] [Review][Patch] `signInNow` is not guarded: two submits can start two OIDC redirects [page.ts]
- [x] [Review][Patch] No timeouts: a hung server leaves "Create it" disabled forever and "Asking the pod server" with no "Try again". Time out every fetch in register.ts and provider.ts (20 s), as `unreachable` / `down` [register.ts, provider.ts]
- [x] [Review][Patch] Descriptor `register` is half honoured: require `path === "/.account/"` and `podNames === "subdomain"` (the only layout this app builds), else `closed`; a protocol-relative `//x` passes today [provider.ts]
- [x] [Review][Patch] Control URLs from the server (`account.create`, `password.login`, ...) are fetched with credentials and the passphrase without checking they are on the issuer's origin [register.ts]
- [x] [Review][Patch] Small: shared `EMAIL` / minimum passphrase between register.ts and podform.ts; Show resets to hidden after success; `takenSuggestion` skips a town already at the end; `bad-name` case as an explicit if [podform.ts, register.ts]
- [x] [Review][Patch] Story text: AC6 says "the new WebID as identifier" but sign-in uses the issuer (a pod seconds old); the passphrase is sent to the password step and again to the login (AC3 requires the login, ADR 010 point 8 says "once"): record both in the story [14-3 story]
- [x] [Review][Patch] vps-infra hardening: add `ipv6_prefix 64` to both zones, match `/.account/account` without the trailing slash, and restrict the 429's CORS echo to the home origin [mom-pods.caddy]
- [x] [Review][Defer] "Pod ready" comes from a one-shot tab marker, not from the signed-in WebID and pod root (AC6 wording) [handoff.ts] — deferred: 14.4 writes `space.ttl` and the done checks read the pod from then on
- [x] [Review][Defer] Password step succeeds, reply lost: the retry reads "already exists" as `email-taken` [register.ts] — deferred: narrow; recovery is signing in at the pod with that email
- [x] [Review][Defer] Resume with a different passphrase: login fails quietly (`loggedIn=false`, flow B) [register.ts] — deferred: harmless, the provider's login page asks
- [x] [Review][Defer] `creating` is page-local while `pending` is module-level: two page instances could both create [page.ts, register.ts] — deferred: page instances are only re-made by sign-out and login returns
- [x] [Review][Defer] Draft from the same browser prefilled for a different WebID's workbench [main.ts] — deferred: same browser, 14.4 moves the draft to the pod
- [x] [Review][Defer] Tile navigation drops typed passphrases (outside an error) [page.ts] — deferred: polish pass
- [x] [Review][Defer] `/.account/login/password/` is unlimited: a password-guessing surface on a server that advertises registration [mom-pods.caddy] — deferred: separate hardening, with 14.9's
- [x] [Review][Defer] xcaddy plugins unpinned (`caddy-ratelimit`, `caddy-dns/ovh`) [Dockerfile] — deferred: pin to the versions in the running image
- [x] [Review][Defer] Nothing ties `OPEN_REGISTRATION` to the gateway limit [describe.js] — deferred: documented in the .env.example
- [x] [Review][Defer] Resolved-name suggestion for a reserved name may itself be reserved [podform.ts] — deferred: the server answers again

## Dev Notes

- **Where the code goes:** mom-home (`/var/home/nicolas/github/mom-home`), copied-from-kit rules apply: `lib/register.ts` is meant to move into solid-kit later, so keep it domain-free (no tile, no tree, no draft inside it) and add its test with it (`register.test.ts`, mocked `fetch`, like `auth.test.ts`). The kit's ADR 010 amendment (points 8-11) is the contract.
- **Same-site is the boundary** (kit ADR 010 point 3): this only works because `home.` and `pod.` share `mapsofmaking.org`. A cross-site fork must link to the provider's sign-up page instead.
- **The account token and half-built account live in memory for the page session only.** Not `localStorage`, not the draft store. A reload mid-flow orphans the account (acceptable, CSS 7.2 cannot delete accounts, solid-css-overlay#17) and the copy for "half-finished" must say what to do (log in at the pod with the same email and passphrase, or pick another address).
- **Names the user sees:** passphrase everywhere (14.0 decision; the provider's pages say password until solid-css-overlay#27 ships).
- **Shadow-state drift** is the recurring bug class in this app's wizards (Epic 9 retro): the form's DOM, the register state and the draft must not each hold their own copy of the email or address. One model, the DOM reads from it.
- **A re-render destroys what the screen held** (mom-home CLAUDE.md): the passphrase fields live in a screen that re-renders on error. Update messages in place, never re-render the form on a validation or network error (AC2 "no error clears a field").
- **Carried from 14.2 review, moved to 14.4** (the write happens there, not here; flagged for Nicolas to confirm): non-http schemes in website/logo are kept as typed, validate at the pod write; a resumed draft whose geocoder answer had no country hides the typed country. Neither can matter before a file is written.
- **Out of scope:** writing `space.ttl`, making it public, registering the space (14.4); the self-host door's content (14.5); deleting accounts; password reset flows (the provider's own page).
- **Testing:** `npm run verify` stays the gate (259 tests, 54 audit checks at 14.2). Mocked tests do not prove the protocol: S5 against production is the done gate, and "tested live" is stated only for what S5 ran (feedback: mocks hide protocol bugs).
- **Rate limiting:** also keep the client honest: one in-flight "Create it" at a time (button disabled while pending), no automatic retry on a 4xx.

### Open questions for Nicolas (not blocking S1)
1. Wording of the AC6 "pod is ready" line.
2. Confirm the two 14.2 deferrals move to 14.4.
3. Rate-limit numbers for `/.account/` (suggest a handful of creations per IP per hour).

