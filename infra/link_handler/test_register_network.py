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
NETWORK = URIRef("urn:mak:network/maakbib")  # its own entity (M1, 2026-11-19)


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
    """Its own prefix and its own id: the seeded space keeps `maakbib`, the network is `network_maakbib`."""
    monkeypatch.setenv("SNAPSHOT_DB_PATH", str(tmp_path / "snap.db"))
    with StoreOxigraph(SEEDED_MAAKBIB) as ox:
        monkeypatch.setattr(main, "OXIGRAPH_ENDPOINT", ox.url)
        response = await register(space_server, ox, NETWORK_TTL, "text/turtle", "/n")
        assert response["kind"] == "network"
        assert response["space_uri"] == "urn:mak:network/maakbib"
        assert not any("GRAPH <urn:mak:space/maakbib>" in u for u in ox.updates)

        # Both are on the map, each as its own kind.
        rows = ox.select(main._SPARQL_SELECT)
        features = {f["properties"]["id"]: f["properties"] for f in map(main._binding_to_feature, rows)}
    assert set(features) == {"maakbib", "network_maakbib"}
    assert features["maakbib"]["kind"] == "space" and features["maakbib"]["name"] == "MaakBib"
    net = features["network_maakbib"]
    assert net["kind"] == "network" and net["uri"] == "urn:mak:network/maakbib"
    assert net["area_served"] == [{"code": "BE-VLG", "name": "Flanders"}]
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
    """Home registers the same address twice: the second finds the network by its address (endpoint
    dedupe on urn:mak:network/), and its snapshot goes under the network's id, never the seeded space's."""
    from snapshot_store import read_snapshot
    monkeypatch.setenv("SNAPSHOT_DB_PATH", str(tmp_path / "snap.db"))
    with StoreOxigraph(SEEDED_MAAKBIB) as ox:
        monkeypatch.setattr(main, "OXIGRAPH_ENDPOINT", ox.url)
        first = await register(space_server, ox, NETWORK_TTL, "text/turtle", "/n")
        second = await register(space_server, ox, NETWORK_TTL, "text/turtle", "/n")
        found = await main._find_graph_by_endpoint(ox.url, space_server.url_for("/n"))
        graphs = {str(r.g) for r in ox.store.query("SELECT DISTINCT ?g WHERE { GRAPH ?g { ?s ?p ?o } }")}
    assert first["space_uri"] == second["space_uri"] == found == "urn:mak:network/maakbib"
    assert graphs == {"urn:mak:space/maakbib", "urn:mak:network/maakbib"}
    assert read_snapshot("maakbib") is None
    assert read_snapshot("network_maakbib")["payload"]["fields"]["schema:areaServed"] == [{"code": "BE-VLG", "name": "Flanders"}]


@pytest.mark.asyncio
async def test_a_network_registered_before_m1_moves_to_its_own_prefix(space_server, tmp_path, monkeypatch):
    """The live maakbib record: a mom:Network in urn:mak:space/maakbib. Registering its address again
    drops that graph and writes urn:mak:network/maakbib in the same update."""
    monkeypatch.setenv("SNAPSHOT_DB_PATH", str(tmp_path / "snap.db"))
    url = serve(space_server, NETWORK_TTL, "text/turtle", "/n")
    legacy = f"""
INSERT DATA {{ GRAPH <urn:mak:space/maakbib> {{
  <urn:mak:space/maakbib> a <{MOM}Network> ;
    <{SCHEMA}name> "Maakbib" ;
    <{MOM}endpointUrl> <{url}> ;
    <{MOM}source> "self-registered" ;
    <{SCHEMA}geo> [ <{SCHEMA}latitude> 51.0378 ; <{SCHEMA}longitude> 4.2406 ] .
}} }}"""
    with StoreOxigraph(legacy) as ox:
        monkeypatch.setattr(main, "OXIGRAPH_ENDPOINT", ox.url)
        response = await main.register_url(main.UrlRequest(url=url), BackgroundTasks())
        graphs = {str(r.g) for r in ox.store.query("SELECT DISTINCT ?g WHERE { GRAPH ?g { ?s ?p ?o } }")}
        rows = ox.select(main._SPARQL_SELECT)
        again = await main.register_url(main.UrlRequest(url=url), BackgroundTasks())
    assert response["space_uri"] == again["space_uri"] == "urn:mak:network/maakbib"
    assert graphs == {"urn:mak:network/maakbib"}
    assert [main._binding_to_feature(r)["properties"]["id"] for r in rows] == ["network_maakbib"]


@pytest.mark.asyncio
async def test_a_network_gets_no_space_subset_or_level_up_hint(space_server, tmp_path, monkeypatch):
    """No pin, and its hours are contact hours: 'Level up: add openingHours' is a space's ladder."""
    monkeypatch.setenv("SNAPSHOT_DB_PATH", str(tmp_path / "snap.db"))
    with FakeOxigraph() as ox:
        monkeypatch.setattr(main, "OXIGRAPH_ENDPOINT", ox.url)
        response = await register(space_server, ox, NETWORK_JSON, "application/json", "/n")
        g = inserted(ox.updates[-1])
    assert response["next_unlock"] is None and response["subset"] is None
    assert not any(p in (URIRef(MOM + "nextUnlock"), URIRef(MOM + "subset")) for _, p, _ in g)


@pytest.mark.asyncio
@pytest.mark.parametrize("body, content_type", [(NETWORK_TTL, "text/turtle"), (NETWORK_JSON, "application/json")], ids=["turtle", "json"])
async def test_validating_a_network_tells_no_space_ladder(space_server, body, content_type):
    out = await main.validate_url(main.UrlRequest(url=serve(space_server, body, content_type, "/n")))
    assert out["kind"] == "network" and out["schema_valid"] and out["coords_found"]
    assert out["next_unlock"] is None and out["subset"] is None and out["unlock_message"] is None


@pytest.mark.asyncio
async def test_validating_a_space_still_tells_its_ladder(space_server):
    out = await main.validate_url(main.UrlRequest(url=serve(space_server, TTL, "text/turtle", "/s")))
    assert out["kind"] == "space" and out["subset"] in ("mom:required", "mom:card", "spaceapi:compatible")


@pytest.mark.asyncio
async def test_a_space_still_claims_its_seeded_record(space_server, tmp_path, monkeypatch):
    # Where the file is (a seed is claimed by name only within 25 km, 2026-11-21): the Gent seed moved to Anderlecht.
    seeded = (SEEDED_MAAKBIB.replace("MaakBib", "Atelier du Canal").replace("urn:mak:space/maakbib", "urn:mak:space/adc-anderlecht")
              .replace("51.05", "50.85").replace("3.72", "4.33"))
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
    assert first["space_uri"] == "urn:mak:network/maakbib"
    assert second["space_uri"] == "urn:mak:space/maakbib"
    # The map's id comes with the answer, so no client parses the IRI (mom-home's onmap.ts did).
    assert (first["id"], second["id"]) == ("network_maakbib", "maakbib")
    kinds = {f["properties"]["id"]: f["properties"]["kind"] for f in map(main._binding_to_feature, rows)}
    assert kinds == {"network_maakbib": "network", "maakbib": "space"}


# ── A network's id, its lookups, its members (M1, 2026-11-19) ───────────────

@pytest.mark.parametrize("uri, sid", [
    ("urn:mak:space/weld-done", "weld-done"),
    ("urn:mak:network/maakbib", "network_maakbib"),
    ("urn:mak:canary/mother-sands", "mother-sands"),
])
def test_ids_and_graphs_go_both_ways(uri, sid):
    assert main._id_of(uri) == sid
    graph, subject = main._graph_of(sid)
    assert subject == uri and graph == (uri if "canary" not in uri else "urn:mak:canary")
    assert main._SPACE_ID_RE.match(sid)


@pytest.mark.asyncio
async def test_the_heartbeat_ticks_a_network_under_its_own_graph_and_id(space_server, tmp_path, monkeypatch):
    monkeypatch.setenv("SNAPSHOT_DB_PATH", str(tmp_path / "snap.db"))
    with StoreOxigraph() as ox:
        monkeypatch.setattr(main, "OXIGRAPH_ENDPOINT", ox.url)
        await register(space_server, ox, NETWORK_TTL, "text/turtle", "/n")
        claimed = await main._query_all_claimed_spaces(ox.url)
        ticked = []

        async def fake_pipeline(**kw):
            ticked.append(kw)
            return "2026-11-19T12:00:00Z"

        async def no_rematerialize():
            return None

        monkeypatch.setattr(main, "run_space_pipeline", fake_pipeline)
        monkeypatch.setattr(main, "_rematerialize_geojson", no_rematerialize)
        main._manual_refresh_cooldowns.pop("network_maakbib", None)
        out = await main.heartbeat_space("network_maakbib")
    assert [(c["uid"], c["graph_uri"], c["subject"]) for c in claimed] == \
        [("network_maakbib", "urn:mak:network/maakbib", "urn:mak:network/maakbib")]
    assert out["outcome"] == "ok"
    assert (ticked[0]["uid"], ticked[0]["graph_uri"], ticked[0]["subject"]) == \
        ("network_maakbib", "urn:mak:network/maakbib", "urn:mak:network/maakbib")


@pytest.mark.asyncio
async def test_space_by_endpoint_answers_a_network_s_id(monkeypatch):
    async def fake(endpoint, url):
        return "urn:mak:network/maakbib"

    monkeypatch.setattr(main, "_find_graph_by_endpoint", fake)
    assert await main.get_space_by_endpoint("https://maakbib.example/network.ttl") == {"id": "network_maakbib"}


def _feature(sid, uri, kind, memberships=(), endpoint=""):
    return {"type": "Feature", "geometry": {"type": "Point", "coordinates": [4.0, 51.0]},
            "properties": {"id": sid, "uri": uri, "kind": kind, "endpoint_url": endpoint,
                           "network_memberships": list(memberships)}}


def test_a_network_s_members_are_the_spaces_that_name_it():
    features = main._link_networks([
        _feature("network_maakbib", "urn:mak:network/maakbib", "network", endpoint="https://maakbib.example/network.ttl"),
        _feature("ingegno", "urn:mak:space/ingegno", "space", ["urn:mak:network/maakbib", "urn:mak:network/vow"]),
        # Names the network by its own file, with the subject's fragment: the same network.
        _feature("weld-done", "urn:mak:space/weld-done", "space", ["https://maakbib.example/network.ttl#space"]),
        _feature("elsewhere", "urn:mak:space/elsewhere", "space", ["urn:mak:network/vow"]),
        # A network in the network is not one of its member spaces.
        _feature("network_sub", "urn:mak:network/sub", "network", ["urn:mak:network/maakbib"]),
    ])
    props = {f["properties"]["id"]: f["properties"] for f in features}
    assert props["network_maakbib"]["members"] == ["ingegno", "weld-done"]
    assert props["network_sub"]["members"] == []
    # One network, one chip: the file's address is read as the network's IRI.
    assert props["weld-done"]["network_memberships"] == ["urn:mak:network/maakbib"]
    assert props["ingegno"]["network_memberships"] == ["urn:mak:network/maakbib", "urn:mak:network/vow"]
    assert "members" not in props["ingegno"]


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
    # No town in this list: a town now brings the areas it sits in (#87, below).
    calls = _stub(monkeypatch, [S_SCOTLAND, S_SCOTLAND_COUNTY, S_LIMBURG_NO_CODE, S_WEST_FLANDERS, S_BELGIUM])
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
    _stub(monkeypatch, [S_SCOTLAND_COUNTY])
    assert await main.geocode(main.GeocodeRequest(area_search="Scotland County")) == {"candidates": []}


# ── #87 (2026-11-20): the ISO list first, typos forgiven; a town brings the areas it sits in ──────

@pytest.fixture(autouse=True)
def _no_centres(monkeypatch):
    """Area centres are cached in the process: each test starts with none."""
    monkeypatch.setattr(main, "_centres", {})


def _stub_by_query(monkeypatch, answers):
    """Nominatim answering by query: a code's lookup (`{area}`'s) and a search differ."""
    calls = []

    def fake(query, **kwargs):
        calls.append((query, kwargs))
        return answers.get(query["country"] if isinstance(query, dict) else query)

    monkeypatch.setattr(main, "_geocode", fake)
    return calls


S_BRUSSELS_REGION = _found("Brussels-Capital, Belgium", 50.8387951, 4.3753041, "county", "Brussels-Capital",
                           {"county": "Brussels-Capital", "region": "Brussels-Capital", "ISO3166-2-lvl4": "BE-BRU",
                            "country": "Belgium", "country_code": "be"})
S_BRUSSELS_CITY = _found("City of Brussels, Brussels-Capital, Belgium", 50.8465573, 4.351697, "city", "City of Brussels",
                         {"city": "City of Brussels", "region": "Brussels-Capital", "ISO3166-2-lvl4": "BE-BRU",
                          "country": "Belgium", "country_code": "be"})
S_GENT = _found("Gent, Oost-Vlaanderen, Vlaanderen, België", 51.0538286, 3.7250121, "city", "Gent",
                {"city": "Gent", "county": "Gent", "province": "Oost-Vlaanderen", "ISO3166-2-lvl6": "BE-VOV",
                 "region": "Vlaanderen", "ISO3166-2-lvl4": "BE-VLG", "country": "België", "country_code": "be"})
S_OOST_VLAANDEREN = _found("Oost-Vlaanderen, Vlaanderen, België", 51.0, 3.8, "province", "Oost-Vlaanderen",
                           {"province": "Oost-Vlaanderen", "ISO3166-2-lvl6": "BE-VOV", "region": "Vlaanderen",
                            "ISO3166-2-lvl4": "BE-VLG", "country_code": "be"})
S_VLAANDEREN = _found("Vlaanderen, België", 51.0377778, 4.2405556, "region", "Vlaanderen",
                      {"region": "Vlaanderen", "ISO3166-2-lvl4": "BE-VLG", "country_code": "be"})
S_IDF = _found("Ile-de-France, France", 48.6443057, 2.7537863, "state", "Ile-de-France",
               {"state": "Ile-de-France", "ISO3166-2-lvl4": "FR-IDF", "country": "France", "country_code": "fr"})
_LOOKUP = {"country_codes": "be", "exactly_one": False, "limit": 5, "addressdetails": True}


@pytest.mark.asyncio
async def test_area_search_forgives_a_typo_in_an_iso_name(monkeypatch):
    """Seen 2026-11-20: Nominatim found nothing for it; the ISO list has "Bruxelles-Capitale, Région de"."""
    calls = _stub_by_query(monkeypatch, {"BE-BRU": [S_BRUSSELS_REGION]})
    out = await main.geocode(main.GeocodeRequest(area_search="region bruxellles capitale", lang="fr"))
    assert calls == [("region bruxellles capitale", {"addressdetails": True, "exactly_one": False, "limit": 10, "language": "fr"}),
                     ("BE-BRU", _LOOKUP)]
    assert out == {"candidates": [
        {"code": "BE-BRU", "name": "Région de Bruxelles-Capitale", "display_name": "Région de Bruxelles-Capitale, Belgique",
         "lat": 50.8387951, "lon": 4.3753041, "fidelity": "region"},
    ]}


@pytest.mark.asyncio
async def test_area_search_reads_every_local_name(monkeypatch):
    """Brussels' Dutch name is in pycountry as a translation of the French one: an exact match, in Dutch."""
    _stub_by_query(monkeypatch, {"BE-BRU": [S_BRUSSELS_REGION]})
    out = await main.geocode(main.GeocodeRequest(area_search="Brussels Hoofdstedelijk Gewest", lang="nl"))
    assert [(c["code"], c["name"]) for c in out["candidates"]][:1] == [("BE-BRU", "Brussels Hoofdstedelijk Gewest")]


@pytest.mark.asyncio
async def test_area_search_a_town_brings_the_area_it_sits_in(monkeypatch):
    calls = _stub_by_query(monkeypatch, {"Brussels": [S_BRUSSELS_CITY], "BE-BRU": [S_BRUSSELS_REGION]})
    out = await main.geocode(main.GeocodeRequest(area_search="Brussels"))
    assert [q for q, _ in calls] == ["Brussels", "BE-BRU"]
    assert out == {"candidates": [
        {"code": "BE-BRU", "name": "Brussels-Capital", "display_name": "Brussels-Capital, Belgium",
         "lat": 50.8387951, "lon": 4.3753041, "fidelity": "region"},
    ]}


@pytest.mark.asyncio
async def test_area_search_a_town_brings_its_province_then_its_region(monkeypatch):
    calls = _stub_by_query(monkeypatch, {"Gent": [S_GENT], "BE-VOV": [S_OOST_VLAANDEREN], "BE-VLG": [S_VLAANDEREN]})
    out = await main.geocode(main.GeocodeRequest(area_search="Gent", lang="nl"))
    assert [q for q, _ in calls] == ["Gent", "BE-VOV", "BE-VLG"]
    assert [(c["code"], c["name"], c["lat"]) for c in out["candidates"]] == [
        ("BE-VOV", "Oost-Vlaanderen", 51.0), ("BE-VLG", "Vlaanderen", 51.0377778)]


@pytest.mark.asyncio
async def test_area_search_a_town_that_is_an_area_comes_first_then_its_region(monkeypatch):
    """Paris is a city and an ISO area of its own (FR-75C, the exact local match), inside Île-de-France."""
    paris_area = _found("Paris, Ile-de-France, France", 48.8588897, 2.3200410, "city", "Paris",
                        {"city": "Paris", "ISO3166-2-lvl6": "FR-75C", "state": "Ile-de-France", "ISO3166-2-lvl4": "FR-IDF",
                         "country_code": "fr"})
    _stub_by_query(monkeypatch, {"Paris": [S_PARIS, S_SCOTLAND_COUNTY], "FR-75C": [paris_area], "FR-IDF": [S_IDF]})
    out = await main.geocode(main.GeocodeRequest(area_search="Paris"))
    assert [(c["code"], c["name"]) for c in out["candidates"]] == [("FR-75C", "Paris"), ("FR-IDF", "Ile-de-France")]


@pytest.mark.asyncio
async def test_area_search_a_town_s_code_that_is_not_iso_is_skipped(monkeypatch):
    town = _found("Somewhere, Brussels-Capital, Belgium", 50.8, 4.3, "town", "Somewhere",
                  {"town": "Somewhere", "ISO3166-2-lvl8": "BE-ZZZ", "region": "Brussels-Capital", "ISO3166-2-lvl4": "BE-BRU",
                   "country_code": "be"})
    calls = _stub_by_query(monkeypatch, {"Somewhere": [town], "BE-BRU": [S_BRUSSELS_REGION]})
    out = await main.geocode(main.GeocodeRequest(area_search="Somewhere"))
    assert [q for q, _ in calls] == ["Somewhere", "BE-BRU"]
    assert [c["code"] for c in out["candidates"]] == ["BE-BRU"]


@pytest.mark.asyncio
async def test_area_search_an_iso_match_nominatim_also_found_costs_no_lookup(monkeypatch):
    """"Scotland" is an exact ISO name and Nominatim's own answer: its name, centre, display_name, one call."""
    calls = _stub_by_query(monkeypatch, {"Scotland": [S_SCOTLAND]})
    out = await main.geocode(main.GeocodeRequest(area_search="Scotland"))
    assert len(calls) == 1
    assert out["candidates"] == [{"code": "GB-SCT", "name": "Scotland", "display_name": "Scotland, United Kingdom",
                                  "lat": 56.7861112, "lon": -4.1140518, "fidelity": "region"}]


@pytest.mark.asyncio
async def test_area_search_asks_a_centre_once(monkeypatch):
    calls = _stub_by_query(monkeypatch, {"Brussels": [S_BRUSSELS_CITY], "BE-BRU": [S_BRUSSELS_REGION]})
    first = await main.geocode(main.GeocodeRequest(area_search="Brussels"))
    again = await main.geocode(main.GeocodeRequest(area_search="Brussels"))
    assert first == again
    assert [q for q, _ in calls] == ["Brussels", "BE-BRU", "Brussels"]


@pytest.mark.asyncio
async def test_area_search_a_centre_nominatim_lacks_leaves_the_area_out(monkeypatch):
    calls = _stub_by_query(monkeypatch, {"Brussels": [S_BRUSSELS_CITY]})
    assert await main.geocode(main.GeocodeRequest(area_search="Brussels")) == {"candidates": []}
    assert [q for q, _ in calls] == ["Brussels", "BE-BRU"]


@pytest.mark.asyncio
async def test_area_search_asks_at_most_three_centres(monkeypatch):
    towns = [_found(f"T{code}", 1.0, 2.0, "town", f"T{code}", {"town": f"T{code}", "ISO3166-2-lvl6": code, "country_code": "be"})
             for code in ("BE-VAN", "BE-VBR", "BE-VLI", "BE-VOV", "BE-VWV")]
    calls = _stub_by_query(monkeypatch, {"Towns": towns, **{c: [] for c in ("BE-VAN", "BE-VBR", "BE-VLI", "BE-VOV", "BE-VWV")}})
    await main.geocode(main.GeocodeRequest(area_search="Towns"))
    assert [q for q, _ in calls] == ["Towns", "BE-VAN", "BE-VBR", "BE-VLI"]


@pytest.mark.parametrize("text, codes", [
    ("region bruxellles capitale", ["BE-BRU"]),
    ("Région de Bruxelles-Capitale", ["BE-BRU"]),
    ("Brussels Hoofdstedelijk Gewest", ["BE-BRU"]),
    ("oost vlanderen", ["BE-VOV"]),
    ("Île de France", ["FR-IDF"]),
    ("BAYERN", ["DE-BY"]),
    ("Belgium", ["BE"]),
])
def test_the_iso_list_finds_an_area_by_any_of_its_names(text, codes):
    exact, near = main._iso_matches(text)
    assert codes[0] in exact + near


@pytest.mark.parametrize("text", ["kitchen table", "hello world", "State", "Brussel", "Gent", "Vlaanderen"])
def test_the_iso_list_does_not_guess_from_a_random_word(text):
    """Nothing near enough: Nominatim's search is the answer (Vlaanderen and Gent among them)."""
    assert main._iso_matches(text)[1] == []


def test_the_iso_list_does_not_take_flanders_for_landes():
    exact, near = main._iso_matches("Flanders")
    assert "FR-40" not in exact + near
    exact, near = main._iso_matches("Scotland")
    assert exact[:1] == ["GB-SCT"] and "NZ-STL" not in near


def test_an_inverted_iso_name_is_shown_as_said():
    assert main._said("Bruxelles-Capitale, Région de") == "Région de Bruxelles-Capitale"
    assert main._said("wallonne, Région") == "Région wallonne"
    assert main._said("Southern Nations, Nationalities and Peoples") == "Southern Nations, Nationalities and Peoples"
    assert main._iso_name("BE-BRU", "en") == "Région de Bruxelles-Capitale"  # no English name in pycountry
    assert main._iso_name("BE", "fr") == "Belgique"


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



# ── 2026-11-23: an area named without an ISO code ("Benelux"); a network with no position ──────────

BENELUX_TTL = """@prefix mom: <https://mapsofmaking.org/ns/mom#> .
@prefix schema: <https://schema.org/> .
<#space> a mom:Network, schema:Organization ;
  schema:name "Benelux Makers" ;
  schema:areaServed [ a schema:AdministrativeArea ; schema:name "Benelux" ] ,
                    [ a schema:AdministrativeArea ; schema:identifier "NL" ; schema:name "Netherlands" ] .
"""
BENELUX_JSON = '{"space": "Benelux Makers", "mom": {"kind": "network", "areaServed": [{"name": "Benelux"}, {"code": "NL", "name": "Netherlands"}]}}'


@pytest.mark.asyncio
@pytest.mark.parametrize("body, content_type", [(BENELUX_TTL, "text/turtle"), (BENELUX_JSON, "application/json")], ids=["turtle", "json"])
async def test_a_network_with_a_named_area_and_no_position_registers_and_is_listed(space_server, tmp_path, monkeypatch, body, content_type):
    monkeypatch.setenv("SNAPSHOT_DB_PATH", str(tmp_path / "snap.db"))
    with StoreOxigraph() as ox:
        monkeypatch.setattr(main, "OXIGRAPH_ENDPOINT", ox.url)
        out = await main.validate_url(main.UrlRequest(url=serve(space_server, body, content_type, "/v")))
        response = await register(space_server, ox, body, content_type, "/n")
        g = inserted(ox.updates[-1])
        rows = ox.select(main._SPARQL_SELECT)
    assert out["placeable"] and not out["coords_found"] and "coords_error" not in out
    assert response["kind"] == "network"
    assert not any(p == URIRef(SCHEMA + "geo") for _, p, _ in g)
    named = [a for a in g.objects(None, URIRef(SCHEMA + "areaServed")) if (a, URIRef(SCHEMA + "identifier"), None) not in g]
    assert [str(g.value(a, URIRef(SCHEMA + "name"))) for a in named] == ["Benelux"]
    feature = main._binding_to_feature(rows[0])
    assert feature["geometry"] is None
    assert feature["properties"]["area_served"] == [{"code": "NL", "name": "Netherlands"}, {"code": "", "name": "Benelux"}]


@pytest.mark.asyncio
async def test_a_space_with_no_position_is_still_refused(space_server, tmp_path, monkeypatch):
    body = '{"space": "Nowhere Lab"}'
    monkeypatch.setenv("SNAPSHOT_DB_PATH", str(tmp_path / "snap.db"))
    with FakeOxigraph() as ox:
        monkeypatch.setattr(main, "OXIGRAPH_ENDPOINT", ox.url)
        with pytest.raises(HTTPException) as e:
            await register(space_server, ox, body, "application/json", "/s")
    assert e.value.status_code == 422


@pytest.mark.asyncio
async def test_a_network_with_no_area_and_no_position_is_still_refused(space_server):
    body = '{"space": "Floating Net", "mom": {"kind": "network"}}'
    out = await main.validate_url(main.UrlRequest(url=serve(space_server, body, "application/json", "/n")))
    assert not out["placeable"] and "coords_error" in out


def test_a_space_row_without_a_position_is_not_on_the_map():
    row = {"spaceUri": {"value": "urn:mak:space/x"}, "type": {"value": MOM + "Space"}, "name": {"value": "X"}}
    assert main._binding_to_feature(row) is None
