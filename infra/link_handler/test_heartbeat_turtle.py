"""Story 14.7 S3: the heartbeat follows a Turtle space file as it follows JSON.

Offline: the space file is a local pytest-httpserver, the snapshot store a temp SQLite file,
Oxigraph a fake that keeps the updates it is sent.
"""
from __future__ import annotations

import pytest
from pytest_httpserver import HTTPServer
from rdflib.compare import isomorphic

from fakes import JSON_TEXT, TTL, FakeOxigraph, inserted, serve
from pipeline import fetch_snapshot, fields_for, write_payload_fields
from snapshot_store import read_snapshot

UID = "atelier-du-canal"


@pytest.fixture
def space_server():
    server = HTTPServer(host="127.0.0.1", port=0)
    server.start()
    yield server
    server.clear()
    server.stop()


@pytest.fixture
def db(tmp_path):
    return str(tmp_path / "snap.db")


@pytest.mark.asyncio
async def test_a_turtle_space_is_fetched_and_kept_as_written(space_server, db):
    url = serve(space_server, TTL, "text/turtle")
    snap, changed = await fetch_snapshot(UID, url, db_path=db)
    assert changed is True
    assert snap["media_type"] == "text/turtle" and snap["raw_text"] == TTL
    assert snap["fetch_status"] == "ok" and snap["observed_at"]
    assert snap["payload"]["fields"]["schema:name"] == "Atelier du Canal"
    assert snap["payload"]["contact"] == {"email": "contact@atelierducanal.example", "matrix": "#atelier:matrix.org"}


@pytest.mark.asyncio
async def test_git_raw_text_plain_turtle_and_json_are_read_by_their_content(space_server, db):
    snap, _ = await fetch_snapshot(UID, serve(space_server, TTL, "text/plain; charset=utf-8"), db_path=db)
    assert snap["media_type"] == "text/turtle"
    snap, _ = await fetch_snapshot("json-one", serve(space_server, JSON_TEXT, "text/plain; charset=utf-8"), db_path=db)
    assert snap["media_type"] == "application/json" and snap["raw_text"] is None
    assert snap["payload"]["space"] == "Atelier du Canal"


@pytest.mark.asyncio
async def test_an_unchanged_file_is_not_a_change_and_an_edit_is(space_server, db):
    url = serve(space_server, TTL, "text/turtle")
    _, first = await fetch_snapshot(UID, url, db_path=db)
    _, again = await fetch_snapshot(UID, url, db_path=db)
    assert (first, again) == (True, False)

    edited = TTL.replace("repairs and prototypes", "repairs, prototypes and a lending library")
    snap, changed = await fetch_snapshot(UID, serve(space_server, edited, "text/turtle"), db_path=db)
    assert changed is True and "lending library" in snap["raw_text"]
    assert "lending library" in snap["payload"]["fields"]["schema:description"]


@pytest.mark.asyncio
async def test_a_change_of_contact_alone_counts_as_a_change(space_server, db):
    await fetch_snapshot(UID, serve(space_server, TTL, "text/turtle"), db_path=db)
    moved = TTL.replace("contact@atelierducanal.example", "hello@atelierducanal.example")
    _, changed = await fetch_snapshot(UID, serve(space_server, moved, "text/turtle"), db_path=db)
    assert changed is True


@pytest.mark.asyncio
@pytest.mark.parametrize("body, content_type, reason", [
    ("<html><body>Maintenance</body></html>", "text/html", "text/html"),
    ("<#space> schema:name .", "text/turtle", "Invalid Turtle"),
    ('{"space": ', "application/json", "Invalid JSON at line 1"),
    ("just some words", "text/plain", "neither JSON nor Turtle"),
])
async def test_an_unusable_answer_marks_the_space_unreachable_and_says_why(space_server, db, body, content_type, reason):
    await fetch_snapshot(UID, serve(space_server, TTL, "text/turtle"), db_path=db)
    before = read_snapshot(UID, db_path=db)["observed_at"]
    snap, changed = await fetch_snapshot(UID, serve(space_server, body, content_type), db_path=db)
    assert (snap, changed) == (None, False)
    row = read_snapshot(UID, db_path=db)
    assert row["fetch_status"] == "unreachable" and reason in row["fetch_error"]
    assert row["observed_at"] == before  # an unreachable fetch never re-stamps


@pytest.mark.asyncio
async def test_http_errors_are_as_before(space_server, db):
    await fetch_snapshot(UID, serve(space_server, TTL, "text/turtle"), db_path=db)
    space_server.clear()
    space_server.expect_request("/space").respond_with_data("gone", status=503)
    snap, _ = await fetch_snapshot(UID, space_server.url_for("/space"), db_path=db)
    assert snap is None and read_snapshot(UID, db_path=db)["fetch_error"] == "HTTP 503"


@pytest.mark.asyncio
async def test_the_request_asks_for_turtle_first(space_server, db):
    from werkzeug.wrappers import Response
    seen = {}

    def handler(request):
        seen["accept"] = request.headers.get("Accept")
        seen["ua"] = request.headers.get("User-Agent")
        return Response(TTL, content_type="text/turtle")

    space_server.expect_request("/space").respond_with_handler(handler)
    await fetch_snapshot(UID, space_server.url_for("/space"), db_path=db)
    assert seen["accept"].startswith("text/turtle") and "MapsOfMaking-heartbeat" in seen["ua"]


@pytest.mark.asyncio
async def test_old_snapshot_rows_read_as_json(db):
    import sqlite3
    from snapshot_store import init_snapshot_db
    init_snapshot_db(db)
    con = sqlite3.connect(db)
    con.execute("INSERT INTO snapshots (uid, observed_at, payload) VALUES ('old', '2026-01-01T00:00:00Z', '{\"space\":\"Old\"}')")
    con.commit()
    con.close()
    row = read_snapshot("old", db_path=db)
    assert row["media_type"] == "application/json" and row["raw_text"] is None and row["payload"] == {"space": "Old"}


# ── What the heartbeat writes to the graph ──────────────────────────────────

@pytest.mark.asyncio
async def test_fields_are_the_same_for_both_formats(space_server, db):
    t, _ = await fetch_snapshot("t", serve(space_server, TTL, "text/turtle"), db_path=db)
    j, _ = await fetch_snapshot("j", serve(space_server, JSON_TEXT, "application/json"), db_path=db)
    from_json = fields_for(j)
    from_json.pop("schema:contactJson")  # kept in the index by the JSON path only, by decision
    assert fields_for(t) == from_json


@pytest.mark.asyncio
async def test_write_payload_fields_writes_the_same_statements_for_both(space_server, db):
    t, _ = await fetch_snapshot("t", serve(space_server, TTL, "text/turtle"), db_path=db)
    j, _ = await fetch_snapshot("j", serve(space_server, JSON_TEXT, "application/json"), db_path=db)
    graphs = []
    for snap in (t, j):
        with FakeOxigraph() as ox:
            await write_payload_fields("x", snap["payload"], "urn:mak:space/x", "urn:mak:space/x", ox.url, fields=fields_for(snap))
        graphs.append(inserted("\n".join(ox.updates)))
    from rdflib import Graph
    drop = "https://schema.org/contactJson"
    a, b = (Graph() for _ in range(2))
    for g, out in zip(graphs, (a, b)):
        for s, p, o in g:
            if str(p) != drop:
                out.add((s, p, o))
    assert len(a) == 4 and isomorphic(a, b)  # address, locality, country code, description (name and geo are the registration anchor)


@pytest.mark.asyncio
async def test_write_payload_fields_never_writes_freshness_predicates_for_turtle(space_server, db):
    t, _ = await fetch_snapshot("t", serve(space_server, TTL, "text/turtle"), db_path=db)
    with FakeOxigraph() as ox:
        await write_payload_fields("x", t["payload"], "urn:mak:space/x", "urn:mak:space/x", ox.url, fields=fields_for(t))
    body = "\n".join(ox.updates)
    for pred in ("observedAt", "updatedAt", "openNow", "lastOpenChange"):
        assert f"mom#{pred}" not in body


def _apply(updates: list[str], before: str, graph_uri: str):
    """The updates run on a real store holding `before` in `graph_uri` (rdflib's SPARQL Update), read back."""
    from rdflib import Dataset, URIRef
    ds = Dataset()
    ds.graph(URIRef(graph_uri)).parse(data=before, format="turtle")
    for update in updates:
        ds.update(update)
    return ds.graph(URIRef(graph_uri))


_BEFORE = """
@prefix schema: <https://schema.org/> . @prefix mom: <https://mapsofmaking.org/ns/mom#> .
<urn:mak:space/x> a mom:Space ; schema:name "Atelier" ;
  schema:geo [ schema:latitude 1.0 ; schema:longitude 2.0 ] ;
  mom:geolocationFidelity "city-level" ; mom:geolocationNote "pinned to the city centre" .
"""


@pytest.mark.asyncio
async def test_a_space_s_own_turtle_moves_its_pin(space_server, db):
    """Story 14.6 AC1b (mom-home #40): the file's new coordinates replace the old pin, nothing of it left over."""
    t, _ = await fetch_snapshot("t", serve(space_server, TTL, "text/turtle"), db_path=db)
    lat, lon = t["payload"]["fields"]["schema:geo"]["lat"], t["payload"]["fields"]["schema:geo"]["lon"]
    with FakeOxigraph() as ox:
        await write_payload_fields("x", t["payload"], "urn:mak:space/x", "urn:mak:space/x", ox.url, fields=fields_for(t), moves=True)
    g = _apply(ox.updates, _BEFORE, "urn:mak:space/x")
    q = """PREFIX schema: <https://schema.org/> SELECT ?lat ?lon WHERE { <urn:mak:space/x> schema:geo ?g . ?g schema:latitude ?lat ; schema:longitude ?lon }"""
    assert [(float(r.lat), float(r.lon)) for r in g.query(q)] == [(lat, lon)]
    # The old node's coordinates went with it, and the seed's word on how exact the old pin was.
    assert len([o for _, p, o in g if str(p) == "https://schema.org/latitude"]) == 1
    assert not [p for _, p, _ in g if "geolocation" in str(p)]
    assert any(str(p) == "https://schema.org/name" for _, p, _ in g)  # the rest of the space stays


@pytest.mark.asyncio
async def test_a_spaceapi_payload_keeps_the_registration_pin(space_server, db):
    j, _ = await fetch_snapshot("j", serve(space_server, JSON_TEXT, "application/json"), db_path=db)
    with FakeOxigraph() as ox:
        await write_payload_fields("x", j["payload"], "urn:mak:space/x", "urn:mak:space/x", ox.url, fields=fields_for(j))
    g = _apply(ox.updates, _BEFORE, "urn:mak:space/x")
    q = """PREFIX schema: <https://schema.org/> SELECT ?lat WHERE { <urn:mak:space/x> schema:geo/schema:latitude ?lat }"""
    assert [float(r.lat) for r in g.query(q)] == [1.0]
    assert any("geolocationFidelity" in str(p) for _, p, _ in g)


@pytest.mark.asyncio
async def test_an_unmoved_pin_keeps_the_seed_s_notes(space_server, db):
    """Only a real move drops how exact the old pin was: an hours edit leaves it (review of #76)."""
    t, _ = await fetch_snapshot("t", serve(space_server, TTL, "text/turtle"), db_path=db)
    lat, lon = t["payload"]["fields"]["schema:geo"]["lat"], t["payload"]["fields"]["schema:geo"]["lon"]
    with FakeOxigraph() as ox:
        await write_payload_fields("x", t["payload"], "urn:mak:space/x", "urn:mak:space/x", ox.url, fields=fields_for(t), moves=True)
    g = _apply(ox.updates, _BEFORE.replace("1.0", str(lat)).replace("2.0", str(lon)), "urn:mak:space/x")
    assert any("geolocationFidelity" in str(p) for _, p, _ in g)
    assert len([o for _, p, o in g if str(p) == "https://schema.org/latitude"]) == 1
