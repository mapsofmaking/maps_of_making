"""mom-home #74: a network's members, as its welcome tile lists them.

Offline: the network's graph is looked up through a faked _find_graph_by_endpoint, the map's
spaces.geojson is a temporary file, the snapshots a temporary SQLite (as test_moved_to.py).
"""
from __future__ import annotations

import json

import pytest
from fastapi import HTTPException

import main
from snapshot_store import mint_observed_at, write_snapshot

NETWORK_FILE = "https://maakbib.pod.example/space.ttl"


def feature(id_, **props):
    return {"type": "Feature", "geometry": {"type": "Point", "coordinates": [3.6, 51.0]}, "properties": {"id": id_, **props}}


@pytest.fixture
def mapfile(tmp_path, monkeypatch):
    monkeypatch.setenv("SNAPSHOT_DB_PATH", str(tmp_path / "snap.db"))
    path = tmp_path / "spaces.geojson"
    monkeypatch.setattr(main, "GEOJSON_OUTPUT", str(path))
    main._pin_cache.update({"mtime": None, "by_id": {}})

    def draw(*features):
        path.write_text(json.dumps({"type": "FeatureCollection", "features": list(features)}))

    return draw


@pytest.fixture
def graph(monkeypatch):
    found = {"uri": "urn:mak:network/maakbib"}

    async def lookup(_endpoint, url):
        return found["uri"] if url == NETWORK_FILE else None

    monkeypatch.setattr(main, "_find_graph_by_endpoint", lookup)
    return found


@pytest.mark.asyncio
async def test_lists_each_member_with_its_file_and_public_contact(mapfile, graph):
    mapfile(
        feature("network_maakbib", kind="network", members=["ingegno", "on-a-pod", "not-drawn"]),
        feature("ingegno", name="Ingegno", endpoint_url="https://gitlab.example/ingegno.json",
                contact={"email": "hello@ingegno.example", "matrix": "#ingegno:matrix.org", "phone": None}),
        feature("on-a-pod", name="On a pod", endpoint_url="https://on-a-pod.pod.example/space.ttl", contact=None),
        feature("elsewhere", name="Not a member", endpoint_url="https://x.example/a.json"),
    )
    write_snapshot("on-a-pod", mint_observed_at(), {"name": "On a pod", "contact": [{"type": "email", "value": "pod@on-a-pod.example"}]},
                   media_type="text/turtle", raw_text="")
    got = await main.get_network_members(NETWORK_FILE)
    assert got["id"] == "network_maakbib"
    assert got["members"] == [
        {"id": "ingegno", "name": "Ingegno", "endpoint_url": "https://gitlab.example/ingegno.json", "media_type": "application/json",
         "contact": [{"type": "email", "value": "hello@ingegno.example"}, {"type": "matrix", "value": "#ingegno:matrix.org"}]},
        {"id": "on-a-pod", "name": "On a pod", "endpoint_url": "https://on-a-pod.pod.example/space.ttl", "media_type": "text/turtle",
         "contact": [{"type": "email", "value": "pod@on-a-pod.example"}]},
    ]


@pytest.mark.asyncio
async def test_a_network_not_drawn_yet_has_no_members(mapfile, graph):
    mapfile(feature("ingegno", name="Ingegno"))
    assert await main.get_network_members(NETWORK_FILE) == {"id": "network_maakbib", "members": []}


@pytest.mark.asyncio
@pytest.mark.parametrize("uri", [None, "urn:mak:space/ingegno"])
async def test_an_address_that_is_not_a_network_is_404(mapfile, graph, uri):
    mapfile()
    graph["uri"] = uri
    with pytest.raises(HTTPException) as e:
        await main.get_network_members(NETWORK_FILE)
    assert e.value.status_code == 404 and e.value.detail == {"error": "not_a_network"}


@pytest.mark.asyncio
async def test_a_bad_address_is_400(mapfile, graph):
    with pytest.raises(HTTPException) as e:
        await main.get_network_members("not a url")
    assert e.value.status_code == 400
