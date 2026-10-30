# Story 14.8: Retire genjson

Status: backlog — after 14.2 is live

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
**Then** the map drawer's wizard link (`web/app.js` ~l.1408) points at home
**And** `infra/web/Caddyfile` and the gateway vhost drop genjson's host rules (keeping the redirect)
**And** `infra/web/smoke-test.sh` checks home instead of genjson, plus the redirect
**And** the Makefile's `deploy-genjson` target points at the home app, and `bernard-copy` (YAML → JSON)
is removed: the app's copy lives in `onboarding.ttl` (mom-home repo, `public/`) (14.1 AC2)
**And** `CREDITS.md` lists the font's new location.

## Dev Notes
- `web/app.js` reads `genjson_draft` from the **map's** origin to choose `?resume=1`. That origin never
  holds genjson's draft, so the hint likely never fires today. Once the draft lives on home, the drawer
  can't see it either: link to home plainly and let home resume on its own.
