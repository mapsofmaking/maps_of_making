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
| country (derived) | yes (`XZ` at sea, outside any country) | `location.country_code` | `schema:address/schema:addressCountry` | `mom:countryCode` (two letters), and in `mom:address` |
| lat, lon (geocoded) | yes | `location.lat`, `location.lon` | `schema:geo [ schema:latitude ; schema:longitude ]` | same |
| description | no | `description` | `schema:description` | `schema:description` |
| contact handles (tile C) | no | `contact` (SpaceAPI's keys: `email`, `phone`, `matrix`, one each) | one or many, by kind (table below) | not kept (below) |
| website | no | `url` | `schema:url` (IRI) | `schema:url` |
| logo | no | `logo` | `schema:logo` (IRI) | `schema:logo` |
| opening hours (tile C) | no | `opening_hours` | `schema:openingHours` | `schema:openingHours` |
| networks (join tile) | no | `mom.memberOf` | `mom:memberOf` (IRIs) | `mom:memberOf` |
| SDGs (import, #73) | no | `mom.sdgs` (1–17) | `mom:sdgs` (integers 1–17) | `mom:sdgs` |
| topics (import, #73) | no | `knowsAbout` (list of text) | `schema:knowsAbout` (literals, ≤ 50, ≤ 200 chars each) | `schema:knowsAbout` |

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

## A network

> Decided with Nicolas, 2026-11-19. A network (not a space) registers through
> the same doors and shows on the map. The fixtures
> (`tests/fixtures/space/maakbib.{ttl,json}`) and their parity tests
> (`tests/test_space_turtle.py`, `infra/link_handler/test_register_network.py`)
> hold the two files together, as for a space.

A network has no address: it **serves an area**, and its file gives the
centre of it, saying how coarse that point is. Everything else (name,
description, website, logo, contact handles, `memberOf`) is as for a space.
On the map a network is **its own entity, not a place** (M1, below): no pin,
a card of its own, and its members.

| Field | Required | SpaceAPI JSON (self-host) | Turtle `space.ttl` (pod) | Map graph after ingest |
|---|---|---|---|---|
| kind | yes | `mom.kind: "network"` | the node is typed `mom:Network, schema:Organization` (subject stays `<#space>`) | `a mom:Network, schema:Organization` (a space: `a mom:Space`) |
| area served | yes | `mom.areaServed`, a list of `{"code", "name"}` | `schema:areaServed [ a schema:AdministrativeArea ; schema:identifier "BE-VLG" ; schema:name "Flanders" ]` (one node per area) | `schema:areaServed`, the same node per area (code, and name when there is one) |
| pin fidelity | yes | `mom.geolocationFidelity` | `mom:geolocationFidelity` | `mom:geolocationFidelity` |
| lat, lon | yes | `location.lat`, `location.lon` | `schema:geo [ schema:latitude ; schema:longitude ]` | same |
| country | no | `location.country_code` | none: derived from the areas | `mom:countryCode` (given, or the one country all areas are in) |
| address | — | none (no `location.address`) | none (no `schema:address`) | none: the card says "Network · …" instead |
| hours | no | `schema:openingHours` (as a space) | `schema:openingHours` | the same; the card calls them **contact hours** |

- **An area** is a code and a name, anywhere in the world. The code is ISO
  3166-1 alpha-2 (`BE`) or ISO 3166-2 (`BE-VLG` Flanders, `FR-IDF`
  Île-de-France, `GB-SCT` Scotland): read in any case, written upper case
  (`^[A-Z]{2}(-[A-Z0-9]{1,3})?$`); an area without a valid code is left out.
  The name is a plain literal, the name the network's file gives (home takes
  it from the area search below), one line, at most 200 characters. One area
  per code (two of one code: a name beats none, then the smaller name),
  sorted by code, at most 10.
- **The first shape is still read** (decided with Nicolas, 2026-11-19): a bare
  code, `schema:areaServed "BE-VLG"` in Turtle or `"BE-VLG"` in the JSON list
  (or `"areaServed": "BE-VLG"`), is an area without a name. The map then
  names a country in English from its code, and shows a subdivision's code
  (Belgium's three regions by name).
- **Fidelity** takes the ontology's values: `exact`, `approximate`, `city`,
  `region` (added for networks), `country`. A network uses `region` for a
  subdivision and `country` for a country. Any other value is left out.
- **The pin** is the area's centre as the geocode proxy gives it (below):
  home searches the area by name, `POST /api/geocode {"area_search":
  "Flanders"}`, and writes the chosen candidate's `code`, `name`, `lat`,
  `lon` and `fidelity` into the file (`{"area": "BE-VLG"}` gives the centre
  of a code already known).
- **Same name as a space.** A network never claims a seeded space of the same
  name (the claim-merge on registration matches the same kind only). The two
  never share a graph or an id either (identity, below).
- **No subset ladder.** The space's ladder (pin → card → SpaceAPI) and its
  "Level up: add openingHours" hint are not a network's: `validate-url` and
  `register-url` answer `subset` and `next_unlock` null for it (and `kind:
  "network"`), and registration writes neither.
- **The map's file** (`spaces.geojson`) gives every feature `kind`
  (`"space"` | `"network"`) and `area_served`, a list of `{"code", "name"}`
  (`name` is `""` for a bare code). A network's feature also has `members`
  (below).

### A network is its own entity (M1)

> Decided with Nicolas, 2026-11-19, after his live test with Maakbib: a
> network is not a place. It has its own identity, no pin, and its members.

**Identity.** A network is registered as graph and subject
`urn:mak:network/<slug>` (`<slug>` from its name, as a space's), the IRI its
members already name with `mom:memberOf` (seeding writes
`urn:mak:network/<label>`). A space stays `urn:mak:space/<slug>`.

| | A space | A network |
|---|---|---|
| graph and subject | `urn:mak:space/<slug>` | `urn:mak:network/<slug>` |
| id (map, snapshot store, API) | `<slug>` | `network_<slug>` |

The id is what `spaces.geojson`, `?space=` links and the snapshot store use.
A slug never holds `_`, so a space and a network of the same name never share
one (`maakbib`, `network_maakbib`). The lookups by id serve both kinds: there
is no `/api/network/…`. `GET /api/space/{id}/pin`, `/raw`, `POST
/api/heartbeat-space/{id}` and `/api/bot/deploy-key/{id}` take
`network_<slug>`; `GET /api/space-by-endpoint` answers it for a network's
address; `POST /api/register-url` answers `space_uri: urn:mak:network/<slug>`
and the id itself, `id: network_<slug>` (`id` comes for a space too: read it
rather than parsing `space_uri`).
The heartbeat ticks a network as it ticks a space; the endpoint dedupe finds
it by its address under either prefix.

`GET /api/network-members?url=<the network's file>` (mom-home #74) lists the
spaces the map counts as the network's members (`members` on its feature):
`{id, members: [{id, name, endpoint_url, media_type, contact: [{type, value}]}]}`.
`contact` is what the map already shows on the card (a JSON file's `contact`,
a Turtle file's handles from its snapshot). 404 `not_a_network` when the
address isn't a registered network; a network the map hasn't redrawn yet has
no members.

**Moving a network registered before M1.** A record found by its address (or a
claimed seed) under the other kind's prefix moves: a network in
`urn:mak:space/<slug>` is written to `urn:mak:network/<slug>` and the old
graph dropped in the same update (and the other way round, for a file that
changed kind). Registering a network's address again migrates it.

**Members.** A network's members are the spaces whose `mom:memberOf` is its
IRI (`urn:mak:network/<slug>`), or the address of its own file (its endpoint
or pod profile, with or without a `#fragment`). The map's file gives the
network `members`, the member spaces' ids, and writes a membership given by
address as the network's IRI, so one network is one filter chip and one
`networks=` parameter whichever way its members name it. A network in a
network is not one of its member spaces.

**On the map.**
- **No pin.** A network is in `spaces.geojson` (its card, Find, its members
  need it) but not on the map layer; the camera's first fit leaves it out.
- **Find.** A network is a row with its own mark (not a pin's dot), "Network ·
  Flanders" (its areas' names), and `network` where a space has its status.
  Its chip, and a space's badge, carry the network's name when the network is
  on the map (else the slug in capitals, as before).
- **Opening a network** (its row, its chip turned on, a badge on a member's
  card, a `?space=network_<slug>` link): the members become the filter, the
  map fits them (none: the area's centre), and the **Network card** opens. A
  chip turned off only removes the filter. A badge whose network is not on the
  map applies the filter and opens Find.
- **The Network card** ("Network", not "Space Profile"): name, logo, "Network
  · <areas>", description, website, **contact hours** (its
  `schema:openingHours`, only when given), contact, **Members · N** (each opens
  that space's card; 50 shown, the rest in Find), and **Embed this network**:
  the preset drawer with its members as the filter (`networks=<its IRI>`) and
  the box around them as `bbox` (no `space=`), so a network embeds its own map
  on its site. No "What your data unlocks".

**Moving the live record** (an admin note: run by hand once this code is
deployed). Maakbib was registered on 2026-11-19 as `urn:mak:space/maakbib`.
Registering its address again moves it; the public API is enough, nothing
touches Oxigraph by hand (on the VPS, `localhost:7878` is another project's
store):

```sh
MAP=https://mapsofmaking.org
# 1. The networks still under urn:mak:space/, and their addresses
curl -s "$MAP/data/spaces.geojson" | jq -r '.features[].properties
  | select(.kind == "network" and (.uri | startswith("urn:mak:space/"))) | "\(.id) \(.endpoint_url)"'
# 2. Register each address again: the answer says urn:mak:network/<slug>
curl -s -X POST "$MAP/api/register-url" -H 'Content-Type: application/json' \
  -d '{"url": "<endpoint_url from 1>"}'
# 3. Check: the id is network_<slug>; step 1 (after the map's rebuild, a minute) lists nothing
curl -s -G "$MAP/api/space-by-endpoint" --data-urlencode 'url=<endpoint_url from 1>'
```

Idempotent: a second run of step 2 finds the network under
`urn:mak:network/` and rewrites it in place. The old snapshot row (`maakbib`)
stays in the snapshot store; nothing reads it.

```turtle
@prefix schema: <https://schema.org/> .
@prefix mom: <https://mapsofmaking.org/ns/mom#> .

<#space> a mom:Network, schema:Organization ;
  schema:name "Maakbib" ;
  schema:description "MaakBib helpt bibliotheken en jeugdwerkingen met kennis en een netwerk om een maakplaats of fablab uit te bouwen en te runnen." ;
  schema:url <https://maakbib.be/> ;
  schema:logo <https://maakbib.be/wp-content/uploads/2026/08/logo-maakbib-kleur.svg> ;
  schema:email "info@decreatievestem.be" ;
  schema:areaServed [ a schema:AdministrativeArea ; schema:identifier "BE-VLG" ; schema:name "Flanders" ] ;
  schema:geo [ a schema:GeoCoordinates ;
    schema:latitude 51.0378 ; schema:longitude 4.2406 ] ;
  mom:geolocationFidelity "region" .
```

```json
{
  "api_compatibility": ["15"],
  "space": "Maakbib",
  "logo": "https://maakbib.be/wp-content/uploads/2026/08/logo-maakbib-kleur.svg",
  "url": "https://maakbib.be/",
  "location": { "country_code": "BE", "lat": 51.0378, "lon": 4.2406 },
  "description": "MaakBib helpt bibliotheken en jeugdwerkingen met kennis en een netwerk om een maakplaats of fablab uit te bouwen en te runnen.",
  "contact": { "email": "info@decreatievestem.be" },
  "state": { "open": null },
  "mom": { "kind": "network", "areaServed": [{"code": "BE-VLG", "name": "Flanders"}], "geolocationFidelity": "region" }
}
```

The centre (51.0378, 4.2406) is Nominatim's point for Vlaanderen, the one the
geocode proxy returns for `BE-VLG`.

### The geocode proxy, for an area

`POST /api/geocode` takes three shapes:

| Request | For | Nominatim is asked | `fidelity` |
|---|---|---|---|
| `{"address", "city", "postcode"?, "country_code"?}` | a space (as before) | the joined address | `exact` with a street, `city` without |
| `{"area": "BE-VLG"}` | a network, a subdivision | the code, `countrycodes=be`, five answers (no `featuretype`: geopy sends it as `featureType`, which Nominatim misreads); the first whose deepest `ISO3166-2-lvl*` is the code is kept | `region` |
| `{"area": "BE"}` | a network, a country | `country=BE`, `featuretype=country` | `country` |

The answer keeps its keys and adds two: `{lat, lon, country_code, postcode,
display_name, fidelity, area}`. No match: `lat`/`lon`/`display_name` null,
`area` still the code asked. A body with neither shape, or an `area` that is
not an ISO code: 422. Nominatim down: 503. The 1 req/s limit is unchanged.

#### Searching an area by its name

> Decided with Nicolas, 2026-11-19: a network's area works anywhere in the
> world, so home asks for it by name rather than by a code from a list.

`{"area_search": "Flanders", "lang": "en"}` (`lang` optional, default `en`,
two letters) answers the areas the name may be:

```json
{"candidates": [
  {"code": "BE-VLG", "name": "Flanders", "display_name": "Flanders, Belgium",
   "lat": 51.0377778, "lon": 4.2405556, "fidelity": "region"}
]}
```

> Since mapsofmaking/maps_of_making#87 (2026-11-20): the ISO 3166 list is
> read first, typos forgiven, and a town brings the areas it sits in
> ("region bruxellles capitale" and "Brussels" found nothing before).

- **The ISO list first, offline.** `pycountry`'s countries and subdivisions
  (all of them: every ISO subdivision is an official area), under every
  name pycountry has (the local name and each translation, an inverted name
  like "Bruxelles-Capitale, Région de" also as said), compared casefolded,
  accents and punctuation gone. An exact name is a candidate; so is a near
  one (`difflib`, ratio 0.9 or more, searches of 5 characters or more, at
  most 3): "region bruxellles capitale" finds `BE-BRU`, "Flanders" does not
  bring Landes. Its `name` is pycountry's in `lang` when it has one, else
  the local name ("Région de Bruxelles-Capitale" in English); its
  `display_name` is that name and the country's.
- Nominatim is asked the name as free text, with `addressdetails`, ten
  answers, `accept-language` set to `lang`, and no `featuretype`.
- An answer is kept when Nominatim files it (`addresstype`) as a `country`,
  `state`, `region` or `province` **and** it has an ISO code of its own: a
  country its `country_code` (upper case), fidelity `country`; a subdivision
  the `ISO3166-2-lvl*` key that comes right after its own component in
  Nominatim's `address` and is the deepest one there, fidelity `region`. A
  province with no code of its own (only its region's) is left out; so are
  counties and streets, and towns as such (Paris the city).
  One exception, seen live: a `county` whose `address` also names it, under
  the same name, as a `state`, `region` or `province` is that area
  (Brussels-Capital: `county, region, ISO3166-2-lvl4: BE-BRU`).
- `name` is the answer's own name in `lang` (else the first part of
  `display_name`). Each code once, in Nominatim's order, at most 5; none
  found: `{"candidates": []}`.
- An empty `area_search` or one over 100 characters, or a `lang` that is not
  two letters: 422. Nominatim down: 503.
- **A town brings its areas.** An answer Nominatim files as a `city`,
  `town`, `village`, `hamlet`, `municipality`, `suburb`, `borough`,
  `city_district`, `quarter` or `neighbourhood` offers each
  `ISO3166-2-lvl*` code of its address that is a real ISO subdivision,
  deepest first, named by the address component just before it: Brussels
  gives `BE-BRU` "Brussels-Capital", Gent `BE-VOV` Oost-Vlaanderen then
  `BE-VLG` Vlaanderen, Paris `FR-75C` then `FR-IDF`. A county does not
  (Scotland County stays out).
- **Order**, each code once, at most 5: exact ISO names, Nominatim's own
  areas, the areas towns sit in, near ISO names. A code Nominatim's own
  answers also give takes their name, `display_name` and centre.
- **Every candidate has a centre** (home pins the pick, no second ask). One
  Nominatim's search didn't place is asked by its code, as `{area}` does:
  one more call each, at most 3 per search, cached in the process (areas
  don't move); no centre, the candidate is left out. So a search costs one
  to four Nominatim calls on the shared 1 req/s limit, which itself is
  unchanged.

Seen live on 2026-11-19 (`lang` en): Flanders, Île-de-France, Bavaria,
Catalonia and Scotland each come back as a `state` with their own `lvl4` code
(`BE-VLG`, `FR-IDF`, `DE-BY`, `ES-CT`, `GB-SCT`); "Scotland" also brings two
US counties named Scotland, left out. West Flanders comes back as a `state`
with its own `lvl6` code (`BE-VWV`) before Flanders' `lvl4`. Wallonia is a
`state` (`BE-WAL`). "Brussels" comes back only as cities, so it found no
area until #87 (now `BE-BRU` through the city); "Brussels-Capital Region"
finds `BE-BRU` "Brussels-Capital" (a `county`, the exception above).

## Moving to a new address, and who may register a name (#85)

> Decided 2026-11-20 (map#85). A record belongs to the address it was
> registered from. A name is no longer enough to replace it.

**A name that is taken.** A registration whose slug lands on a record already
registered from **another** address is refused (`409`). Before #85 it dropped
that record and wrote its own (the same name was enough). Not affected:
registering the same address again; claiming a seed (`mom:source`
`scraped-*`, no address), as before; a space and a network of the same name
(own prefixes, M1). The canary's id `mother-sands` is taken too: a file named
"Mother Sands" is refused instead of making a second pin.

**Same name, same place or not (2026-11-21).** A new registration (an
address the map doesn't hold, no seed of that name to claim) is checked
against every record of the same name and kind registered from another
address, whatever its id:

- closer than 25 km (`_SAME_PLACE_KM`), or either side without a position:
  the same space registered twice, refused `name_taken` with that record's
  `id` and address. This catches a record under a seed's id
  (`ingegno-maker-space-drongen`) that the name alone (`ingegno-maker-space`)
  would miss, and would duplicate;
- farther: another space (OpenFab in Brussels, OpenFab in Istanbul). It gets
  the first free id of `<slug>`, `<slug>-<town>`, `<slug>-<country code>`;
  all three taken is `name_taken`.

Distance, not the town's text: Ingegno's file says Gent, its id Drongen.

A seed (unclaimed, `mom:source` `scraped-*`) is claimed by name the same
way: only within 25 km of the file's pin, the nearest one if several. A seed
of that name farther away is another space and stays as it is; registering
again never drops it as an orphan either. Who claims a nearby seed is not
checked: the network's recognition settles that.

**Moving.** The coordinator puts the new address in the **old** file, then
registers the new one, naming the old:

```json
"mom": { "movedTo": "https://<pod>/public/space.ttl" }
```

```sh
curl -s -X POST "$MAP/api/register-url" -H 'Content-Type: application/json' \
  -d '{"url": "https://<pod>/public/space.ttl", "replaces": "https://old.example/space.json"}'
```

The map fetches the old file again, with the same guarded fetch as a
registration (public hosts only, no redirects). If `mom.movedTo` is exactly
`url`, the record is rewritten from the new file **in its own graph**: same
graph, same id, so the snapshot history (`urn:mak:space/<id>/…`), `?space=`
links and members' `mom:memberOf` still hold. `mom:endpointUrl` becomes the
new address and the heartbeat follows it from its next tick. The answer
carries `moved_from: <old address>` (`null` otherwise). A retry after the move
is an ordinary re-registration: the new address is already known. Only JSON
old files are read for `movedTo`.

**Refusals** (`409`, `detail` below). `add` is the block the old file must
hold, so home can show it as one line to copy:

```json
{ "error": "<code>", "id": "<the record's id>", "add": { "mom": { "movedTo": "<url>" } } }
```

| `error` | When | Also |
|---|---|---|
| `name_taken` | the slug is a record registered from another address (no `replaces`) | `replaces`: that record's address, to send back once the old file holds `add` |
| `replaces_not_found` | no record has the `replaces` address (or it is the canary, which never moves) | no `id` |
| `replaces_unreachable` | the old file cannot be fetched now | |
| `moved_to_missing` | the old file has no `mom.movedTo` | |
| `moved_to_mismatch` | `mom.movedTo` is not exactly `url` | `found`: what it holds |
| `kind_changed` | a space moving into a network file, or back (the id would change) | |

If the store cannot be asked whether a name is taken, registration answers
`503 {"error": "triplestore_unavailable"}` and writes nothing.

## Reading a file without registering it (`read-url`, #84)

`POST /api/read-url {"url": "…"}` fetches a space or network file (JSON or Turtle, so a pod
file too), validates it like `validate-url` and answers what it holds as plain JSON. It
**writes nothing**. Home uses it to start tile A from an existing file: the browser cannot
fetch another origin.

```json
{
  "validation": { "...": "validate-url's answer" },
  "record": {
    "name": "Mother Sand", "kind": "space",
    "lat": 51.65, "lon": 1.7, "address": "Maunsell Fort, North Sea", "country_code": "XZ", "timezone": "UTC+0",
    "url": "…", "logo": "…", "description": "…", "opening_hours": "…",
    "contact": { "email": "…", "irc": "#mothersand", "twitter": "@mothersand" },
    "memberOf": ["urn:mak:network/canary", "urn:mak:network/vulca"],
    "sdgs": [9, 11, 12, 14, 17], "knowsAbout": [],
    "areaServed": [], "geolocationFidelity": null,
    "unmapped": ["ext_canary", "ext_fab", "issue_report_channels", "state"]
  }
}
```

- The record is what the register readers take (`extract_core` + `extract_mom`, or the Turtle
  reader), so what home fills in is what the map would keep. `record` is `null` when the file
  could not be read; `validation.error` says why.
- `contact` is SpaceAPI's dict: the file's own for JSON; for Turtle, the first handle of each
  type (a second one of a type is named in `unmapped` as `contact.<type>`).
- `unmapped` names what the readers leave out, so nothing is lost silently: JSON top-level
  keys, and keys inside `location`, `mom`, `ext_fab` (`ext_fab.sdgs` is read when `mom.sdgs`
  is absent) and `ext` (`ext.tags` read as `knowsAbout`); Turtle predicates of the subject, as
  full IRIs. `api`, `api_compatibility` and JSON-LD's `@context`/`@type`/`@id` are not listed (a
  writer sets them again); JSON-LD `schema:geo` reaches the record through the validation's coordinates.- Fixtures: Mother Sand (`data/canary/baseline.json`), Maakbib, Ingegno (`tests/fixtures/space/ingegno.json`, a member of Maakbib).
- Same fetch rules as register: http(s) only, no redirects, 2 MiB, HTML/PDF/images refused.
- **Public hosts only** (validate, read and register): a URL whose host is, or resolves to, a
  loopback, private, link-local or otherwise non-public address (a container such as `oxigraph`)
  is refused before any request: `"The map reads files on the public internet; <host> is not."`
  Known gap: the name is resolved again for the request (DNS rebinding). The heartbeat does not
  check this (it only fetches registered endpoints).
- At most 30 reads a minute for the whole service (the link handler sees one address behind the
  proxies): then 429 `{"error": "rate_limited", "retry_after_seconds": n}`.

## What the map does with Turtle (Story 14.7)

1. **Subject.** The node typed `mom:Space`, `schema:Place` or `mom:Network`
   (`schema:Organization` only when nothing else is typed) is the space.
   The file's `<…/space.ttl#space>` becomes the space's own IRI
   (`urn:mak:space/<slug>`; a network's `urn:mak:network/<slug>`); the pod document is kept as `mom:profileUrl`
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
