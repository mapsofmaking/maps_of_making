"""Story 14.7 S2: register and validate accept a Turtle space file, as they do JSON.

Offline: the "server" with the space file and a fake Oxigraph are local
pytest-httpserver instances. The last tests register both fixtures through
`register_url` and compare the statements it writes (AC2, AC5 at the registration level).
"""
from __future__ import annotations

import json

import pytest
from fastapi import BackgroundTasks
from pytest_httpserver import HTTPServer
from rdflib import Graph, URIRef
from rdflib.compare import isomorphic
from werkzeug.wrappers import Response

import main
from snapshot_store import read_snapshot

from fakes import JSON_TEXT, TTL, FakeOxigraph, inserted, serve

# What a pod or git host sends for the same bytes.
CASES = [
    ("turtle as text/turtle", TTL, "text/turtle"),
    ("turtle as text/turtle with charset", TTL, "text/turtle; charset=utf-8"),
    ("turtle as text/plain (git raw)", TTL, "text/plain; charset=utf-8"),
    ("turtle as octet-stream", TTL, "application/octet-stream"),
    ("json as application/json", JSON_TEXT, "application/json"),
    ("json as text/plain (GitLab / GitHub raw: the self-host door)", JSON_TEXT, "text/plain; charset=utf-8"),
    ("json as octet-stream", JSON_TEXT, "application/octet-stream"),
]


@pytest.fixture
def space_server():
    server = HTTPServer(host="127.0.0.1", port=0)
    server.start()
    yield server
    server.clear()
    server.stop()


@pytest.mark.asyncio
@pytest.mark.parametrize("label, body, content_type", CASES, ids=[c[0] for c in CASES])
async def test_both_formats_validate_whatever_the_server_calls_them(space_server, label, body, content_type):
    result = await main._fetch_and_validate(serve(space_server, body, content_type))
    assert result["schema_valid"] is True, result
    assert result["name_found"] == "Atelier du Canal"
    assert (result["lat"], result["lon"]) == (50.8391, 4.3297)
    assert result["coords_found"] is True


@pytest.mark.asyncio
async def test_the_request_asks_for_turtle_first(space_server):
    seen = {}

    def handler(request):
        seen["accept"] = request.headers.get("Accept")
        return Response(TTL, content_type="text/turtle")

    space_server.expect_request("/space").respond_with_handler(handler)
    await main._fetch_and_validate(space_server.url_for("/space"))
    assert seen["accept"].startswith("text/turtle")
    assert "application/json" in seen["accept"]


@pytest.mark.asyncio
async def test_compact_key_json_ld_keeps_the_json_path(space_server):
    doc = {"@context": "https://schema.org", "schema:name": "Lab", "schema:geo": {"schema:latitude": 1.5, "schema:longitude": 2.5}}
    result = await main._fetch_and_validate(serve(space_server, json.dumps(doc), "application/ld+json"))
    assert result["name_found"] == "Lab" and result["coords_found"] is True
    assert result["media_type"] == "application/json"


@pytest.mark.asyncio
async def test_turtle_and_json_get_the_same_subset(space_server):
    a = await main._fetch_and_validate(serve(space_server, TTL, "text/turtle", "/a"))
    b = await main._fetch_and_validate(serve(space_server, JSON_TEXT, "application/json", "/b"))
    for key in ("subset", "subset_score", "missing_card_fields", "next_subset", "next_unlock"):
        assert a[key] == b[key], key


# ── AC4: refusal that says what the server sent ─────────────────────────────

@pytest.mark.asyncio
async def test_html_is_refused_with_its_media_type(space_server):
    result = await main._fetch_and_validate(serve(space_server, "<html><body>Oops</body></html>", "text/html; charset=utf-8"))
    assert result["schema_valid"] is False and result["media_type"] == "text/html"
    assert "text/html" in result["error"]


@pytest.mark.asyncio
async def test_a_page_labelled_text_plain_is_still_refused(space_server):
    result = await main._fetch_and_validate(serve(space_server, "<!doctype html><title>404</title>", "text/plain"))
    assert result["schema_valid"] is False and "text/plain" in result["error"]


@pytest.mark.asyncio
async def test_neither_json_nor_turtle_says_so(space_server):
    result = await main._fetch_and_validate(serve(space_server, "just some words, not a file", "text/plain"))
    assert result["schema_valid"] is False
    assert "neither JSON nor Turtle" in result["error"] and "text/plain" in result["error"]


@pytest.mark.asyncio
async def test_an_empty_answer_is_refused(space_server):
    result = await main._fetch_and_validate(serve(space_server, "  \n", "text/plain"))
    assert result["schema_valid"] is False and "empty" in result["error"]


@pytest.mark.asyncio
async def test_broken_json_keeps_its_message(space_server):
    result = await main._fetch_and_validate(serve(space_server, '{"space": ', "application/json"))
    assert result["error"] == "Response is not valid JSON"


@pytest.mark.asyncio
async def test_broken_turtle_says_invalid_turtle(space_server):
    result = await main._fetch_and_validate(serve(space_server, "<#space> schema:name .", "text/turtle"))
    assert result["schema_valid"] is False and result["error"].startswith("Invalid Turtle")


@pytest.mark.asyncio
async def test_turtle_without_coordinates_reports_them_missing(space_server):
    ttl = '@prefix schema: <https://schema.org/> .\n<#space> a schema:Place ; schema:name "Lab" .'
    result = await main._fetch_and_validate(serve(space_server, ttl, "text/turtle"))
    assert result["schema_valid"] is True and result["coords_found"] is False
    assert "schema:geo" in result["coords_error"]


@pytest.mark.asyncio
async def test_http_errors_are_as_before(space_server):
    space_server.expect_request("/gone").respond_with_data("nope", status=404)
    result = await main._fetch_and_validate(space_server.url_for("/gone"))
    assert result["status_code"] == 404 and result["error"] == "HTTP 404"


@pytest.mark.asyncio
async def test_a_file_over_the_cap_is_refused(space_server, monkeypatch):
    import source
    monkeypatch.setattr(source, "MAX_FETCH_BYTES", 100)
    result = await main._fetch_and_validate(serve(space_server, TTL, "text/turtle"))
    assert result["schema_valid"] is False and "smaller files" in result["error"]


# ── Registration: what is written, for both formats ─────────────────────────

async def register(space_server, body, content_type, tmp_path, monkeypatch, path):
    monkeypatch.setenv("SNAPSHOT_DB_PATH", str(tmp_path / f"snap{path.replace('/', '-')}.db"))
    url = serve(space_server, body, content_type, path)
    with FakeOxigraph() as ox:
        monkeypatch.setattr(main, "OXIGRAPH_ENDPOINT", ox.url)
        response = await main.register_url(main.UrlRequest(url=url), BackgroundTasks())
    assert response["status"] == "confirmed", response
    return url, inserted(ox.updates[-1])


# What differs by design: the source's own address, the pod profile, and the contact the JSON path keeps in the index.
ONLY_BY_FORMAT = {
    "https://mapsofmaking.org/ns/mom#endpointUrl",
    "https://mapsofmaking.org/ns/mom#profileUrl",
    "https://schema.org/contactJson",
}


def comparable(g: Graph) -> Graph:
    out = Graph()
    for s, p, o in g:
        if str(p) not in ONLY_BY_FORMAT:
            out.add((s, p, o))
    return out


@pytest.mark.asyncio
async def test_registering_turtle_and_json_writes_the_same_statements(space_server, tmp_path, monkeypatch):
    _, from_ttl = await register(space_server, TTL, "text/turtle", tmp_path, monkeypatch, "/t")
    _, from_json = await register(space_server, JSON_TEXT, "application/json", tmp_path, monkeypatch, "/j")
    assert len(comparable(from_ttl)) > 6
    assert isomorphic(comparable(from_ttl), comparable(from_json))


@pytest.mark.asyncio
async def test_a_turtle_space_keeps_its_pod_document_as_profile_and_nothing_foreign(space_server, tmp_path, monkeypatch):
    ttl = TTL + '\n<#space> schema:taxID "BE0123" ; <https://other.example/p> "x" .'
    url, g = await register(space_server, ttl, "text/turtle", tmp_path, monkeypatch, "/p")
    subject = URIRef("urn:mak:space/atelier-du-canal")
    assert (subject, URIRef("https://mapsofmaking.org/ns/mom#profileUrl"), URIRef(url)) in g
    assert (subject, URIRef("https://mapsofmaking.org/ns/mom#endpointUrl"), URIRef(url)) in g
    assert not any("taxID" in str(p) or "other.example" in str(p) for _, p, _ in g)
    assert not any("contactJson" in str(p) or "email" in str(p).lower() for _, p, _ in g)


@pytest.mark.asyncio
async def test_the_snapshot_keeps_the_source_as_written(space_server, tmp_path, monkeypatch):
    monkeypatch.setenv("SNAPSHOT_DB_PATH", str(tmp_path / "snap.db"))
    with FakeOxigraph() as ox:
        monkeypatch.setattr(main, "OXIGRAPH_ENDPOINT", ox.url)
        await main.register_url(main.UrlRequest(url=serve(space_server, TTL, "text/plain", "/t")), BackgroundTasks())
        snap = read_snapshot("atelier-du-canal")
        assert snap["media_type"] == "text/turtle" and snap["raw_text"] == TTL
        assert snap["payload"]["fields"]["schema:name"] == "Atelier du Canal"
        assert snap["payload"]["contact"]["email"] == "contact@atelierducanal.example"

        await main.register_url(main.UrlRequest(url=serve(space_server, JSON_TEXT, "text/plain", "/j")), BackgroundTasks())
        snap = read_snapshot("atelier-du-canal")
        assert snap["media_type"] == "application/json" and snap["raw_text"] is None
        assert snap["payload"]["space"] == "Atelier du Canal"


@pytest.mark.asyncio
async def test_refused_files_are_not_registered(space_server, tmp_path, monkeypatch):
    from fastapi import HTTPException
    monkeypatch.setenv("SNAPSHOT_DB_PATH", str(tmp_path / "snap.db"))
    with FakeOxigraph() as ox:
        monkeypatch.setattr(main, "OXIGRAPH_ENDPOINT", ox.url)
        with pytest.raises(HTTPException) as err:
            await main.register_url(main.UrlRequest(url=serve(space_server, "<html></html>", "text/html")), BackgroundTasks())
        assert err.value.status_code == 422 and "text/html" in json.dumps(err.value.detail)
        assert ox.updates == []
