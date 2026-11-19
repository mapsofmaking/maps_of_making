"""A network registers and shows on the map (2026-11-19, docs/reference/space-file.md).

Offline, as test_register_turtle.py: the space file is served by a local pytest-httpserver,
Oxigraph is faked (an rdflib Dataset where what is already stored matters), Nominatim is
replaced by a stub.
"""
from __future__ import annotations

import pytest
from fastapi import BackgroundTasks, HTTPException
from geopy.location import Location
from pytest_httpserver import HTTPServer
from rdflib import Literal, URIRef
from rdflib.compare import isomorphic
from rdflib.namespace import RDF

import main
from fakes import JSON_TEXT, NETWORK_JSON, NETWORK_TTL, TTL, FakeOxigraph, StoreOxigraph, inserted, serve
from test_register_turtle import comparable

MOM = "https://mapsofmaking.org/ns/mom#"
SCHEMA = "https://schema.org/"
NETWORK = URIRef("urn:mak:space/maakbib")


@pytest.fixture
def space_server():
    server = HTTPServer(host="127.0.0.1", port=0)
    server.start()
    yield server
    server.clear()
    server.stop()


def areas_of(g):
    """(code, name) of each schema:AdministrativeArea node the subject serves."""
    q = """PREFIX schema: <https://schema.org/>
    SELECT ?code ?name WHERE { ?s schema:areaServed ?a . ?a a schema:AdministrativeArea ; schema:identifier ?code .
                               OPTIONAL { ?a schema:name ?name } }"""
    return sorted((str(r.code), str(r.name) if r.name is not None else "") for r in g.query(q))


async def register(space_server, ox, body, content_type, path):
    url = serve(space_server, body, content_type, path)
    return await main.register_url(main.UrlRequest(url=url), BackgroundTasks())


@pytest.mark.asyncio
@pytest.mark.parametrize("body, content_type", [(NETWORK_TTL, "text/turtle"), (NETWORK_JSON, "application/json")], ids=["turtle", "json"])
async def test_a_network_is_stored_as_a_network_with_its_area_and_fidelity(space_server, tmp_path, monkeypatch, body, content_type):
    monkeypatch.setenv("SNAPSHOT_DB_PATH", str(tmp_path / "snap.db"))
    with FakeOxigraph() as ox:
        monkeypatch.setattr(main, "OXIGRAPH_ENDPOINT", ox.url)
        response = await register(space_server, ox, body, content_type, "/n")
        g = inserted(ox.updates[-1])
    assert response["status"] == "confirmed" and response["kind"] == "network"
    assert response["space_uri"] == str(NETWORK)
    assert (NETWORK, RDF.type, URIRef(MOM + "Network")) in g
    assert (NETWORK, RDF.type, URIRef(SCHEMA + "Organization")) in g
    assert (NETWORK, RDF.type, URIRef(MOM + "Space")) not in g
    assert areas_of(g) == [("BE-VLG", "Flanders")]
    assert (NETWORK, URIRef(MOM + "geolocationFidelity"), Literal("region")) in g
    assert (NETWORK, URIRef(MOM + "countryCode"), Literal("BE")) in g
    assert not any(p == URIRef(MOM + "address") for _, p, _ in g)


@pytest.mark.asyncio
async def test_turtle_and_json_networks_write_the_same_statements(space_server, tmp_path, monkeypatch):
    monkeypatch.setenv("SNAPSHOT_DB_PATH", str(tmp_path / "snap.db"))
    with FakeOxigraph() as ox:
        monkeypatch.setattr(main, "OXIGRAPH_ENDPOINT", ox.url)
        await register(space_server, ox, NETWORK_TTL, "text/turtle", "/t")
        from_ttl = inserted(ox.updates[-1])
        await register(space_server, ox, NETWORK_JSON, "application/json", "/j")
        from_json = inserted(ox.updates[-1])
    assert len(comparable(from_ttl)) > 8
    assert isomorphic(comparable(from_ttl), comparable(from_json))


@pytest.mark.asyncio
@pytest.mark.parametrize("body, content_type", [(TTL, "text/turtle"), (JSON_TEXT, "application/json")], ids=["turtle", "json"])
async def test_a_space_is_still_a_space(space_server, tmp_path, monkeypatch, body, content_type):
    monkeypatch.setenv("SNAPSHOT_DB_PATH", str(tmp_path / "snap.db"))
    with FakeOxigraph() as ox:
        monkeypatch.setattr(main, "OXIGRAPH_ENDPOINT", ox.url)
        response = await register(space_server, ox, body, content_type, "/s")
        g = inserted(ox.updates[-1])
    subject = URIRef("urn:mak:space/atelier-du-canal")
    assert response["kind"] == "space"
    assert set(g.objects(subject, RDF.type)) == {URIRef(MOM + "Space")}
    assert not any(p in (URIRef(SCHEMA + "areaServed"), URIRef(MOM + "geolocationFidelity")) for _, p, _ in g)


SEEDED_MAAKBIB = """
INSERT DATA { GRAPH <urn:mak:space/maakbib> {
  <urn:mak:space/maakbib> a <https://mapsofmaking.org/ns/mom#Space> ;
    <https://schema.org/name> "MaakBib" ;
    <https://mapsofmaking.org/ns/mom#source> "scraped-vow" ;
    <https://schema.org/geo> [ <https://schema.org/latitude> 51.05 ; <https://schema.org/longitude> 3.72 ] .
} }"""


@pytest.mark.asyncio
async def test_a_network_does_not_take_over_a_seeded_space_of_the_same_name(space_server, tmp_path, monkeypatch):
    monkeypatch.setenv("SNAPSHOT_DB_PATH", str(tmp_path / "snap.db"))
    with StoreOxigraph(SEEDED_MAAKBIB) as ox:
        monkeypatch.setattr(main, "OXIGRAPH_ENDPOINT", ox.url)
        response = await register(space_server, ox, NETWORK_TTL, "text/turtle", "/n")
        assert response["kind"] == "network"
        assert response["space_uri"] == "urn:mak:space/maakbib-network"
        assert not any("DROP GRAPH <urn:mak:space/maakbib>" in u or "DROP SILENT GRAPH <urn:mak:space/maakbib>" in u for u in ox.updates)

        # Both are on the map, each as its own kind.
        rows = ox.select(main._SPARQL_SELECT)
        features = {f["properties"]["id"]: f["properties"] for f in map(main._binding_to_feature, rows)}
    assert features["maakbib"]["kind"] == "space" and features["maakbib"]["name"] == "MaakBib"
    net = features["maakbib-network"]
    assert net["kind"] == "network" and net["area_served"] == [{"code": "BE-VLG", "name": "Flanders"}]
    assert net["geolocationFidelity"] == "region" and net["country_code"] == "BE" and net["address"] == ""


@pytest.mark.asyncio
async def test_the_map_reads_a_bare_area_code_an_earlier_registration_wrote(tmp_path, monkeypatch):
    """Maakbib's first record (2026-11-19) holds the code alone: the map still shows it, without a name."""
    legacy = """
INSERT DATA { GRAPH <urn:mak:space/net> {
  <urn:mak:space/net> a <https://mapsofmaking.org/ns/mom#Network> ;
    <https://schema.org/name> "Net" ;
    <https://schema.org/areaServed> "BE-VLG" ,
      [ a <https://schema.org/AdministrativeArea> ; <https://schema.org/identifier> "FR-IDF" ; <https://schema.org/name> "Île-de-France | Paris" ] ;
    <https://schema.org/geo> [ <https://schema.org/latitude> 51.0 ; <https://schema.org/longitude> 4.2 ] .
} }"""
    with StoreOxigraph(legacy) as ox:
        rows = ox.select(main._SPARQL_SELECT)
    net = main._binding_to_feature(rows[0])["properties"]
    assert net["area_served"] == [{"code": "BE-VLG", "name": ""}, {"code": "FR-IDF", "name": "Île-de-France | Paris"}]


@pytest.mark.asyncio
async def test_registering_a_network_again_keeps_to_its_own_record(space_server, tmp_path, monkeypatch):
    """Home registers the same address twice: the second finds the network by its address, and its
    snapshot goes under the network's id, never the seeded space's of the same name."""
    from snapshot_store import read_snapshot
    monkeypatch.setenv("SNAPSHOT_DB_PATH", str(tmp_path / "snap.db"))
    with StoreOxigraph(SEEDED_MAAKBIB) as ox:
        monkeypatch.setattr(main, "OXIGRAPH_ENDPOINT", ox.url)
        first = await register(space_server, ox, NETWORK_TTL, "text/turtle", "/n")
        second = await register(space_server, ox, NETWORK_TTL, "text/turtle", "/n")
    assert first["space_uri"] == second["space_uri"] == "urn:mak:space/maakbib-network"
    assert read_snapshot("maakbib") is None
    assert read_snapshot("maakbib-network")["payload"]["fields"]["schema:areaServed"] == [{"code": "BE-VLG", "name": "Flanders"}]


@pytest.mark.asyncio
async def test_a_space_still_claims_its_seeded_record(space_server, tmp_path, monkeypatch):
    seeded = SEEDED_MAAKBIB.replace("MaakBib", "Atelier du Canal").replace("urn:mak:space/maakbib", "urn:mak:space/adc-anderlecht")
    monkeypatch.setenv("SNAPSHOT_DB_PATH", str(tmp_path / "snap.db"))
    with StoreOxigraph(seeded) as ox:
        monkeypatch.setattr(main, "OXIGRAPH_ENDPOINT", ox.url)
        response = await register(space_server, ox, TTL, "text/turtle", "/s")
    assert response["space_uri"] == "urn:mak:space/adc-anderlecht"


@pytest.mark.asyncio
async def test_a_space_does_not_drop_a_registered_network_of_the_same_name(space_server, tmp_path, monkeypatch):
    monkeypatch.setenv("SNAPSHOT_DB_PATH", str(tmp_path / "snap.db"))
    space = TTL.replace("Atelier du Canal", "Maakbib")
    with StoreOxigraph() as ox:
        monkeypatch.setattr(main, "OXIGRAPH_ENDPOINT", ox.url)
        first = await register(space_server, ox, NETWORK_TTL, "text/turtle", "/n")
        second = await register(space_server, ox, space, "text/turtle", "/s")
        rows = ox.select(main._SPARQL_SELECT)
    assert first["space_uri"] == "urn:mak:space/maakbib"
    assert second["space_uri"] == "urn:mak:space/maakbib-space"
    kinds = {f["properties"]["id"]: f["properties"]["kind"] for f in map(main._binding_to_feature, rows)}
    assert kinds == {"maakbib": "network", "maakbib-space": "space"}


# ── Geocode: an area, as well as an address ─────────────────────────────────

def _stub(monkeypatch, location):
    calls = []

    def fake(query, **kwargs):
        calls.append((query, kwargs))
        return location

    monkeypatch.setattr(main, "_geocode", fake)
    return calls


FLANDERS = Location("Vlaanderen, België / Belgique / Belgien", (51.0377778, 4.2405556, 0),
                    {"address": {"state": "Vlaanderen", "ISO3166-2-lvl4": "BE-VLG", "country": "België / Belgique / Belgien", "country_code": "be"}})
BRUSSELS = Location("Région de Bruxelles-Capitale - Brussels Hoofdstedelijk Gewest, België", (50.8387951, 4.3753041, 0),
                    {"address": {"region": "Région de Bruxelles-Capitale", "ISO3166-2-lvl4": "BE-BRU", "country_code": "be"}})
# A province inside Flanders: it carries Flanders' code at lvl4 and its own at lvl6 (seen live, 2026-11-19).
WEST_FLANDERS = Location("West-Vlaanderen, Vlaanderen, België / Belgique / Belgien", (51.0404747, 2.9994213, 0),
                         {"address": {"province": "West-Vlaanderen", "ISO3166-2-lvl6": "BE-VWV", "state": "Vlaanderen",
                                      "ISO3166-2-lvl4": "BE-VLG", "country_code": "be"}})
BELGIUM = Location("België / Belgique / Belgien", (50.6402809, 4.6667145, 0), {"address": {"country": "België", "country_code": "be"}})


@pytest.mark.asyncio
async def test_geocode_a_region_by_its_code(monkeypatch):
    calls = _stub(monkeypatch, [FLANDERS])
    out = await main.geocode(main.GeocodeRequest(area="be-vlg"))
    assert calls == [("BE-VLG", {"addressdetails": True, "country_codes": "be", "exactly_one": False, "limit": 5})]
    assert out == {"lat": 51.0377778, "lon": 4.2405556, "country_code": "BE", "postcode": None,
                   "display_name": "Vlaanderen, België / Belgique / Belgien", "fidelity": "region", "area": "BE-VLG"}


@pytest.mark.asyncio
async def test_geocode_a_region_skips_the_provinces_inside_it(monkeypatch):
    _stub(monkeypatch, [WEST_FLANDERS, FLANDERS])
    out = await main.geocode(main.GeocodeRequest(area="BE-VLG"))
    assert (out["lat"], out["lon"], out["fidelity"]) == (51.0377778, 4.2405556, "region")


@pytest.mark.asyncio
async def test_geocode_only_provinces_is_no_result(monkeypatch):
    _stub(monkeypatch, [WEST_FLANDERS])
    out = await main.geocode(main.GeocodeRequest(area="BE-VLG"))
    assert out["lat"] is None and out["area"] == "BE-VLG"


@pytest.mark.asyncio
async def test_geocode_a_region_nominatim_files_under_region_not_state(monkeypatch):
    _stub(monkeypatch, BRUSSELS)
    out = await main.geocode(main.GeocodeRequest(area="BE-BRU"))
    assert (out["lat"], out["fidelity"], out["area"]) == (50.8387951, "region", "BE-BRU")


@pytest.mark.asyncio
async def test_geocode_a_country_by_its_code(monkeypatch):
    calls = _stub(monkeypatch, BELGIUM)
    out = await main.geocode(main.GeocodeRequest(area="BE"))
    assert calls == [({"country": "BE"}, {"addressdetails": True, "featuretype": "country", "country_codes": "be"})]
    assert (out["lat"], out["lon"], out["country_code"], out["fidelity"], out["area"]) == (50.6402809, 4.6667145, "BE", "country", "BE")


@pytest.mark.asyncio
async def test_geocode_an_answer_for_another_area_is_no_result(monkeypatch):
    _stub(monkeypatch, FLANDERS)
    out = await main.geocode(main.GeocodeRequest(area="BE-WAL"))
    assert out["lat"] is None and out["fidelity"] is None and out["area"] == "BE-WAL"


@pytest.mark.asyncio
async def test_geocode_no_result_for_an_area(monkeypatch):
    _stub(monkeypatch, None)
    out = await main.geocode(main.GeocodeRequest(area="BE-VLG"))
    assert out["lat"] is None and out["display_name"] is None and out["area"] == "BE-VLG"


@pytest.mark.asyncio
@pytest.mark.parametrize("area", ["Flanders", "BE_VLG", "B", "BE-VLGX", "be-"])
async def test_geocode_refuses_what_is_not_an_iso_code(monkeypatch, area):
    calls = _stub(monkeypatch, FLANDERS)
    with pytest.raises(HTTPException) as err:
        await main.geocode(main.GeocodeRequest(area=area))
    assert err.value.status_code == 422 and calls == []


@pytest.mark.asyncio
async def test_geocode_needs_an_address_or_an_area(monkeypatch):
    calls = _stub(monkeypatch, FLANDERS)
    with pytest.raises(HTTPException) as err:
        await main.geocode(main.GeocodeRequest())
    assert err.value.status_code == 422 and calls == []


@pytest.mark.asyncio
async def test_geocode_an_address_as_before(monkeypatch):
    """mom-home's request (address + city) keeps its answer; two keys are added."""
    loc = Location("Rue Royale 1, 1000 Bruxelles, Belgique", (50.85, 4.36, 0), {"address": {"postcode": "1000", "country_code": "be"}})
    calls = _stub(monkeypatch, loc)
    out = await main.geocode(main.GeocodeRequest(address="Rue Royale 1", city="Brussels"))
    assert calls == [("Rue Royale 1, Brussels", {"addressdetails": True})]
    assert out == {"lat": 50.85, "lon": 4.36, "country_code": "BE", "postcode": "1000",
                   "display_name": "Rue Royale 1, 1000 Bruxelles, Belgique", "fidelity": "exact", "area": None}


# ── Geocode: an area by its name, anywhere (2026-11-19) ─────────────────────
# Nominatim's answers as seen live on 2026-11-19 (format json, addressdetails, accept-language en),
# trimmed to the keys read, in Nominatim's own key order: the place's ISO key follows its own component.

def _found(display, lat, lon, addresstype, name, address):
    return Location(display, (lat, lon, 0), {"addresstype": addresstype, "name": name, "display_name": display,
                                              "lat": str(lat), "lon": str(lon), "address": address})


S_FLANDERS = _found("Flanders, Belgium", 51.0377778, 4.2405556, "state", "Flanders",
                    {"state": "Flanders", "ISO3166-2-lvl4": "BE-VLG", "country": "Belgium", "country_code": "be"})
S_SCOTLAND = _found("Scotland, United Kingdom", 56.7861112, -4.1140518, "state", "Scotland",
                    {"state": "Scotland", "ISO3166-2-lvl4": "GB-SCT", "country": "United Kingdom", "country_code": "gb"})
# A county in North Carolina: its only ISO key is its state's.
S_SCOTLAND_COUNTY = _found("Scotland County, North Carolina, United States", 34.8628902, -79.4903372, "county", "Scotland County",
                           {"county": "Scotland County", "state": "North Carolina", "ISO3166-2-lvl4": "US-NC",
                            "country": "United States", "country_code": "us"})
S_BELGIUM = _found("Belgium", 50.6402809, 4.6667145, "country", "Belgium", {"country": "Belgium", "country_code": "be"})
# A province with a code of its own (lvl6) inside a region (lvl4): Nominatim files it as a state.
S_WEST_FLANDERS = _found("West Flanders, Flanders, Belgium", 51.0404747, 2.9994213, "state", "West Flanders",
                         {"state": "West Flanders", "ISO3166-2-lvl6": "BE-VWV", "ISO3166-2-lvl4": "BE-VLG",
                          "country": "Belgium", "country_code": "be"})
# A city that carries a code (Paris is also a département): a city all the same, left out.
S_PARIS = _found("Paris, Ile-de-France, Metropolitan France, France", 48.8534951, 2.3483915, "city", "Paris",
                 {"city": "Paris", "ISO3166-2-lvl6": "FR-75C", "state": "Ile-de-France", "ISO3166-2-lvl4": "FR-IDF",
                  "region": "Metropolitan France", "country": "France", "country_code": "fr"})
# A province without a code of its own: only its region's comes with it.
S_LIMBURG_NO_CODE = _found("Limburg, Flanders, Belgium", 51.0, 5.4, "province", "Limburg",
                           {"province": "Limburg", "state": "Flanders", "ISO3166-2-lvl4": "BE-VLG", "country": "Belgium", "country_code": "be"})


@pytest.mark.asyncio
async def test_area_search_keeps_countries_and_subdivisions_with_their_own_code(monkeypatch):
    calls = _stub(monkeypatch, [S_SCOTLAND, S_SCOTLAND_COUNTY, S_PARIS, S_LIMBURG_NO_CODE, S_WEST_FLANDERS, S_BELGIUM])
    out = await main.geocode(main.GeocodeRequest(area_search="  Scotland "))
    assert calls == [("Scotland", {"addressdetails": True, "exactly_one": False, "limit": 10, "language": "en"})]
    assert out == {"candidates": [
        {"code": "GB-SCT", "name": "Scotland", "display_name": "Scotland, United Kingdom",
         "lat": 56.7861112, "lon": -4.1140518, "fidelity": "region"},
        {"code": "BE-VWV", "name": "West Flanders", "display_name": "West Flanders, Flanders, Belgium",
         "lat": 51.0404747, "lon": 2.9994213, "fidelity": "region"},
        {"code": "BE", "name": "Belgium", "display_name": "Belgium", "lat": 50.6402809, "lon": 4.6667145, "fidelity": "country"},
    ]}


@pytest.mark.asyncio
async def test_area_search_finds_a_region_nominatim_files_as_a_county(monkeypatch):
    """Brussels-Capital comes back a `county` that its address also names as `region`, its code after it."""
    office = _found("Assemblée de la Commission communautaire française, Rue du Lombard, Bruxelles", 50.84, 4.35, "office",
                    "Assemblée de la Commission communautaire française",
                    {"office": "Assemblée de la Commission communautaire française", "road": "Rue du Lombard",
                     "city": "Brussels", "region": "Brussels-Capital", "ISO3166-2-lvl4": "BE-BRU", "country_code": "be"})
    region = _found("Brussels-Capital, Belgium", 50.8387951, 4.3753041, "county", "Brussels-Capital",
                    {"county": "Brussels-Capital", "region": "Brussels-Capital", "ISO3166-2-lvl4": "BE-BRU",
                     "country": "Belgium", "country_code": "be"})
    _stub(monkeypatch, [office, region, S_SCOTLAND_COUNTY])
    out = await main.geocode(main.GeocodeRequest(area_search="Brussels-Capital Region"))
    assert [(c["code"], c["name"], c["fidelity"]) for c in out["candidates"]] == [("BE-BRU", "Brussels-Capital", "region")]


@pytest.mark.asyncio
async def test_area_search_gives_each_code_once_in_nominatim_s_order(monkeypatch):
    vlaanderen = _found("Vlaanderen, België", 51.0, 4.2, "state", "Vlaanderen",
                        {"state": "Vlaanderen", "ISO3166-2-lvl4": "BE-VLG", "country": "België", "country_code": "be"})
    _stub(monkeypatch, [S_BELGIUM, S_FLANDERS, vlaanderen] + [S_BELGIUM] * 3)
    out = await main.geocode(main.GeocodeRequest(area_search="Flanders"))
    assert [(c["code"], c["name"]) for c in out["candidates"]] == [("BE", "Belgium"), ("BE-VLG", "Flanders")]


@pytest.mark.asyncio
async def test_area_search_answers_at_most_five(monkeypatch):
    many = [_found(f"State {i}", 1.0, 2.0, "state", f"State {i}", {"state": f"State {i}", "ISO3166-2-lvl4": f"US-A{i}", "country_code": "us"})
            for i in range(8)]
    _stub(monkeypatch, many)
    out = await main.geocode(main.GeocodeRequest(area_search="State"))
    assert [c["code"] for c in out["candidates"]] == ["US-A0", "US-A1", "US-A2", "US-A3", "US-A4"]


@pytest.mark.asyncio
async def test_area_search_names_come_in_the_language_asked(monkeypatch):
    unnamed = _found("Vlaanderen, België / Belgique / Belgien", 51.0, 4.2, "state", "",
                     {"state": "Vlaanderen", "ISO3166-2-lvl4": "BE-VLG", "country_code": "be"})
    calls = _stub(monkeypatch, [unnamed])
    out = await main.geocode(main.GeocodeRequest(area_search="Vlaanderen", lang="NL"))
    assert calls[0][1]["language"] == "nl"
    assert out["candidates"][0]["name"] == "Vlaanderen"  # no `name`: the first part of display_name


@pytest.mark.asyncio
async def test_area_search_nothing_found_is_no_candidates(monkeypatch):
    _stub(monkeypatch, None)
    assert await main.geocode(main.GeocodeRequest(area_search="Atlantis")) == {"candidates": []}
    _stub(monkeypatch, [S_PARIS, S_SCOTLAND_COUNTY])
    assert await main.geocode(main.GeocodeRequest(area_search="Paris")) == {"candidates": []}


@pytest.mark.asyncio
@pytest.mark.parametrize("body", [{"area_search": ""}, {"area_search": "   "}, {"area_search": "x" * 101},
                                  {"area_search": "Flanders", "lang": "eng"}, {"area_search": "Flanders", "lang": ""},
                                  {"area_search": "Flanders", "lang": "e1"}])
async def test_area_search_refuses_an_empty_or_long_search_or_a_bad_lang(monkeypatch, body):
    calls = _stub(monkeypatch, [S_FLANDERS])
    with pytest.raises(HTTPException) as err:
        await main.geocode(main.GeocodeRequest(**body))
    assert err.value.status_code == 422 and calls == []


@pytest.mark.asyncio
async def test_area_search_nominatim_down_is_503(monkeypatch):
    from geopy.exc import GeocoderUnavailable

    def down(query, **kwargs):
        raise GeocoderUnavailable("down")

    monkeypatch.setattr(main, "_geocode", down)
    with pytest.raises(HTTPException) as err:
        await main.geocode(main.GeocodeRequest(area_search="Flanders"))
    assert err.value.status_code == 503
