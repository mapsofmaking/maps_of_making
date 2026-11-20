"""read-url: a space or network file read and validated, written nowhere (#84).

Offline: the file is served by a local pytest-httpserver; no Oxigraph is running, so any write
would fail the test. The public-host check is off for 127.0.0.1 (conftest.py) except where
a test is marked host_check.
"""
from __future__ import annotations

import json
import socket
from pathlib import Path

import pytest
from fastapi import HTTPException
from pytest_httpserver import HTTPServer

import main
import source
from fakes import JSON_TEXT, NETWORK_JSON, NETWORK_TTL, TTL, serve
from read_record import json_unmapped

MOTHER_SAND = (Path(__file__).resolve().parents[2] / "data" / "canary" / "baseline.json").read_text()


@pytest.fixture
def space_server():
    server = HTTPServer(host="127.0.0.1", port=0)
    server.start()
    yield server
    server.clear()
    server.stop()


@pytest.fixture(autouse=True)
def fresh_limit(monkeypatch):
    monkeypatch.setattr(main, "_read_url_times", [])


async def read(space_server, body, content_type="application/json", path="/f"):
    return await main.read_url(main.UrlRequest(url=serve(space_server, body, content_type, path)))


@pytest.mark.asyncio
async def test_mother_sand_reads_with_its_networks_and_what_is_left_behind(space_server, monkeypatch):
    async def no_write(*a, **k):
        raise AssertionError("read-url wrote something")
    monkeypatch.setattr(main.httpx.AsyncClient, "post", no_write)
    out = await read(space_server, MOTHER_SAND)
    v, r = out["validation"], out["record"]
    assert v["schema_valid"] and v["coords_found"] and "_data" not in v and "_source" not in v
    assert r["name"] == "Mother Sand" and r["kind"] == "space"
    assert (r["lat"], r["lon"]) == (51.65, 1.7)
    assert r["memberOf"] == ["urn:mak:network/canary", "urn:mak:network/vulca"]
    assert r["sdgs"] == [9, 11, 12, 14, 17]
    assert r["address"] == "Maunsell Fort, North Sea" and r["timezone"] == "UTC+0"
    assert r["contact"] == {"email": "bernard@mothersand.example.org", "irc": "#mothersand", "twitter": "@mothersand"}
    assert r["opening_hours"].startswith("closed during low tide")
    assert {"ext_canary", "ext_fab", "state", "issue_report_channels"} <= set(r["unmapped"])
    assert "api" not in r["unmapped"] and "api_compatibility" not in r["unmapped"]


@pytest.mark.asyncio
async def test_maakbib_reads_as_a_network_with_its_area(space_server):
    r = (await read(space_server, NETWORK_JSON))["record"]
    assert r["kind"] == "network" and r["name"] == "Maakbib"
    assert r["areaServed"] == [{"code": "BE-VLG", "name": "Flanders"}]
    assert r["geolocationFidelity"] == "region" and r["country_code"] == "BE"
    assert r["contact"] == {"email": "info@decreatievestem.be"}
    assert r["unmapped"] == ["state"]


@pytest.mark.asyncio
async def test_turtle_and_json_networks_give_the_same_record(space_server):
    from_json = (await read(space_server, NETWORK_JSON, path="/j"))["record"]
    from_ttl = (await read(space_server, NETWORK_TTL, "text/turtle", "/t"))["record"]
    for key in ("name", "kind", "lat", "lon", "areaServed", "geolocationFidelity", "country_code", "url", "logo", "description"):
        assert from_ttl[key] == from_json[key], key


@pytest.mark.asyncio
async def test_a_pod_file_reads_too(space_server):
    out = await read(space_server, TTL, "text/turtle")
    assert out["validation"]["media_type"] == "text/turtle"
    assert out["record"]["name"] and out["record"]["kind"] == "space"


@pytest.mark.asyncio
async def test_turtle_names_what_it_does_not_read(space_server):
    ttl = """@prefix schema: <http://schema.org/> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
<#space> a schema:Place ; schema:name "zz Two Mails" ;
  schema:email "a@example.org", "b@example.org" ;
  schema:foundingDate "2020" ;
  rdfs:seeAlso <https://example.org/config.ttl#zz> ;
  schema:geo [ schema:latitude 50.8 ; schema:longitude 4.3 ] .
"""
    r = (await read(space_server, ttl, "text/turtle"))["record"]
    assert r["contact"] == {"email": "a@example.org"}
    assert r["unmapped"] == ["contact.email", "http://www.w3.org/2000/01/rdf-schema#seeAlso", "https://schema.org/foundingDate"]


def test_sdgs_from_ext_fab_carry_that_block_s_other_keys_as_left_behind():
    data = {"space": "x", "ext_fab": {"sdgs": [4], "space_type": "fablab"}}
    assert json_unmapped(data, {"mom:sdgs": [4]}) == ["ext_fab.space_type"]
    data = {"space": "x", "mom": {"sdgs": [4]}, "ext_fab": {"sdgs": [9]}}
    assert json_unmapped(data, {"mom:sdgs": [4]}) == ["ext_fab"]


def test_unknown_keys_inside_location_and_mom_are_named():
    data = {"space": "x", "location": {"lat": 1, "lon": 2, "ext_floor": 3}, "mom": {"kind": "space", "movedTo": "y"}}
    assert json_unmapped(data, {}) == ["location.ext_floor", "mom.movedTo"]


@pytest.mark.asyncio
async def test_a_page_that_is_not_a_space_file_has_no_record(space_server):
    out = await read(space_server, "<html><body>hi</body></html>", "text/html")
    assert out["record"] is None and out["validation"]["error"]


@pytest.mark.asyncio
async def test_an_unreachable_file_has_no_record(space_server):
    space_server.expect_request("/gone").respond_with_data("", status=404)
    out = await main.read_url(main.UrlRequest(url=space_server.url_for("/gone")))
    assert out["record"] is None and out["validation"]["status_code"] == 404


@pytest.mark.asyncio
async def test_read_url_is_capped_for_the_whole_service(space_server, monkeypatch):
    monkeypatch.setattr(main, "READ_URL_MAX", 2)
    await read(space_server, NETWORK_JSON)
    await read(space_server, NETWORK_JSON)
    with pytest.raises(HTTPException) as caught:
        await read(space_server, NETWORK_JSON)
    assert caught.value.status_code == 429 and caught.value.detail["retry_after_seconds"] >= 1


# ── The public-host check (validate, read and register all go through it) ──

@pytest.mark.host_check
@pytest.mark.asyncio
@pytest.mark.parametrize("url", ["http://127.0.0.1:8000/x", "http://[::1]/x", "http://10.0.0.1/x", "http://169.254.169.254/latest",
                                 "http://[::ffff:192.168.1.1]/x", "http://0.0.0.0/x", "http://localhost/x"])
async def test_a_host_inside_the_server_is_refused_before_any_request(url, monkeypatch):
    async def no_fetch(*a, **k):
        raise AssertionError("fetched")
    monkeypatch.setattr(main, "fetch_source", no_fetch)
    out = await main.read_url(main.UrlRequest(url=url))
    assert out["record"] is None
    assert "public internet" in out["validation"]["error"] and out["validation"]["reachable"] is False


@pytest.mark.host_check
@pytest.mark.asyncio
async def test_a_container_name_is_refused(monkeypatch):
    async def resolve(self, host, port, **kw):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("172.18.0.2", 0))]
    monkeypatch.setattr(type(__import__("asyncio").get_running_loop()), "getaddrinfo", resolve)
    assert "public internet" in await source.non_public_host("http://oxigraph:7878/query")


@pytest.mark.host_check
@pytest.mark.asyncio
async def test_a_name_with_one_private_address_among_public_ones_is_refused(monkeypatch):
    async def resolve(self, host, port, **kw):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.215.14", 0)), (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.1.2.3", 0))]
    monkeypatch.setattr(type(__import__("asyncio").get_running_loop()), "getaddrinfo", resolve)
    assert await source.non_public_host("https://example.org/x")


@pytest.mark.host_check
@pytest.mark.asyncio
async def test_a_public_host_is_let_through(monkeypatch):
    async def resolve(self, host, port, **kw):
        return [(socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("2606:4700::1111", 0, 0, 0))]
    monkeypatch.setattr(type(__import__("asyncio").get_running_loop()), "getaddrinfo", resolve)
    assert await source.non_public_host("https://example.org/x") is None
    assert await source.non_public_host("https://1.1.1.1/x") is None


@pytest.mark.host_check
@pytest.mark.asyncio
async def test_register_refuses_a_host_inside_the_server_too():
    with pytest.raises(HTTPException) as caught:
        await main.register_url(main.UrlRequest(url="http://127.0.0.1:7878/"), main.BackgroundTasks())
    assert caught.value.status_code == 422
    assert "public internet" in caught.value.detail["validation"]["error"]
