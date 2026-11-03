"""Story 14.4 S3 (mom-home #13): one space as the map draws it, read from spaces.geojson."""
from __future__ import annotations

import json
import os

import pytest
from fastapi import HTTPException

import main


def _write(path, features):
    path.write_text(json.dumps({"type": "FeatureCollection", "features": features}))


def _feature(sid, lon, lat, name="Weld Done"):
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [lon, lat]},
        "properties": {"id": sid, "name": name, "city": "Marolles", "country": "Belgium", "address": "Rue de l'Étincelle 12"},
    }


@pytest.fixture
def geojson(tmp_path, monkeypatch):
    path = tmp_path / "spaces.geojson"
    monkeypatch.setattr(main, "GEOJSON_OUTPUT", str(path))
    main._pin_cache.update({"mtime": None, "by_id": {}})
    return path


@pytest.mark.asyncio
async def test_returns_the_pin_the_map_draws(geojson):
    _write(geojson, [_feature("weld-done", 4.3458, 50.8371)])
    pin = await main.get_space_pin("weld-done")
    assert pin == {"id": "weld-done", "name": "Weld Done", "lat": 50.8371, "lon": 4.3458,
                   "city": "Marolles", "country": "Belgium", "address": "Rue de l'Étincelle 12"}


@pytest.mark.asyncio
async def test_not_on_the_map_yet_is_404(geojson):
    _write(geojson, [_feature("other", 1, 2)])
    with pytest.raises(HTTPException) as e:
        await main.get_space_pin("weld-done")
    assert e.value.status_code == 404


@pytest.mark.asyncio
async def test_no_file_yet_is_404(geojson):
    with pytest.raises(HTTPException) as e:
        await main.get_space_pin("weld-done")
    assert e.value.status_code == 404


@pytest.mark.asyncio
async def test_rereads_when_the_map_is_rebuilt(geojson):
    _write(geojson, [_feature("other", 1, 2)])
    with pytest.raises(HTTPException):
        await main.get_space_pin("weld-done")
    _write(geojson, [_feature("weld-done", 4.3, 50.8)])
    st = geojson.stat()
    os.utime(geojson, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000))
    assert (await main.get_space_pin("weld-done"))["lat"] == 50.8


@pytest.mark.asyncio
async def test_refuses_an_id_that_isnt_a_slug(geojson):
    with pytest.raises(HTTPException) as e:
        await main.get_space_pin("../etc")
    assert e.value.status_code == 400
