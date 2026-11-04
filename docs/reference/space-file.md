# The space file — what home writes, and what the map takes from it

> One table for the fields tile A collects (home app, Epic 14), the two files
> tile B writes from them, and what the map keeps when it reads either.
> The pod door writes Turtle (`space.ttl`, Story 14.4); the self-host door
> writes SpaceAPI JSON (Story 14.5); the map reads both (Story 14.7). Past
> the ingest, a field follows the [field traceability matrix](field-traceability.md).
>
> Decided with Nicolas, 2026-10-31 and 2026-11-01. The fixtures
> (`tests/fixtures/space/atelier-du-canal.{ttl,json}`, the example below) and
> the parity test that hold the two files together are in the repo
> (`tests/test_space_turtle.py`, `infra/link_handler/test_register_turtle.py`);
> home's two writers (Stories 14.4, 14.5) are tested against the same fixtures.

## The fields

| Draft (tile A) | Required | SpaceAPI JSON (self-host) | Turtle `space.ttl` (pod) | Map graph after ingest |
|---|---|---|---|---|
| name | yes | `space` | `schema:name` | `schema:name` |
| street | no | in `location.address` | `schema:address/schema:streetAddress` | in `mom:address` (below) |
| postcode (derived) | no | in `location.address` | `schema:address/schema:postalCode` | in `mom:address` (below) |
| city | yes | in `location.address` | `schema:address/schema:addressLocality` | `schema:addressLocality`, and in `mom:address` |
| country (derived) | yes | `location.country_code` | `schema:address/schema:addressCountry` | `mom:countryCode` (two letters), and in `mom:address` |
| lat, lon (geocoded) | yes | `location.lat`, `location.lon` | `schema:geo [ schema:latitude ; schema:longitude ]` | same |
| description | no | `description` | `schema:description` | `schema:description` |
| contact handles (tile C) | no | `contact` (SpaceAPI's keys: `email`, `phone`, `matrix`, one each) | one or many, by kind (table below) | not kept (below) |
| website | no | `url` | `schema:url` (IRI) | `schema:url` |
| logo | no | `logo` | `schema:logo` (IRI) | `schema:logo` |
| opening hours (tile C) | no | `opening_hours` | `schema:openingHours` | `schema:openingHours` |
| networks (join tile) | no | `mom.memberOf` | `mom:memberOf` (IRIs) | `mom:memberOf` |

### Contact handles

A space gives one handle or many, several of one kind allowed (mom-home #39). Each kind lives in one
place in the file. The `contactType` strings and the keys are an agreement between home's writer (its
tree's `onb:ContactType`) and the map's reader (`spaceapi_extract/turtle.py` `_contact`); the card shows
each handle with the design system's ContactPicto of the same key. The pinned contract is
`tests/fixtures/space/handles.ttl` (re-pinned in mom-home).

| Key | Turtle | What the card gets (`value`) |
|---|---|---|
| `email` | `schema:email "…"` (one statement per address) | the address; copied on click |
| `phone` | `schema:telephone "+…"` (international form) | the number; copied on click |
| `matrix` | `schema:contactPoint [ schema:contactType "Matrix" ; schema:url <https://matrix.to/#/…> ]` | the room (`#room:server`); copied |
| `signal` | contact point, `contactType "Signal"`, `url` a group link | the link; opened |
| `telegram` | contact point, `contactType "Telegram"`, `url <https://t.me/…>` | the link; opened |
| `discord` | contact point, `contactType "Discord"`, `url` an invite link | the link; opened |
| `mattermost` | contact point, `contactType "Mattermost"`, `url` the team or channel | the link; opened |
| `link` | contact point, `contactType "Link"`, `url` any other page | the link; opened |

A contact point may be a blank node or a named one (home names the ones it adds, `<#contact-<key>-<n>>`).
`contactType` is read in any case. A value the map can't show safely (not an address, not a number, a
link that isn't plain `http(s)`), an unknown kind, and handles past the twentieth are left out.

`location.address` is written `"<street>, <postcode> <city>, <CC>"`, the
order `parse_locality_from_free_address` reads (`scripts/spaceapi_extract/address.py`).
Without a street: `"<postcode> <city>, <CC>"`.

**The graph keeps one address string for both formats** (decided 2026-11-01):
`mom:address` is the string above, composed from the Turtle's address node
exactly as home composes it for JSON, next to `schema:addressLocality` and
`mom:countryCode`. The map's card reads `mom:address`; neither format writes
`schema:streetAddress`, `schema:postalCode` or `schema:addressCountry`. A
country that is not two letters ("Belgium") stays in the string, and
`mom:countryCode` is not written.

Email and Matrix stay in the source file only: no query uses them, so the
index doesn't hold them (decided 2026-10-31). The card reads them from the
source as the map last read it.

## Example

```turtle
@prefix schema: <https://schema.org/> .
@prefix mom: <https://mapsofmaking.org/ns/mom#> .

<#space> a mom:Space, schema:Place ;
  schema:name "Atelier du Canal" ;
  schema:description "Open workshop for repairs and prototypes." ;
  schema:address [ a schema:PostalAddress ;
    schema:streetAddress "Rue du Canal 12" ;
    schema:postalCode "1070" ;
    schema:addressLocality "Anderlecht" ;
    schema:addressCountry "BE" ] ;
  schema:geo [ a schema:GeoCoordinates ;
    schema:latitude 50.8391 ; schema:longitude 4.3297 ] ;
  schema:email "contact@atelierducanal.example" ;
  schema:contactPoint [ a schema:ContactPoint ;
    schema:contactType "Matrix" ;
    schema:url <https://matrix.to/#/%23atelier:matrix.org> ] .
```

```json
{
  "api_compatibility": ["15"],
  "space": "Atelier du Canal",
  "location": {
    "address": "Rue du Canal 12, 1070 Anderlecht, BE",
    "country_code": "BE",
    "lat": 50.8391,
    "lon": 4.3297
  },
  "description": "Open workshop for repairs and prototypes.",
  "contact": { "email": "contact@atelierducanal.example", "matrix": "#atelier:matrix.org" },
  "state": { "open": null }
}
```

## What the map does with Turtle (Story 14.7)

1. **Subject.** The file's `<…/space.ttl#space>` becomes the space's own IRI
   (`urn:mak:space/<slug>`); the pod document is kept as `mom:profileUrl`
   (the registered address is also `mom:endpointUrl`, which the heartbeat
   needs). With several space nodes in one file, the `#space` one is read;
   with several and none of them `#space`, the file is refused.
2. **Address.** The `schema:PostalAddress` node is flattened into `mom:address`
   (as above), `schema:addressLocality` and `mom:countryCode`, the same
   statements the JSON path writes.
3. **Allow-list.** Only the predicates in the table are read. A pod file has
   other writers, and a person's pod holds more than a space. Everything else
   in the file is ignored, and a space file read from a pod is one node of it.
4. **Untrusted input.** IRIs are accepted only as plain `http(s)` (and
   `urn:mak:network/<slug>` for networks), with none of the characters that
   could end an IRI in SPARQL; relative IRIs resolve against the document.
   Lengths are capped (name 200, description 5000), coordinates range-checked,
   at most 5000 statements and 1 MiB of Turtle.
5. **Contact handles** stay out of the index. They are read from the source
   as the map last read it: `/api/space/{id}/raw` returns them for the card as a
   list of `{type, value}` (snapshots read before 2026-11-04 hold a SpaceAPI-style
   object; the card takes both). The SpaceAPI view of a Turtle file (`as_spaceapi`,
   for the validators) keeps SpaceAPI's own keys: the first email, phone and room.
6. **Namespace.** `http://schema.org/` is read as `https://schema.org/`.
7. **Asking and telling apart.** The map asks `Accept: text/turtle,
   application/ld+json;q=0.9, application/json;q=0.8` (Turtle first: a CSS pod
   would otherwise answer with full-IRI JSON-LD that the JSON path cannot
   read). `text/turtle` is Turtle; `application/json` and `application/ld+json`
   go the SpaceAPI way, as before (JSON-LD with compact `schema:` keys keeps
   working; **JSON-LD with full IRIs is not read yet**, a follow-up). Any other
   label is looked through: the content is tried as JSON, then as Turtle, so
   a git host's `text/plain` raw file works for both. A web page, an image or
   an empty answer is refused with the media type the server sent. At most 2 MiB
   is read.
8. **Heartbeat.** The same reading runs every tick: a Turtle space's snapshot
   keeps the fields read, the contact, the text as written and its media type
   (`snapshots.media_type`, `snapshots.raw_text`; rows from before read as
   JSON). A change counts on the fields the map keeps; whether that is what a
   coordinator wants counted is Story 14.10's.
