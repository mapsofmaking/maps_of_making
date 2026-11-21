"""#85: a space moves from its JSON file to its pod and keeps its id; a same name no longer overwrites.

Offline, as test_register_network.py: files served by a local pytest-httpserver, Oxigraph faked by an
rdflib Dataset (what is already stored matters here).
"""
from __future__ import annotations

import json

import pytest
from fastapi import BackgroundTasks, HTTPException
from pytest_httpserver import HTTPServer

import main
from fakes import JSON_TEXT, NETWORK_TTL, TTL, StoreOxigraph

SPACE = "urn:mak:space/atelier-du-canal"


@pytest.fixture
def files():
    """One server for every file of a test: fakes.serve() clears what was there, a move needs two."""
    server = HTTPServer(host="127.0.0.1", port=0)
    server.start()
    yield server
    server.clear()
    server.stop()


@pytest.fixture(autouse=True)
def _snapshots(tmp_path, monkeypatch):
    monkeypatch.setenv("SNAPSHOT_DB_PATH", str(tmp_path / "snap.db"))


@pytest.fixture(autouse=True)
def _no_background(monkeypatch):
    """The first tick and the rebuild run after the answer; nothing here depends on them."""
    async def nothing(*a, **kw):
        return None

    monkeypatch.setattr(main, "run_space_pipeline", nothing)
    monkeypatch.setattr(main, "_rematerialize_geojson", nothing)


def put(server, path, body, content_type):
    server.expect_request(path).respond_with_data(body, content_type=content_type)
    return server.url_for(path)


def old_json(moved_to=None):
    data = json.loads(JSON_TEXT)
    if moved_to is not None:
        data.setdefault("mom", {})["movedTo"] = moved_to
    return json.dumps(data)


async def register(url, replaces=None):
    return await main.register_url(main.UrlRequest(url=url, replaces=replaces), BackgroundTasks())


def graphs(ox):
    return {str(r.g) for r in ox.store.query("SELECT DISTINCT ?g WHERE { GRAPH ?g { ?s ?p ?o } }")}


def endpoints(ox):
    return {str(r.g): str(r.u) for r in ox.store.query(
        "SELECT ?g ?u WHERE { GRAPH ?g { ?s <https://mapsofmaking.org/ns/mom#endpointUrl> ?u } }")}


async def refused(url, replaces=None):
    with pytest.raises(HTTPException) as err:
        await register(url, replaces)
    assert err.value.status_code == 409
    return err.value.detail


# ── The hole closed: a name is not enough ───────────────────────────────────

@pytest.mark.asyncio
async def test_a_file_with_the_same_name_does_not_overwrite_a_registered_space(files, monkeypatch):
    with StoreOxigraph() as ox:
        monkeypatch.setattr(main, "OXIGRAPH_ENDPOINT", ox.url)
        first = put(files, "/old.json", old_json(), "application/json")
        other = put(files, "/someone-else.ttl", TTL, "text/turtle")
        await register(first)
        before = endpoints(ox)
        detail = await refused(other)
        assert endpoints(ox) == before == {SPACE: first}
    assert detail["error"] == "name_taken"
    assert detail["id"] == "atelier-du-canal" and detail["replaces"] == first
    assert detail["add"] == {"mom": {"movedTo": other}}


@pytest.mark.asyncio
async def test_registering_the_same_address_again_is_still_fine(files, monkeypatch):
    with StoreOxigraph() as ox:
        monkeypatch.setattr(main, "OXIGRAPH_ENDPOINT", ox.url)
        url = put(files, "/old.json", old_json(), "application/json")
        a = await register(url)
        b = await register(url)
    assert a["id"] == b["id"] == "atelier-du-canal" and b["moved_from"] is None


@pytest.mark.asyncio
async def test_a_file_named_like_the_canary_is_refused(files, monkeypatch):
    data = json.loads(JSON_TEXT)
    data["space"] = "Mother Sands"
    with StoreOxigraph() as ox:
        monkeypatch.setattr(main, "OXIGRAPH_ENDPOINT", ox.url)
        url = put(files, "/ms.json", json.dumps(data), "application/json")
        detail = await refused(url)
        assert graphs(ox) == set()
    assert detail["error"] == "name_taken" and detail["id"] == "mother-sands"


@pytest.mark.asyncio
async def test_an_oxigraph_error_refuses_rather_than_overwrites(files, monkeypatch):
    async def down(endpoint, graph_uri):
        raise HTTPException(status_code=503, detail={"error": "triplestore_unavailable"})

    with StoreOxigraph() as ox:
        monkeypatch.setattr(main, "OXIGRAPH_ENDPOINT", ox.url)
        monkeypatch.setattr(main, "_endpoint_in_graph", down)
        url = put(files, "/s.ttl", TTL, "text/turtle")
        with pytest.raises(HTTPException) as err:
            await register(url)
        assert ox.updates == []
    assert err.value.status_code == 503


# ── The move, proven by the old file ────────────────────────────────────────

@pytest.mark.asyncio
async def test_a_proven_move_keeps_the_graph_and_the_id_and_the_heartbeat_follows(files, monkeypatch):
    with StoreOxigraph() as ox:
        monkeypatch.setattr(main, "OXIGRAPH_ENDPOINT", ox.url)
        pod = files.url_for("/pod/space.ttl")
        old = put(files, "/old.json", old_json(moved_to=pod), "application/json")
        put(files, "/pod/space.ttl", TTL, "text/turtle")
        await register(old)
        moved = await register(pod, replaces=old)
        assert graphs(ox) == {SPACE}
        assert endpoints(ox) == {SPACE: pod}
        claimed = await main._query_all_claimed_spaces(ox.url)
        retry = await register(pod, replaces=old)  # the old address matches nothing now: a plain re-registration
    assert moved["id"] == "atelier-du-canal" and moved["space_uri"] == SPACE and moved["moved_from"] == old
    assert [(c["uid"], c["endpoint_url"]) for c in claimed] == [("atelier-du-canal", pod)]
    assert retry["id"] == "atelier-du-canal" and retry["moved_from"] is None


@pytest.mark.asyncio
async def test_a_move_keeps_the_id_when_the_name_changes(files, monkeypatch):
    with StoreOxigraph() as ox:
        monkeypatch.setattr(main, "OXIGRAPH_ENDPOINT", ox.url)
        pod = files.url_for("/pod/space.ttl")
        old = put(files, "/old.json", old_json(moved_to=pod), "application/json")
        put(files, "/pod/space.ttl", TTL.replace("Atelier du Canal", "Canal Werkplaats"), "text/turtle")
        await register(old)
        moved = await register(pod, replaces=old)
        assert graphs(ox) == {SPACE}
    assert moved["id"] == "atelier-du-canal" and moved["space_name"] == "Canal Werkplaats"


@pytest.mark.asyncio
@pytest.mark.parametrize("moved_to, error", [(None, "moved_to_missing"), ("https://elsewhere.example/space.ttl", "moved_to_mismatch")])
async def test_a_move_without_the_proof_is_refused_and_changes_nothing(files, moved_to, error, monkeypatch):
    with StoreOxigraph() as ox:
        monkeypatch.setattr(main, "OXIGRAPH_ENDPOINT", ox.url)
        pod = files.url_for("/pod/space.ttl")
        old = put(files, "/old.json", old_json(moved_to=moved_to), "application/json")
        put(files, "/pod/space.ttl", TTL, "text/turtle")
        await register(old)
        before = endpoints(ox)
        detail = await refused(pod, replaces=old)
        assert endpoints(ox) == before == {SPACE: old}
    assert detail["error"] == error and detail["id"] == "atelier-du-canal"
    assert detail["add"] == {"mom": {"movedTo": pod}}


@pytest.mark.asyncio
async def test_a_move_from_an_address_the_map_does_not_know_is_refused(files, monkeypatch):
    with StoreOxigraph() as ox:
        monkeypatch.setattr(main, "OXIGRAPH_ENDPOINT", ox.url)
        pod = put(files, "/pod/space.ttl", TTL, "text/turtle")
        detail = await refused(pod, replaces=files.url_for("/never-registered.json"))
        assert graphs(ox) == set()
    assert detail["error"] == "replaces_not_found"


@pytest.mark.asyncio
async def test_a_move_whose_old_file_is_gone_is_refused(files, monkeypatch):
    with StoreOxigraph() as ox:
        monkeypatch.setattr(main, "OXIGRAPH_ENDPOINT", ox.url)
        pod = files.url_for("/pod/space.ttl")
        old = put(files, "/old.json", old_json(moved_to=pod), "application/json")
        await register(old)
        files.clear()
        put(files, "/pod/space.ttl", TTL, "text/turtle")  # /old.json now answers 500
        detail = await refused(pod, replaces=old)
        assert endpoints(ox) == {SPACE: old}
    assert detail["error"] == "replaces_unreachable"


@pytest.mark.asyncio
async def test_a_space_cannot_move_into_a_network(files, monkeypatch):
    with StoreOxigraph() as ox:
        monkeypatch.setattr(main, "OXIGRAPH_ENDPOINT", ox.url)
        pod = files.url_for("/pod/network.ttl")
        old = put(files, "/old.json", old_json(moved_to=pod), "application/json")
        put(files, "/pod/network.ttl", NETWORK_TTL, "text/turtle")
        await register(old)
        detail = await refused(pod, replaces=old)
        assert endpoints(ox) == {SPACE: old}
    assert detail["error"] == "kind_changed"


@pytest.mark.asyncio
async def test_the_canary_never_moves(files, monkeypatch):
    seed = """INSERT DATA { GRAPH <urn:mak:canary> {
  <urn:mak:canary/mother-sands> <https://mapsofmaking.org/ns/mom#endpointUrl> <%s> } }"""
    pod = files.url_for("/pod/space.ttl")
    old = put(files, "/canary.json", old_json(moved_to=pod), "application/json")
    put(files, "/pod/space.ttl", TTL, "text/turtle")
    with StoreOxigraph(seed % old) as ox:
        monkeypatch.setattr(main, "OXIGRAPH_ENDPOINT", ox.url)
        detail = await refused(pod, replaces=old)
        assert graphs(ox) == {"urn:mak:canary"}
    assert detail["error"] == "replaces_not_found"


@pytest.mark.asyncio
async def test_a_seed_is_still_claimed_by_name(files, monkeypatch):
    seed = f"""INSERT DATA {{ GRAPH <urn:mak:space/adc-anderlecht> {{
  <urn:mak:space/adc-anderlecht> a <https://mapsofmaking.org/ns/mom#Space> ;
    <https://schema.org/name> "Atelier du Canal" ;
    <https://mapsofmaking.org/ns/mom#source> "scraped-vow" ;
    <https://schema.org/geo> [ <https://schema.org/latitude> 50.85 ; <https://schema.org/longitude> 4.33 ] .
}} }}"""
    with StoreOxigraph(seed) as ox:
        monkeypatch.setattr(main, "OXIGRAPH_ENDPOINT", ox.url)
        url = put(files, "/s.ttl", TTL, "text/turtle")
        out = await register(url)
    assert out["space_uri"] == "urn:mak:space/adc-anderlecht"


# ── Same name: one place is one space, two places are two (2026-11-21) ──────

def elsewhere(address=None, cc="TR", lat=41.0082, lon=28.9784):
    """Atelier du Canal's file, for another workshop of the same name in Istanbul."""
    data = json.loads(JSON_TEXT)
    data["location"] = {"country_code": cc, "lat": lat, "lon": lon, **({"address": address} if address else {})}
    return json.dumps(data)


@pytest.mark.asyncio
async def test_the_same_name_far_away_is_another_space_with_its_own_id(files, monkeypatch):
    with StoreOxigraph() as ox:
        monkeypatch.setattr(main, "OXIGRAPH_ENDPOINT", ox.url)
        first = put(files, "/brussels.json", old_json(), "application/json")
        other = put(files, "/istanbul.json", elsewhere("Moda Cd. 5, 34710 Istanbul, TR"), "application/json")
        await register(first)
        out = await register(other)
        assert endpoints(ox) == {SPACE: first, SPACE + "-istanbul": other}
        # Registering it again finds it by its address, under its own id.
        assert (await register(other))["id"] == "atelier-du-canal-istanbul"
    assert out["id"] == "atelier-du-canal-istanbul"


@pytest.mark.asyncio
async def test_far_away_with_no_town_the_country_tells_them_apart(files, monkeypatch):
    with StoreOxigraph() as ox:
        monkeypatch.setattr(main, "OXIGRAPH_ENDPOINT", ox.url)
        await register(put(files, "/brussels.json", old_json(), "application/json"))
        out = await register(put(files, "/istanbul.json", elsewhere(), "application/json"))
    assert out["id"] == "atelier-du-canal-tr"


@pytest.mark.asyncio
async def test_the_same_name_nearby_under_another_id_is_refused_not_duplicated(files, monkeypatch):
    """Ingegno's case: registered under a seed's id (name + town), its pod under the name alone would be a second pin."""
    registered = f"""INSERT DATA {{ GRAPH <{SPACE}-anderlecht> {{
  <{SPACE}-anderlecht> a <https://mapsofmaking.org/ns/mom#Space> ;
    <https://schema.org/name> "Atelier du Canal" ;
    <https://mapsofmaking.org/ns/mom#source> "self-registered" ;
    <https://mapsofmaking.org/ns/mom#endpointUrl> <https://gitlab.example/adc.json> ;
    <https://schema.org/geo> [ <https://schema.org/latitude> 50.84 ; <https://schema.org/longitude> 4.33 ] .
}} }}"""
    with StoreOxigraph(registered) as ox:
        monkeypatch.setattr(main, "OXIGRAPH_ENDPOINT", ox.url)
        before = endpoints(ox)
        detail = await refused(put(files, "/pod.ttl", TTL, "text/turtle"))
        assert endpoints(ox) == before
    assert detail["error"] == "name_taken"
    assert detail["id"] == "atelier-du-canal-anderlecht" and detail["replaces"] == "https://gitlab.example/adc.json"


# ── A seed is claimed by name only where it is (2026-11-21) ─────────────────

def seed(slug, lat, lon, endpoint=None):
    owner = f"; <https://mapsofmaking.org/ns/mom#endpointUrl> <{endpoint}> " if endpoint else ""
    return f"""INSERT DATA {{ GRAPH <urn:mak:space/{slug}> {{
  <urn:mak:space/{slug}> a <https://mapsofmaking.org/ns/mom#Space> ;
    <https://schema.org/name> "Atelier du Canal" ;
    <https://mapsofmaking.org/ns/mom#source> "scraped-vow" {owner};
    <https://schema.org/geo> [ <https://schema.org/latitude> {lat} ; <https://schema.org/longitude> {lon} ] .
}} }}"""


@pytest.mark.asyncio
async def test_a_seed_of_the_same_name_far_away_is_not_claimed(files, monkeypatch):
    with StoreOxigraph(seed("adc-istanbul", 41.0082, 28.9784)) as ox:
        monkeypatch.setattr(main, "OXIGRAPH_ENDPOINT", ox.url)
        out = await register(put(files, "/s.ttl", TTL, "text/turtle"))
        assert "urn:mak:space/adc-istanbul" in graphs(ox)
    assert out["space_uri"] == SPACE


@pytest.mark.asyncio
async def test_the_nearest_seed_of_that_name_is_the_one_claimed(files, monkeypatch):
    seeds = seed("adc-istanbul", 41.0082, 28.9784) + " ;\n" + seed("adc-anderlecht", 50.85, 4.33)
    with StoreOxigraph(seeds) as ox:
        monkeypatch.setattr(main, "OXIGRAPH_ENDPOINT", ox.url)
        out = await register(put(files, "/s.ttl", TTL, "text/turtle"))
        assert "urn:mak:space/adc-istanbul" in graphs(ox)
    assert out["space_uri"] == "urn:mak:space/adc-anderlecht"


@pytest.mark.asyncio
async def test_registering_again_never_drops_a_far_seed_of_the_same_name(files, monkeypatch):
    with StoreOxigraph(seed("adc-istanbul", 41.0082, 28.9784)) as ox:
        monkeypatch.setattr(main, "OXIGRAPH_ENDPOINT", ox.url)
        url = put(files, "/s.ttl", TTL, "text/turtle")
        await register(url)
        await register(url)
        assert "urn:mak:space/adc-istanbul" in graphs(ox)
