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
    assert (NETWORK, URIRef(SCHEMA + "areaServed"), Literal("BE-VLG")) in g
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
    assert net["kind"] == "network" and net["area_served"] == ["BE-VLG"]
    assert net["geolocationFidelity"] == "region" and net["country_code"] == "BE" and net["address"] == ""


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
    assert read_snapshot("maakbib-network")["payload"]["fields"]["schema:areaServed"] == ["BE-VLG"]


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
