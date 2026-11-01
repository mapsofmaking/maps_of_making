# Story 14.7: Register and Heartbeat Accept Turtle

Status: in-progress — S1 to S5 built on branch `epic-14-14-7-turtle` (PR open); done once merged, deployed and checked on production. Blocks 14.4 until then (since 2026-10-30 the pod door writes `space.ttl`)

## Story

As a space coordinator who publishes my space as Turtle,
I want the map to register and follow my `.ttl` as it does a `.json`,
So that the format is my choice, and the card shows my source as I wrote it.

## Context

Today `_fetch_and_validate` calls `resp.json()` and rejects anything else ("Response is not valid JSON").
It already accepts JSON-LD keys (`schema:name`, `schema:geo`). JSON is converted to triples by
`spaceapi_extract`; Turtle is already triples, so it skips that step but needs the same validation (a name,
coordinates). The snapshot store holds a parsed JSON payload; Turtle needs its text and media type.

## Acceptance Criteria

### AC1 — Negotiate, then branch on what came back
**Then** link_handler requests with `Accept: text/turtle, application/ld+json;q=0.9, application/json;q=0.8`
(Turtle first, see Dev Notes) and branches on the response `Content-Type`; a vague label (`text/plain`,
`application/octet-stream`, none) is looked through: JSON first, then Turtle, so a git host's raw file works
for both formats
**And** Turtle is parsed (rdflib), validated for a name and coordinates with the same rules as JSON-LD, and
mapped into the space's graph without passing through the SpaceAPI extractor.

### AC2 — Same registration, same heartbeat
**Then** register, dedup by endpoint, claim-merge and the heartbeat behave identically for both formats.

### AC3 — The source as written
**Then** the snapshot keeps the raw text and its media type; `/api/space/{id}/raw` returns both (and, for
Turtle, the contact read from it), and the space card shows the source in its own format, coloured like
the JSON one.

### AC4 — Clear refusal
**Then** a response that is neither (HTML, an error page) is refused with the media type it actually got.

## Tasks
- [x] **S1 (`12bb32a`):** `scripts/spaceapi_extract/turtle.py` `parse_space_turtle` (rdflib): subject choice,
  allow-list, same CURIE fields as `extract_core` + `extract_mom`, hostile IRIs dropped, caps; fixtures
  `tests/fixtures/space/atelier-du-canal.{ttl,json}`; parity test (graphs compared as graphs). 35 tests.
- [x] **S2 (`a9d1463`):** `infra/link_handler/source.py` (`fetch_source`: Accept order, label then content,
  refusal with the media type, 2 MiB cap, parse off the loop); `_fetch_and_validate`, `register_url` and
  `_build_sparql_update` take Turtle; snapshot store keeps `media_type` and `raw_text`. Registration checked
  against a real Oxigraph: the two fixtures differ only by `endpointUrl`, `profileUrl`, `contactJson`.
- [x] **S3 (`ba96a95`):** `fetch_snapshot` uses `fetch_source`; `fields_for` / `write_payload_fields` take a
  Turtle snapshot's fields; unusable answers mark the space unreachable with the reason. Checked on a local
  stack: an edited Turtle file moves `mom:updatedAt` and the description via `POST /api/heartbeat-space`.
- [x] **S4 (`7f0160f`):** `/raw` returns `mediaType` (and the contact for Turtle); the card heads and colours
  the Turtle source, the contact line reads email and Matrix from `/raw`.
- [x] **S5:** reference doc, this story, 14.4 and 14.5 notes, sprint status.
- [ ] **After merge:** deploy by CI, then check on production with `POST /api/validate-url` (read-only,
  writes nothing) on the fixture's raw GitHub URL (served `text/plain`, so it takes the content path) and on
  a JSON endpoint already registered; register nothing.

## Live check (2026-11-01, local stack with a real Oxigraph, not production)
- Register the Turtle and the JSON fixture: graphs identical but for `endpointUrl`, `profileUrl` (Turtle
  only) and `contactJson` (JSON only); a web page is refused ("The server sent text/html; the map reads JSON
  or Turtle.").
- Heartbeat: Turtle edited, `POST /api/heartbeat-space/atelier-du-canal`: description and `mom:updatedAt`
  follow, snapshot `text/turtle`, 740 bytes; the rematerialized feature has the address, locality, country
  code, description and endpoint, the pin at the file's coordinates.
- Card (Chromium, 1440 and 390 wide): Turtle space shows "Turtle · Endpoint Response" in colour and
  email + Matrix in the contact line; JSON space unchanged.
- Suites as CI runs them: `link_handler` 53, `tests` 93, `bot` 14 passing.

## Follow-ups (not in this story)
- Full-IRI JSON-LD (a stock CSS pod's default answer) is not read: parse it as RDF with a fallback to the
  JSON path, with regression tests on the existing JSON-LD registrations.
- Heartbeat hardening, including the existing gaps this story did not close (registered URLs are not checked
  against private addresses; the endpoint IRI is written into SPARQL unchecked): Story 14.9.
- What counts as a change for a Turtle space (today: the fields the map keeps; JSON: the whole payload):
  Story 14.10.

## Dev Notes
- A pod can serve one RDF document as Turtle or JSON-LD on request; a Turtle file on a pod may therefore
  arrive as JSON-LD if JSON is preferred. Checked against `pod.mapsofmaking.org` (2026-10-31, again
  2026-11-01): it answers `text/turtle` whatever the order of the Accept header. Turtle goes first
  anyway, for a stock CSS.

## Added 2026-10-31 — the space file

The fields, the Turtle home writes and what the map keeps are in
[`docs/reference/space-file.md`](../../docs/reference/space-file.md). For AC1 that means:

- **Subject.** `<…/space.ttl#space>` becomes `urn:mak:space/<slug>`; the pod document is kept as
  `mom:profileUrl` (the map's query already reads it).
- **Address (as built, decided 2026-11-01).** The `schema:PostalAddress` node is flattened into the space's
  composed `mom:address`, `schema:addressLocality` and `mom:countryCode`, the set the JSON path writes (the
  reference doc's streetAddress / postalCode column was never written by the JSON path). Was: flattened onto the space, with `mom:address` and
  `mom:countryCode` written from it, as the JSON path writes them.
- **Allow-list.** Only the table's predicates are copied: a pod file has other writers, and a person's pod
  holds more than a space.
- **Namespace.** `http://schema.org/` is read as `https://schema.org/`.
- **Media type.** `text/turtle` is parsed as RDF; `application/json` and `application/ld+json` go the
  SpaceAPI way, as before (decided 2026-11-01: parsing every ld+json as RDF would change how existing
  JSON-LD registrations behave; full-IRI JSON-LD, what a stock CSS pod sends, is a follow-up). Our pod
  answers `text/turtle` whatever the Accept order (checked 2026-10-31 and 2026-11-01), and Turtle comes
  first in the header so a stock CSS would send it too.
- **Email and Matrix stay out of the index** (no query uses them). The card shows them from the source as
  last read (AC3's raw), not from `contactJson`.

### AC5 — One table, held by a test
**Then** two fixtures, `space.ttl` and `space.json` for the reference doc's example, ingest to the same set of
statements in the space's graph (parity test), and home's two writers (14.4, 14.5) are tested against the
same fixtures.
