# Story 14.7: Register and Heartbeat Accept Turtle

Status: backlog — blocks 14.4 (since 2026-10-30 the pod door writes `space.ttl`)

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
