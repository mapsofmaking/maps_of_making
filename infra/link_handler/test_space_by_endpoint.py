"""Story 14.4 S4 (mom-home #14): the map's id for a space file's address."""
from __future__ import annotations

import pytest
from fastapi import HTTPException

import main

FILE = "https://weld-done.pod.example/space.ttl"


@pytest.fixture
def lookup(monkeypatch):
    seen = []

    async def fake(endpoint, url):
        seen.append(url)
        return "urn:mak:space/weld-done" if url == FILE else None

    monkeypatch.setattr(main, "_find_graph_by_endpoint", fake)
    return seen


@pytest.mark.asyncio
async def test_returns_the_maps_id(lookup):
    assert await main.get_space_by_endpoint(FILE) == {"id": "weld-done"}


@pytest.mark.asyncio
async def test_unknown_address_is_404(lookup):
    with pytest.raises(HTTPException) as e:
        await main.get_space_by_endpoint("https://other.pod.example/space.ttl")
    assert e.value.status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", ["not a url", "ftp://x/y", "https://x/a> } ; DROP ALL ; <x", "javascript:alert(1)"])
async def test_refuses_what_cant_be_an_iri_before_any_query(lookup, bad):
    with pytest.raises(HTTPException) as e:
        await main.get_space_by_endpoint(bad)
    assert e.value.status_code == 400
    assert lookup == []


@pytest.mark.asyncio
async def test_the_shared_lookup_never_splices_an_unsafe_address(monkeypatch):
    called = []

    class Boom:
        def __init__(self, *a, **k):
            called.append(1)

    monkeypatch.setattr(main.httpx, "AsyncClient", Boom)
    assert await main._find_graph_by_endpoint("http://oxigraph", "https://x/a> } ; DROP ALL ; <x") is None
    assert called == []
