# Story 14.8: Retire genjson

Status: done — live 2026-11-01 (map `01095c8`, home `940b468`). The Hetzner clean-up continues in `deferred-work.md`, from 2026-11-15

## Story

As anyone holding an old genjson link (a flyer, a bookmark, the map's drawer),
I want to land on the onboarding app with my draft still there where possible,
So that retiring genjson costs nobody their work.

## Acceptance Criteria

### AC1 — Redirect
**Then** `genjson.mapsofmaking.org/*` answers 301 to `home.mapsofmaking.org/`, keeping the query
(`?resume=1`).

### AC2 — Drafts in flight
**Given** localStorage is per origin, so home cannot read a draft saved on genjson
**Then** for a transition period genjson serves one small page instead of the redirect when a
`genjson_draft` exists: it forwards the draft to home in the URL fragment (never sent to a server), and
home imports it once and clears the fragment
**And** after the period (to set; usage is low, see the analytics design), the plain redirect replaces it.

### AC3 — Every pointer moves
**Then** the map drawer's wizard link (`web/app.js`) opens home plainly (the map's origin never held
`genjson_draft`, so the `?resume=1` lookup is gone)
**And** `infra/web/Caddyfile` (the app's, behind the gateway's Caddy) serves the forwarder at `genjson.` `/` and
301s every other path; `infra/web/smoke-test.sh` checks both
**And** the Hetzner leftovers go: `deploy-genjson` and `bernard-copy` (YAML → JSON) in the Makefile, and the nginx
vhost `infra/gateway-nginx/08-genjson-mapsofmaking.conf`. `deploy-genjson` is removed, not re-pointed: it
rsynced to Hetzner and home deploys from its own repo. The app's copy lives in `onboarding.ttl` (mom-home repo,
`public/`, 14.1 AC2)
**And** `CREDITS.md` lists the font where it still lives (`web/fonts/`, the map drawer's).

## Tasks
- [x] **S1 (mom-home `940b468`, live 2026-11-01):** `src/lib/forwarded.ts` reads `#from-genjson=<base64url JSON>`,
  known text fields only, cut to a length; `main.ts` imports once, only when home has no draft, and always
  clears the fragment. The pin is left out; a draft with a town and no pin now asks the geocoder when the page
  opens (`page.ts`). Checked against production.
- [x] **S2 (`6fd4757`):** `web/genjson/index.html` forwards the draft (or goes plain, query kept); Caddyfile: `/`
  serves it, other paths `redir` 301 to home (`/?{query}`); drawer link; smoke test (30 checks, run with podman).
  End to end on `genjson.localhost` against the live home: with draft, without, damaged draft, deep path.
- [x] **S3:** `genjson.js`, `bernard_copy.yaml`, `fonts/`, `tuto/`, `spaceapi-v15.schema.json`,
  `tests/test_bernard_voice_completeness.py` and the nginx vhost deleted; Makefile, `.gitignore`, `CREDITS.md`,
  compose comment, `07-wizard-shell.md` (retired banner) and `vps-topology.md` updated. Tag `genjson-last`
  keeps the wizard one `git show` away (14.5 may want the hosting-guide pictures from `tuto/`).
- [x] **S4, end of the transition (2026-11-01, Nicolas: "proceed S4", right after S2/S3 went live):** every path on
  `genjson.`, `/` included, is a 301 to home (query kept); `web/genjson/` is gone; smoke test updated. Ships by
  merge, no gateway change. A draft still in a browser on genjson's origin is no longer forwarded: the way in was
  open for the length of one deploy. (AC2's "transition period" was therefore minutes, by choice: usage is low.)
- [x] **S5a (now, repo only):** `import-a-space-batch.md` says `ssh mom`, two compose comments reworded, the geocode-cap options written down; decided: accept, look at the log after a week.
- [~] **S5, Hetzner leftovers: moved out of this story (2026-11-01).** What is left is not genjson's: it is the
  clean-up of the old server, gated on the end of the rollback window (2026-11-15) and mostly done on the Hetzner
  box by Nicolas. It is tracked in `deferred-work.md` ("Hetzner leftovers", with where each item is and what to do),
  not as a slice here.
- [x] **Nominatim identity** (own commit, not a slice): `_USER_AGENT` is `MapsOfMaking-geocode/1.0 (+https://mapsofmaking.org; contact …)`,
  and the `/api/geocode` docstring says what is true now.

## Live check (2026-11-01)
- `genjson.mapsofmaking.org/`, `/?resume=1` and `/x/y?a=1` answer 301 to `home.mapsofmaking.org/` with the query kept;
  the map's apex still answers 200. CI on `01095c8`: `tests`, `maps-web`, `images` green.
- Before S4, on the real genjson origin with a seeded `genjson_draft`: it landed on home with the form filled, the
  pin resolved and a clean URL; with no draft or a damaged one, home empty, query kept.
- No separate code review was run; each slice was checked by its own tests and a browser run before the commit.

## Dev Notes
- `web/app.js` reads `genjson_draft` from the **map's** origin to choose `?resume=1`. That origin never
  holds genjson's draft, so the hint likely never fires today. Once the draft lives on home, the drawer
  can't see it either: link to home plainly and let home resume on its own.
