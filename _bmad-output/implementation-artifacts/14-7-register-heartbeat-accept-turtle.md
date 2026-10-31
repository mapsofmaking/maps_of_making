# Story 14.7: Register and Heartbeat Accept Turtle

Status: ready-for-dev — blocks 14.4 (since 2026-10-30 the pod door writes `space.ttl`)

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
**Then** link_handler requests with `Accept: application/json, application/ld+json, text/turtle;q=0.9`
and branches on the response `Content-Type`
**And** Turtle is parsed (rdflib), validated for a name and coordinates with the same rules as JSON-LD, and
mapped into the space's graph without passing through the SpaceAPI extractor.

### AC2 — Same registration, same heartbeat
**Then** register, dedup by endpoint, claim-merge and the heartbeat behave identically for both formats.

### AC3 — The source as written
**Then** the snapshot keeps the raw text and its media type; `/api/space/{id}/raw` returns both, and the
space card shows the source in its own format.

### AC4 — Clear refusal
**Then** a response that is neither (HTML, an error page) is refused with the media type it actually got.

## Dev Notes
- A pod can serve one RDF document as Turtle or JSON-LD on request; a Turtle file on a pod may therefore
  arrive as JSON-LD if JSON is preferred. Verify against `pod.mapsofmaking.org` before fixing the Accept
  order.

## Added 2026-10-31 — the space file

The fields, the Turtle home writes and what the map keeps are in
[`docs/reference/space-file.md`](../../docs/reference/space-file.md). For AC1 that means:

- **Subject.** `<…/space.ttl#space>` becomes `urn:mak:space/<slug>`; the pod document is kept as
  `mom:profileUrl` (the map's query already reads it).
- **Address.** The `schema:PostalAddress` node is flattened onto the space, with `mom:address` and
  `mom:countryCode` written from it, as the JSON path writes them.
- **Allow-list.** Only the table's predicates are copied: a pod file has other writers, and a person's pod
  holds more than a space.
- **Namespace.** `http://schema.org/` is read as `https://schema.org/`.
- **Media type.** `text/turtle` and `application/ld+json` are parsed as RDF; `application/json` goes the
  SpaceAPI way. Our pod answers `text/turtle` (checked 2026-10-31); CSS would send JSON-LD with full IRIs,
  which the SpaceAPI path can't read, so Turtle comes first in the Accept header.
- **Email and Matrix stay out of the index** (no query uses them). The card shows them from the source as
  last read (AC3's raw), not from `contactJson`.

### AC5 — One table, held by a test
**Then** two fixtures, `space.ttl` and `space.json` for the reference doc's example, ingest to the same set of
statements in the space's graph (parity test), and home's two writers (14.4, 14.5) are tested against the
same fixtures.
