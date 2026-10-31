# The space file — what home writes, and what the map takes from it

> One table for the fields tile A collects (home app, Epic 14), the two files
> tile B writes from them, and what the map keeps when it reads either.
> The pod door writes Turtle (`space.ttl`, Story 14.4); the self-host door
> writes SpaceAPI JSON (Story 14.5); the map reads both (Story 14.7). Past
> the ingest, a field follows the [field traceability matrix](field-traceability.md).
>
> Decided with Nicolas, 2026-10-31. Draft: the fixtures and parity test that
> hold the three sides together are Story 14.7's to write.

## The fields

| Draft (tile A) | Required | SpaceAPI JSON (self-host) | Turtle `space.ttl` (pod) | Map graph after ingest |
|---|---|---|---|---|
| name | yes | `space` | `schema:name` | `schema:name` |
| street | no | in `location.address` | `schema:address/schema:streetAddress` | `schema:streetAddress` |
| postcode (derived) | no | in `location.address` | `schema:address/schema:postalCode` | `schema:postalCode` |
| city | yes | in `location.address` | `schema:address/schema:addressLocality` | `schema:addressLocality` |
| country (derived) | yes | `location.country_code` | `schema:address/schema:addressCountry` | `schema:addressCountry`, `mom:countryCode` |
| lat, lon (geocoded) | yes | `location.lat`, `location.lon` | `schema:geo [ schema:latitude ; schema:longitude ]` | same |
| description | no | `description` | `schema:description` | `schema:description` |
| contact email | no | `contact.email` | `schema:email` | not kept (below) |
| Matrix room | no | `contact.matrix` | `schema:contactPoint [ schema:contactType "Matrix" ; schema:url <https://matrix.to/#/…> ]` | not kept (below) |
| website | no | `url` | `schema:url` (IRI) | `schema:url` |
| logo | no | `logo` | `schema:logo` (IRI) | `schema:logo` |
| opening hours (tile C) | no | `opening_hours` | `schema:openingHours` | `schema:openingHours` |
| networks (join tile) | no | `mom.memberOf` | `mom:memberOf` (IRIs) | `mom:memberOf` |

`location.address` is written `"<street>, <postcode> <city>, <CC>"`, the
order `parse_locality_from_free_address` reads (`scripts/spaceapi_extract/address.py`).
Without a street: `"<postcode> <city>, <CC>"`.

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
   (`urn:mak:space/<slug>`); the pod document is kept as `mom:profileUrl`.
2. **Address.** The `schema:PostalAddress` node is flattened onto the space,
   and `mom:address` and `mom:countryCode` are written from it, as the JSON
   path writes them.
3. **Allow-list.** Only the predicates in the table above are copied. A pod
   file has other writers, and a person's pod holds more than a space.
4. **Namespace.** `http://schema.org/` is read as `https://schema.org/`.
5. **Media type.** `text/turtle` and `application/ld+json` are parsed as RDF;
   `application/json` goes the SpaceAPI way, as today.
