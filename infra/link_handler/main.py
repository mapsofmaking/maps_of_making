import difflib
import functools
import gettext
import json
import logging
import os
import re
import sys
import unicodedata
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional, List, Union

import httpx
import pycountry
import yaml
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from fastapi import BackgroundTasks, FastAPI, Header, HTTPException
from geopy.geocoders import Nominatim
from geopy.extra.rate_limiter import RateLimiter
from geopy.exc import GeocoderServiceError, GeocoderTimedOut, GeocoderUnavailable
from pydantic import BaseModel, Field, ConfigDict

import asyncio

# Ensure scripts/ (containing spaceapi_extract) is on the path.
# In Docker set SCRIPTS_DIR=/app/scripts via docker-compose env; locally resolved automatically.
_scripts_dir = os.environ.get("SCRIPTS_DIR") or str(Path(__file__).resolve().parents[2] / "scripts")
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)

from spaceapi_extract import escape_literal, extract_core, extract_mom, kind_of, triples_for
from spaceapi_extract.area import clean_area, clean_area_name, clean_areas
from spaceapi_extract.turtle import safe_iri

from pipeline import run_space_pipeline
from pipeline_helpers import get_config
from snapshot_store import mint_observed_at, write_snapshot, read_last_ok_observed_at, read_snapshot
from source import as_spaceapi, fetch_source, non_public_host, snapshot_parts
from read_record import read_record
from utils import MOM, SCHEMA, _ALLOWED_SCHEMES, _sparql_str, _sparql_iri, _slug
import bot_keys

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_manual_refresh_cooldowns: dict[str, datetime] = {}
COOLDOWN_SECONDS = 60

_last_heartbeat_completed: Optional[datetime] = None

OXIGRAPH_ENDPOINT = os.getenv("OXIGRAPH_ENDPOINT", "http://oxigraph:7878")
GEOJSON_OUTPUT = os.getenv("GEOJSON_OUTPUT", "/app/web_data/spaces.geojson")

_TOKEN_RE = re.compile(r'^[A-Za-z0-9_\-]{8,255}$')

_scheduler = AsyncIOScheduler()

# Geocode proxy — module-level geocoder + 1 req/s rate limiter
# Nominatim policy: max 1 req/s; descriptive user_agent required (see geopy docs)
_USER_AGENT = "MapsOfMaking-geocode/1.0 (+https://mapsofmaking.org; contact: nicolas.de.barquin@gmail.com)"
_geolocator = Nominatim(user_agent=_USER_AGENT)
_geocode = RateLimiter(_geolocator.geocode, min_delay_seconds=1, max_retries=1, swallow_exceptions=False)

async def _heartbeat_job():
    global _last_heartbeat_completed
    try:
        await run_heartbeat_tick(OXIGRAPH_ENDPOINT)
    except Exception as e:
        logger.exception("[heartbeat] tick failed: %s", e)
    _last_heartbeat_completed = datetime.now(timezone.utc)


async def _query_all_claimed_spaces(oxigraph_endpoint: str) -> list[dict]:
    """Return [{uid, endpoint_url, graph_uri, subject}, ...] for every space
    (canary + regular) that has mom:endpointUrl written.

    One SPARQL SELECT across all urn:mak:* named graphs. The seeded/unclaimed
    gate inside run_space_pipeline is still authoritative — this just prunes
    the work list early.
    """
    sparql = """PREFIX mom: <https://mapsofmaking.org/ns/mom#>
SELECT ?graph ?subject ?endpointUrl WHERE {
  GRAPH ?graph {
    ?subject mom:endpointUrl ?endpointUrl .
  }
  FILTER(STRSTARTS(STR(?graph), "urn:mak:"))
}"""
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            f"{oxigraph_endpoint}/query",
            content=sparql,
            headers={
                "Content-Type": "application/sparql-query",
                "Accept": "application/sparql-results+json",
            },
        )
        resp.raise_for_status()
    rows = resp.json().get("results", {}).get("bindings", [])
    out = []
    for b in rows:
        subject = b["subject"]["value"]
        graph_uri = b["graph"]["value"]
        endpoint_url = b["endpointUrl"]["value"]
        # The map's id for the subject (_id_of): mother-sands, <slug>, network_<slug>.
        uid = _id_of(subject)
        out.append({
            "uid": uid,
            "endpoint_url": endpoint_url,
            "graph_uri": graph_uri,
            "subject": subject,
        })
    return out


# The class each kind of registration is typed with (a network: 2026-11-19, docs/reference/space-file.md).
_KIND_TYPE = {"space": f"{MOM}Space", "network": f"{MOM}Network"}

# Where each kind lives (M1, 2026-11-19): a network is its own entity, graph and subject
# `urn:mak:network/<slug>`, the IRI its members already name with mom:memberOf.
_KIND_PREFIX = {"space": "urn:mak:space/", "network": "urn:mak:network/"}
# A network's id on the map, in the snapshot store and in /api/space/{id}: `network_<slug>`.
# A space's id is its slug, which never holds `_` (utils._slug), so the two never meet.
_NETWORK_ID_PREFIX = "network_"


def _id_of(uri: str) -> str:
    """The map's id for a space or network IRI: `<slug>` for urn:mak:space/<slug> (and the
    canary's last segment), `network_<slug>` for urn:mak:network/<slug>."""
    if uri.startswith(_KIND_PREFIX["network"]):
        return _NETWORK_ID_PREFIX + uri[len(_KIND_PREFIX["network"]):]
    return uri.rsplit("/", 1)[-1] if "/" in uri else uri


def _graph_of(space_id: str) -> tuple[str, str]:
    """(graph, subject) for a map id, the inverse of _id_of. The canary has its own graph."""
    if space_id == "mother-sands":
        return "urn:mak:canary", f"urn:mak:canary/{space_id}"
    if space_id.startswith(_NETWORK_ID_PREFIX):
        uri = _KIND_PREFIX["network"] + space_id[len(_NETWORK_ID_PREFIX):]
    else:
        uri = _KIND_PREFIX["space"] + space_id
    return uri, uri


async def _find_seeded_graph_by_name(oxigraph_endpoint: str, name: str, kind: str = "space") -> Optional[str]:
    """Find a bundle-seeded graph (mom:source starts with 'scraped-') matching the
    given space name (case-insensitive) and of the same kind. Returns the graph URI or None.

    Same kind only: a network never claims a seeded space that happens to share its name.

    Used by register_url to claim a Path B record in place when a coordinator
    self-registers a SpaceAPI URL whose name matches a previously-seeded bundle
    entry. Same URI → grey pin upgrades to live with no orphan record.
    """
    # Escape the name for safe literal inclusion.
    safe = name.replace("\\", "\\\\").replace('"', '\\"')
    sparql = f"""PREFIX mom: <https://mapsofmaking.org/ns/mom#>
PREFIX schema: <https://schema.org/>
SELECT ?graph WHERE {{
  GRAPH ?graph {{
    ?s a <{_KIND_TYPE[kind]}> ;
       schema:name ?n ;
       mom:source ?src .
    FILTER(LCASE(STR(?n)) = LCASE("{safe}"))
    FILTER(STRSTARTS(STR(?src), "scraped-"))
  }}
}} LIMIT 1"""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{oxigraph_endpoint}/query",
                content=sparql,
                headers={
                    "Content-Type": "application/sparql-query",
                    "Accept": "application/sparql-results+json",
                },
            )
            resp.raise_for_status()
    except httpx.HTTPError as e:
        logger.warning("[register] claim-merge lookup failed for %r: %s", name, e)
        return None
    rows = resp.json().get("results", {}).get("bindings", [])
    return rows[0]["graph"]["value"] if rows else None


async def _find_graph_by_endpoint(oxigraph_endpoint: str, endpoint_url: str) -> Optional[str]:
    """Return the graph URI of any existing space that already has this endpointUrl, or None.

    Prevents double-registration when a coordinator registers an endpoint that is
    already stored under a different slug (e.g. a bundle-seeded slug with a city suffix
    was claimed before the original name-only slug was confirmed, or vice versa).
    """
    # Spliced into SPARQL as <...>: an address that could end the IRI is never looked up.
    safe_url = safe_iri(endpoint_url.strip())
    if safe_url is None:
        return None
    sparql = f"""PREFIX mom: <https://mapsofmaking.org/ns/mom#>
SELECT ?graph WHERE {{
  GRAPH ?graph {{
    ?s mom:endpointUrl <{safe_url}> .
  }}
}} LIMIT 1"""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{oxigraph_endpoint}/query",
                content=sparql,
                headers={
                    "Content-Type": "application/sparql-query",
                    "Accept": "application/sparql-results+json",
                },
            )
            resp.raise_for_status()
    except httpx.HTTPError as e:
        logger.warning("[register] endpoint-dedup lookup failed for %r: %s", endpoint_url, e)
        return None
    rows = resp.json().get("results", {}).get("bindings", [])
    return rows[0]["graph"]["value"] if rows else None


async def run_heartbeat_tick(oxigraph_endpoint: str) -> int:
    """Unified single tick: fetch every claimed space concurrently, then rematerialize once.

    Returns the number of spaces dispatched (for logs / smoke tests).
    """
    spaces = await _query_all_claimed_spaces(oxigraph_endpoint)
    if not spaces:
        logger.info("[heartbeat] no claimed spaces — skipping tick")
        await _rematerialize_geojson()
        return 0

    cfg = get_config()
    concurrency = int(cfg.get("bandwidth", {}).get("heartbeat_concurrency", 8))
    sem = asyncio.Semaphore(max(1, concurrency))

    async def _guarded(s: dict):
        async with sem:
            try:
                return await run_space_pipeline(
                    uid=s["uid"],
                    endpoint_url=s["endpoint_url"],
                    graph_uri=s["graph_uri"],
                    subject=s["subject"],
                    oxigraph_endpoint=oxigraph_endpoint,
                )
            except Exception as e:
                logger.exception("[heartbeat] space %s failed: %s", s["uid"], e)
                return None

    logger.info("[heartbeat] dispatching %d spaces (concurrency=%d)", len(spaces), concurrency)
    await asyncio.gather(*(_guarded(s) for s in spaces))
    await _rematerialize_geojson()
    return len(spaces)


@asynccontextmanager
async def lifespan(app: FastAPI):
    cfg = get_config()
    interval = cfg.get("bandwidth", {}).get("heartbeat_interval_seconds", 600)
    try:
        _scheduler.add_job(
            _heartbeat_job,
            IntervalTrigger(seconds=interval),
            id="heartbeat",
            replace_existing=True,
        )
        _scheduler.start()
        logger.info("APScheduler started — heartbeat every %ds", interval)
    except Exception as e:
        logger.error("APScheduler failed to start: %s", e)
    yield
    try:
        _scheduler.shutdown(wait=False)
    except Exception:
        pass


app = FastAPI(title="Maps of Making Link Handler", lifespan=lifespan)


_SPARQL_SELECT = """PREFIX mom: <https://mapsofmaking.org/ns/mom#>
PREFIX schema: <https://schema.org/>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>

SELECT ?spaceUri ?type ?name ?latitude ?longitude
       ?geolocationFidelity ?geolocationNote
       ?street ?postcode ?city ?country ?address ?countryCode ?timeZone
       ?website ?profileUrl ?endpointUrl ?openNow ?lastOpenChange
       ?source ?openingHours ?description ?logo ?contactJson ?updatedAt
       ?subset ?nextUnlock
       (GROUP_CONCAT(DISTINCT ?specialty; separator="|") AS ?specialties)
       (GROUP_CONCAT(DISTINCT STR(?memberOf); separator="|") AS ?networkMemberships)
       (GROUP_CONCAT(DISTINCT ?area; separator="\u001e") AS ?areasServed)
WHERE {
  {
    GRAPH ?spaceGraph {
      # A space, or a network (2026-11-19): ?type tells them apart.
      ?spaceUri a ?type ;
        schema:name ?name ;
        schema:geo [
          schema:latitude ?latitude ;
          schema:longitude ?longitude
        ] .
      OPTIONAL { ?spaceUri mom:geolocationFidelity ?geolocationFidelity }
      OPTIONAL { ?spaceUri mom:geolocationNote ?geolocationNote }
      OPTIONAL { ?spaceUri schema:streetAddress ?street }
      OPTIONAL { ?spaceUri schema:postalCode ?postcode }
      OPTIONAL { ?spaceUri schema:addressLocality ?city }
      OPTIONAL { ?spaceUri schema:addressCountry ?country }
      OPTIONAL { ?spaceUri mom:address ?address }
      OPTIONAL { ?spaceUri mom:countryCode ?countryCode }
      OPTIONAL { ?spaceUri mom:timeZone ?timeZone }
      OPTIONAL { ?spaceUri schema:url ?website }
      OPTIONAL { ?spaceUri mom:profileUrl ?profileUrl }
      OPTIONAL { ?spaceUri mom:endpointUrl ?endpointUrl }
      OPTIONAL { ?spaceUri schema:knowsAbout ?specialty }
      OPTIONAL { ?spaceUri mom:memberOf ?memberOf }
      OPTIONAL { ?spaceUri mom:source ?source }
      OPTIONAL { ?spaceUri schema:openingHours ?openingHours }
      OPTIONAL { ?spaceUri schema:description ?description }
      OPTIONAL { ?spaceUri schema:logo ?logo }
      OPTIONAL { ?spaceUri schema:contactJson ?contactJson }
      OPTIONAL { ?spaceUri mom:updatedAt ?updatedAt }
      OPTIONAL { ?spaceUri mom:openNow ?openNow }
      OPTIONAL { ?spaceUri mom:lastOpenChange ?lastOpenChange }
      OPTIONAL { ?spaceUri mom:subset ?subset }
      OPTIONAL { ?spaceUri mom:nextUnlock ?nextUnlock }
      # An area served (2026-11-19): a node with its code and name, or a bare code (the first shape).
      # "code<US>name", the areas joined by <RS>: control characters never in a cleaned name.
      OPTIONAL {
        ?spaceUri schema:areaServed ?areaNode .
        OPTIONAL { ?areaNode schema:identifier ?areaCode }
        OPTIONAL { ?areaNode schema:name ?areaName }
        BIND (CONCAT(IF(isLiteral(?areaNode), STR(?areaNode), STR(?areaCode)), "\u001f", COALESCE(STR(?areaName), "")) AS ?area)
      }
      FILTER (?type IN (mom:Space, mom:Network))
    }
    # Spaces, and networks in their own graphs (M1, 2026-11-19); a network registered before
    # M1 under urn:mak:space/ still shows until it is registered again.
    FILTER (STRSTARTS(STR(?spaceGraph), "urn:mak:space/") || STRSTARTS(STR(?spaceGraph), "urn:mak:network/"))
  }
  UNION
  {
    # Canary space (diagnostic instrument — isolated named graph, not on urn:mak:space/).
    GRAPH <urn:mak:canary> {
      ?spaceUri a mom:Space ;
        a ?type ;
        schema:name ?name ;
        schema:geo [
          schema:latitude ?latitude ;
          schema:longitude ?longitude
        ] .
      OPTIONAL { ?spaceUri mom:address ?address }
      OPTIONAL { ?spaceUri mom:countryCode ?countryCode }
      OPTIONAL { ?spaceUri mom:timeZone ?timeZone }
      OPTIONAL { ?spaceUri schema:url ?website }
      OPTIONAL { ?spaceUri schema:logo ?logo }
      OPTIONAL { ?spaceUri mom:endpointUrl ?endpointUrl }
      OPTIONAL { ?spaceUri schema:openingHours ?openingHours }
      OPTIONAL { ?spaceUri schema:description ?description }
      OPTIONAL { ?spaceUri mom:updatedAt ?updatedAt }
      OPTIONAL { ?spaceUri mom:openNow ?openNow }
      OPTIONAL { ?spaceUri mom:lastOpenChange ?lastOpenChange }
      OPTIONAL { ?spaceUri mom:source ?source }
      OPTIONAL { ?spaceUri schema:contactJson ?contactJson }
      OPTIONAL { ?spaceUri mom:memberOf ?memberOf }
      FILTER (?type = mom:Space)
    }
  }
}
GROUP BY ?spaceUri ?type ?name ?latitude ?longitude
         ?geolocationFidelity ?geolocationNote
         ?street ?postcode ?city ?country ?address ?countryCode ?timeZone
         ?website ?profileUrl ?endpointUrl ?openNow ?lastOpenChange
         ?source ?openingHours ?description ?logo ?contactJson ?updatedAt
         ?subset ?nextUnlock
ORDER BY ?spaceUri"""

class UrlRequest(BaseModel):
    url: str
    space_id: Optional[str] = None


from schema import SpaceAPIGeo, SpaceAPILocation, SpaceAPISchema  # noqa: E402  (placed here to match original class location)


def _extract_name(data: dict) -> Optional[str]:
    return data.get("schema:name") or data.get("name")


def _extract_coords(data: dict) -> tuple[Optional[float], Optional[float]]:
    # Normalise schema:geo — may be a dict or a single-element list
    raw_geo = data.get("schema:geo")
    if isinstance(raw_geo, list):
        raw_geo = raw_geo[0] if raw_geo else {}
    geo = raw_geo if isinstance(raw_geo, dict) else {}

    # Use `is not None` throughout — lat/lon of 0 is valid (equator / prime meridian)
    lat = geo.get("schema:latitude") if geo.get("schema:latitude") is not None else geo.get("latitude")
    lon = geo.get("schema:longitude") if geo.get("schema:longitude") is not None else geo.get("longitude")
    if lat is not None and lon is not None:
        try:
            return float(lat), float(lon)
        except (TypeError, ValueError):
            pass

    # Flat-key fallback (less common encodings)
    lat = data.get("schema:latitude")
    lon = data.get("schema:longitude")
    if lat is None and lon is None:
        plain_geo = data.get("geo")
        if isinstance(plain_geo, dict):
            lat = plain_geo.get("lat")
            lon = plain_geo.get("lon")
    if lat is not None and lon is not None:
        try:
            return float(lat), float(lon)
        except (TypeError, ValueError):
            pass
    return None, None


def classify_subset(schema: SpaceAPISchema) -> dict:
    """Classify the subset level reached by the endpoint data.

    api_compatibility is intentionally excluded from tier checks — it is a SpaceAPI
    interop signal with no MoM-specific feature unlock. Logo and contact are sufficient
    for the spaceapi:compatible tier on MoM.
    """
    has_required = bool(schema.resolved_name and schema.resolved_lat is not None and schema.resolved_lon is not None)
    has_card = has_required and bool(schema.resolved_url and schema.resolved_opening_hours)
    has_spaceapi = has_card and bool(schema.logo and schema.contact)

    if has_spaceapi:
        return {
            "subset": "spaceapi:compatible",
            "subset_score": 3,
            "missing_card_fields": [],
            "unlock_message": "Full SpaceAPI compatibility — interoperable with mapall.space and other SpaceAPI maps.",
            "next_subset": None,
            "next_unlock": None,
        }
    elif has_card:
        missing = []
        if not schema.logo:
            missing.append("logo")
        if not schema.contact:
            missing.append("contact")
        if not schema.logo:
            next_unlock = "Add logo to unlock SpaceAPI compatibility"
        elif not schema.contact:
            next_unlock = "Add contact to unlock SpaceAPI compatibility"
        else:
            next_unlock = None
        return {
            "subset": "mom:card",
            "subset_score": 2,
            "missing_card_fields": missing,
            "unlock_message": "Full detail card unlocked.",
            "next_subset": "spaceapi:compatible",
            "next_unlock": next_unlock,
        }
    elif has_required:
        missing = []
        if not schema.resolved_url:
            missing.append("schema:url")
        if not schema.resolved_opening_hours:
            missing.append("schema:openingHours")
        if not schema.resolved_url:
            next_unlock = "Add schema:url (website) to unlock the full detail card"
        elif not schema.resolved_opening_hours:
            next_unlock = "Add schema:openingHours to unlock the full detail card"
        else:
            next_unlock = None
        return {
            "subset": "mom:required",
            "subset_score": 1,
            "missing_card_fields": missing,
            "unlock_message": "Pin on map unlocked.",
            "next_subset": "mom:card",
            "next_unlock": next_unlock,
        }
    else:
        return {
            "subset": "none",
            "subset_score": 0,
            "missing_card_fields": [],
            "unlock_message": None,
            "next_subset": None,
            "next_unlock": None,
        }


# Checked before every fetch of a URL someone gave (validate, read, register); tests serve from
# 127.0.0.1 and replace it (conftest.py).
_host_error = non_public_host


_EMPTY_RESULT = {
    "reachable": False,
    "status_code": None,
    "schema_valid": False,
    "name_found": None,
    "coords_found": False,
    "lat": None,
    "lon": None,
}


async def _fetch_and_validate(url: str) -> dict:
    """Fetch URL and return validation result dict."""
    from urllib.parse import urlparse
    if urlparse(url).scheme not in _ALLOWED_SCHEMES:
        return {**_EMPTY_RESULT, "error": f"URL scheme not allowed; use http or https"}
    refused = await _host_error(url)
    if refused:
        return {**_EMPTY_RESULT, "error": refused}

    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=False) as client:
            fetched = await fetch_source(client, url)
    except (httpx.ConnectError, httpx.TimeoutException) as e:
        return {**_EMPTY_RESULT, "error": str(e)}
    except httpx.HTTPError as e:
        return {**_EMPTY_RESULT, "error": str(e)}

    if fetched.status_code != 200:
        return {
            **_EMPTY_RESULT,
            "status_code": fetched.status_code,
            "error": f"HTTP {fetched.status_code}",
        }

    source = fetched.source
    if not source.ok:
        # AC4 (14.7): a page that is neither JSON nor Turtle is refused with the media type it really was.
        error = "Response is not valid JSON" if source.kind == "invalid_json" else source.error
        return {
            "reachable": True,
            "status_code": fetched.status_code,
            "schema_valid": False,
            "media_type": source.sent,
            "error": error,
        }

    # Turtle is validated through the same model, in SpaceAPI's shape, so both formats
    # answer name / coordinates / subset alike. The graph is written from the Turtle's
    # own fields (_build_sparql_update), never from this dict.
    data = as_spaceapi(source.turtle) if source.kind == "turtle" else source.data

    # Validate through Pydantic schema
    try:
        schema = SpaceAPISchema.model_validate(data)
    except Exception as e:
        logger.warning("Pydantic validation failed: %s", e)
        schema = SpaceAPISchema()

    name = schema.resolved_name
    lat = schema.resolved_lat
    lon = schema.resolved_lon
    # A network (mom:Network) or a space: what the file says it is (2026-11-19). The subset ladder
    # (pin → card → SpaceAPI) and its "add openingHours" hint are a space's (M1): none for a network.
    kind = source.turtle.kind if source.kind == "turtle" else kind_of(data)
    subset_info = classify_subset(schema) if kind != "network" else {
        "subset": None, "subset_score": None, "missing_card_fields": [], "unlock_message": None,
        "next_subset": None, "next_unlock": None,
    }

    result = {
        "reachable": True,
        "status_code": fetched.status_code,
        "schema_valid": bool(name),
        "name_found": name,
        "coords_found": lat is not None and lon is not None,
        "lat": lat,
        "lon": lon,
        "kind": kind,
        "subset": subset_info["subset"],
        "subset_score": subset_info["subset_score"],
        "missing_card_fields": subset_info["missing_card_fields"],
        "unlock_message": subset_info["unlock_message"],
        "next_subset": subset_info["next_subset"],
        "next_unlock": subset_info["next_unlock"],
        "media_type": source.media_type,
        "_data": data,  # internal — stripped before response
        "_source": source,  # internal — stripped before response
    }
    if not name:
        result["error"] = "Name not found — expected 'space' (SpaceAPI v13–15) or 'schema:name' / 'name' (JSON-LD, Turtle)"
    elif lat is None or lon is None:
        result["coords_error"] = "Coordinates not found — expected location.lat/lon (SpaceAPI), schema:geo (JSON-LD or Turtle)"
    return result


def _build_sparql_update(graph_uri: str, space_uri: str, name: str, lat: float, lon: float,
                          endpoint_url: str, data: dict,
                          subset: str = "", next_unlock: Optional[str] = None,
                          turtle_fields: Optional[dict] = None, profile_url: Optional[str] = None,
                          kind: str = "space") -> str:
    # Registration envelope — identity + metadata (not extractable from payload)
    # A network is typed mom:Network, schema:Organization (2026-11-19); a space keeps mom:Space alone.
    types = [f"<{space_uri}> a <{MOM}Network> .", f"<{space_uri}> a <{SCHEMA}Organization> ."] if kind == "network" \
        else [f"<{space_uri}> a <{MOM}Space> ."]
    envelope = [
        *types,
        f"<{space_uri}> <{SCHEMA}name> {escape_literal(name)} .",
        f"<{space_uri}> <{SCHEMA}geo> [ <{SCHEMA}latitude> {lat} ; <{SCHEMA}longitude> {lon} ] .",
        f"<{space_uri}> <{MOM}endpointUrl> <{endpoint_url}> .",
        f'<{space_uri}> <{MOM}source> "self-registered" .',
    ]
    if subset:
        envelope.append(f"<{space_uri}> <{MOM}subset> {escape_literal(subset)} .")
    if next_unlock:
        envelope.append(f"<{space_uri}> <{MOM}nextUnlock> {escape_literal(next_unlock)} .")

    # Payload fields — skip name/geo (already in envelope)
    _ENVELOPE_SKIP = {"schema:name", "schema:geo"}
    if turtle_fields is not None:
        # Turtle (Story 14.7): the fields read from the file itself, not through the SpaceAPI
        # extractor; same shape, so the same triples. The pod document is the profile.
        payload_triples = triples_for(space_uri, {k: v for k, v in turtle_fields.items() if k not in _ENVELOPE_SKIP})
        if profile_url:
            payload_triples += triples_for(space_uri, {"mom:profileUrl": profile_url})
    else:
        core_fields = {k: v for k, v in extract_core(data).items() if k not in _ENVELOPE_SKIP}
        mom_fields = extract_mom(data)
        payload_triples = triples_for(space_uri, core_fields) + triples_for(space_uri, mom_fields)

    all_triples = ["  " + t for t in envelope] + ["  " + t for t in payload_triples]
    triples_str = "\n".join(all_triples)
    return f"""DROP SILENT GRAPH <{graph_uri}> ;
INSERT DATA {{
  GRAPH <{graph_uri}> {{
{triples_str}
  }}
}}"""


def _areas_served(value: str) -> list[dict[str, str]]:
    """The map query's areas ("code<US>name" joined by <RS>) as [{code, name}], cleaned as the readers clean them."""
    pairs = (part.split("\x1f", 1) for part in value.split("\x1e") if part)
    return clean_areas({"code": p[0], "name": p[1] if len(p) > 1 else ""} for p in pairs)


def _parse_contact_json(raw: Optional[str]) -> Optional[dict]:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None


def _binding_to_feature(b: dict) -> Optional[dict]:
    space_uri = b.get("spaceUri", {}).get("value", "")
    space_id = _id_of(space_uri)
    name = b.get("name", {}).get("value", "")
    lat_raw = b.get("latitude", {}).get("value")
    lon_raw = b.get("longitude", {}).get("value")
    if lat_raw is None or lon_raw is None:
        return None
    try:
        lat, lon = float(lat_raw), float(lon_raw)
    except (TypeError, ValueError):
        return None

    raw_specialties = b.get("specialties", {}).get("value", "")
    specialties = [s for s in raw_specialties.split("|") if s] if raw_specialties else []
    open_now_raw = b.get("openNow", {}).get("value")
    # None preserved (not coerced to False) so the browser distinguishes
    # "operator declared closed" (False) from "operator opted out / no state field" (None → opt-out).
    open_now = open_now_raw.lower() == "true" if open_now_raw is not None else None
    street = b.get("street", {}).get("value", "")
    postcode = b.get("postcode", {}).get("value", "")
    city = b.get("city", {}).get("value", "")
    raw_address = b.get("address", {}).get("value", "")
    if raw_address:
        address = raw_address
    else:
        address_parts = [p for p in [street, f"{postcode} {city}".strip()] if p]
        address = ", ".join(address_parts)

    updated_at = b.get("updatedAt", {}).get("value")
    last_open_change = b.get("lastOpenChange", {}).get("value")

    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [lon, lat]},
        "properties": {
            "id": space_id,
            "uri": space_uri,
            # "space" or "network" (2026-11-19). A network has no address: it serves areas (ISO 3166 codes).
            "kind": "network" if b.get("type", {}).get("value") == _KIND_TYPE["network"] else "space",
            "area_served": _areas_served(b.get("areasServed", {}).get("value", "")),
            "name": name,
            "geolocationFidelity": b.get("geolocationFidelity", {}).get("value", ""),
            "geolocationNote": b.get("geolocationNote", {}).get("value", ""),
            "address": address,
            "city": city,
            "country": b.get("country", {}).get("value", ""),
            "country_code": b.get("countryCode", {}).get("value", ""),
            "timezone": b.get("timeZone", {}).get("value", ""),
            "website": b.get("website", {}).get("value", ""),
            "endpoint_url": b.get("endpointUrl", {}).get("value") or b.get("profileUrl", {}).get("value", ""),
            "specialties": specialties,
            "open_now": open_now,
            "last_open_change": last_open_change,
            "source": b.get("source", {}).get("value"),
            "opening_hours": b.get("openingHours", {}).get("value", ""),
            "description": b.get("description", {}).get("value", ""),
            "logo": b.get("logo", {}).get("value", ""),
            "contact": _parse_contact_json(b.get("contactJson", {}).get("value")),
            "subset": b.get("subset", {}).get("value", ""),
            "next_unlock": b.get("nextUnlock", {}).get("value", ""),
            "founded": "",
            "capacity": 0,
            "network_memberships": [m for m in b.get("networkMemberships", {}).get("value", "").split("|") if m],
            "open_for_hosting": False,
            # Three freshness tokens (Axis A, B, C)
            "observed_at": None,  # Filled from SQLite by _rematerialize_geojson
            "updated_at": updated_at,  # From Oxigraph mom:updatedAt; may be null for pre-3.8b spaces
            "last_fetch_status": None,  # Filled from SQLite by _rematerialize_geojson
            "last_fetch_error": None,   # Human-readable failure reason when last_fetch_status='unreachable'
        },
    }


def _link_networks(features: list[dict]) -> list[dict]:
    """Each network gets `members`: the ids of the spaces that name it with mom:memberOf (M1, 2026-11-19).

    A member names a network by its IRI (`urn:mak:network/<slug>`, as seeding writes it), or by the
    address of the network's own file (its endpoint or pod profile, with or without a `#fragment`).
    The second is rewritten to the first in the member's `network_memberships`, so one network is
    one filter chip and one `networks=` embed parameter, whichever way its members name it.
    """
    def bare(iri: str) -> str:
        return iri.split("#", 1)[0]

    networks = [f["properties"] for f in features if f["properties"].get("kind") == "network"]
    by_address = {bare(n["endpoint_url"]): n["uri"] for n in networks if n.get("endpoint_url")}
    members: dict[str, list[str]] = {n["uri"]: [] for n in networks}
    for f in features:
        props = f["properties"]
        named = (by_address.get(bare(m), m) for m in props.get("network_memberships") or [])
        props["network_memberships"] = list(dict.fromkeys(named))
        if props.get("kind") == "network":
            continue  # a network in a network is not one of its member spaces
        for uri in props["network_memberships"]:
            if uri in members:
                members[uri].append(props["id"])
    for n in networks:
        n["members"] = members[n["uri"]]
    return features


def _load_thresholds_from_config() -> dict:
    config_path = Path(__file__).parent / "config.yaml"
    with open(config_path, "r") as f:
        cfg = yaml.safe_load(f) or {}
    endpoint_health = cfg.get("endpoint_health") or {}
    operational_state = cfg.get("operational_state") or {}
    if not endpoint_health or not operational_state:
        raise RuntimeError(
            f"THRESHOLDS_MISSING: config.yaml missing endpoint_health/operational_state blocks "
            f"(endpoint_health={endpoint_health!r}, operational_state={operational_state!r}) — "
            f"materializer cannot ship a GeoJSON the browser can compute against"
        )
    return {"endpoint_health": endpoint_health, "operational_state": operational_state}


# Serializes whole-corpus rebuilds. Registration moved this off the request path into
# a BackgroundTask, which removed the de-facto serialization a single in-flight request
# provided: two registrations, or a registration racing the scheduler's heartbeat, now
# overlap freely. The temp file is per-run so a second writer cannot truncate the file
# the first is about to publish; the lock keeps N concurrent whole-corpus passes from
# piling up on Oxigraph and the snapshot store.
_rematerialize_lock = asyncio.Lock()


async def _rematerialize_geojson() -> None:
    async with _rematerialize_lock:
        await _rematerialize_geojson_locked()


async def _rematerialize_geojson_locked() -> None:
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{OXIGRAPH_ENDPOINT}/query",
            content=_SPARQL_SELECT,
            headers={
                "Content-Type": "application/sparql-query",
                "Accept": "application/sparql-results+json",
            },
        )
        resp.raise_for_status()
        bindings = resp.json().get("results", {}).get("bindings", [])

    features = [_binding_to_feature(b) for b in bindings]
    features = _link_networks([f for f in features if f is not None])

    # SQLite join: fill in observed_at and last_fetch_status for each feature
    for feature in features:
        space_id = feature["properties"]["id"]
        snapshot = read_snapshot(space_id)
        if snapshot:
            # Story 3.10 Axis A: always carry observed_at, even when unreachable —
            # mark_unreachable preserves it intentionally so the card can show the
            # last-good snapshot timestamp ("fetched X ago" growing while broken).
            feature["properties"]["observed_at"] = snapshot["observed_at"]
            feature["properties"]["last_fetch_status"] = snapshot["fetch_status"]
            feature["properties"]["last_fetch_error"] = snapshot.get("fetch_error")

            # Story 3.10 B1: canary self-describes its demo mode via ext_canary.thresholdMode
            # in its own payload. When true, attach seconds-scale thresholds_override
            # so the aging→zombie→dead bucket walk is observable in ~minutes against
            # real mom:updatedAt. Source of truth lives in the canary endpoint itself.
            payload = snapshot.get("payload") or {}
            ext_canary = payload.get("ext_canary") or {}
            if ext_canary.get("thresholdMode") is True:
                feature["properties"]["thresholds_override"] = {
                    "operational_state": {
                        # fractional days = seconds (1/86400 ≈ 1 second)
                        "aging_days_threshold": 30 / 86400,
                        "zombie_days_threshold": 60 / 86400,
                        "dead_days_threshold": 120 / 86400,
                    }
                }

        # Check for missing tokens (fail-loud contract for materialization)
        has_observed = feature["properties"].get("observed_at") is not None
        has_updated = feature["properties"].get("updated_at") is not None
        has_lastchange = feature["properties"].get("last_open_change") is not None

        if not has_observed and not has_updated and not has_lastchange:
            logger.warning(
                "THREE_TOKENS_MISSING: space=%s — zero freshness tokens (data integrity)",
                feature["properties"]["uri"]
            )

    # Load thresholds and generate timestamp
    thresholds = _load_thresholds_from_config()
    generated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    geojson = {
        "type": "FeatureCollection",
        "generated_at": generated_at,
        "thresholds": thresholds,
        "features": features,
    }

    out_path = Path(GEOJSON_OUTPUT)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    # Per-run temp name: replace() is atomic, but a shared temp path is not — a second
    # writer truncating it mid-flight would publish a torn file to the map.
    tmp_path = out_path.with_suffix(f".{uuid.uuid4().hex}.tmp")
    try:
        tmp_path.write_text(json.dumps(geojson, indent=2))
        tmp_path.replace(out_path)
    finally:
        tmp_path.unlink(missing_ok=True)
    logger.info("rematerialized %d spaces → %s", len(features), out_path)


_SPACE_ID_RE = re.compile(r'^[a-zA-Z0-9_-]{1,64}$')


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/api/heartbeat/run")
async def heartbeat_run():
    """Trigger an immediate full heartbeat cycle. Used by make publish after deploy."""
    global _last_heartbeat_completed
    dispatched = await run_heartbeat_tick(OXIGRAPH_ENDPOINT)
    _last_heartbeat_completed = datetime.now(timezone.utc)
    return {"status": "ok", "dispatched": dispatched}


@app.post("/api/rematerialize")
async def rematerialize_endpoint():
    """Rebuild web/data/spaces.geojson from current Oxigraph + SQLite state.

    Story 3.10: used by `make cb-aging/zombie/dead/closed` after back-dating
    mom:updatedAt — those scenarios don't need a fresh fetch, only a re-emit.
    """
    await _rematerialize_geojson()
    return {"status": "ok"}


@app.get("/api/heartbeat/last-run")
async def heartbeat_last_run():
    """Return timestamp of the last completed heartbeat cycle (UTC ISO-8601).

    Used by the browser to detect when new data is available and soft-refresh the map
    without a full page reload. Returns null on first boot before any cycle completes.
    """
    return {"last_run": _last_heartbeat_completed.isoformat() if _last_heartbeat_completed else None}


@app.post("/api/heartbeat-space/{space_id}")
async def heartbeat_space(space_id: str):
    if not _SPACE_ID_RE.match(space_id):
        raise HTTPException(status_code=400, detail={"error": "invalid_space_id"})

    now = datetime.now(timezone.utc)
    last = _manual_refresh_cooldowns.get(space_id)
    if last and (now - last) < timedelta(seconds=COOLDOWN_SECONDS):
        retry_after = COOLDOWN_SECONDS - int((now - last).total_seconds())
        raise HTTPException(
            status_code=429,
            detail={"error": "rate_limited", "retry_after_seconds": retry_after},
        )

    # Canary lives in urn:mak:canary, spaces in urn:mak:space/<slug>, networks in
    # urn:mak:network/<slug> (id network_<slug>) — same shape as the heartbeat driver.
    graph_uri, subject = _graph_of(space_id)

    sparql = f"""PREFIX mom: <https://mapsofmaking.org/ns/mom#>
SELECT ?endpointUrl WHERE {{
  GRAPH <{graph_uri}> {{
    <{subject}> mom:endpointUrl ?endpointUrl .
  }}
}}"""
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            f"{OXIGRAPH_ENDPOINT}/query",
            content=sparql,
            headers={
                "Content-Type": "application/sparql-query",
                "Accept": "application/sparql-results+json",
            },
        )
        resp.raise_for_status()
    bindings = resp.json().get("results", {}).get("bindings", [])
    if not bindings:
        raise HTTPException(
            status_code=404,
            detail={"error": "no_endpoint", "message": "Space has no registered endpoint URL"},
        )

    endpoint_url = bindings[0]["endpointUrl"]["value"]
    _manual_refresh_cooldowns[space_id] = now

    observed_at = await run_space_pipeline(
        uid=space_id,
        endpoint_url=endpoint_url,
        graph_uri=graph_uri,
        subject=subject,
        oxigraph_endpoint=OXIGRAPH_ENDPOINT,
    )
    await _rematerialize_geojson()
    outcome = "ok" if observed_at else "unreachable_or_unclaimed"
    return {"status": "ok", "space_id": space_id, "outcome": outcome}


class DeployKeyRequest(BaseModel):
    room_id: Optional[str] = None


@app.post("/api/bot/deploy-key/{space_id}")
async def bot_deploy_key(
    space_id: str,
    req: Optional[DeployKeyRequest] = None,
    room_id: Optional[str] = None,
    x_bot_secret: Optional[str] = Header(None),
):
    """Generate (or reuse) a deploy key for a registered space, and — if a
    Matrix room_id is supplied — write the mom:botRoom mapping. The bot itself
    never writes to Oxigraph (NFR-S7); link_handler, the sole writer (ADR-015),
    does this write on the bot's behalf. See Story 6.1 Dev Notes "Room→space
    mapping: who writes it".

    `/api/` is proxied to the public internet (infra/nginx/conf.d/app.conf) —
    this endpoint is meant to be called only by mak-agent-bot, so it requires
    the shared X-Bot-Secret header (same value as BOT_KEY_SECRET) to prevent
    an internet caller from hijacking a space's mom:botRoom mapping (Story 6.1
    code review finding)."""
    if x_bot_secret != os.environ.get("BOT_KEY_SECRET"):
        raise HTTPException(status_code=401, detail={"error": "unauthorized"})

    if not _SPACE_ID_RE.match(space_id):
        raise HTTPException(status_code=400, detail={"error": "invalid_space_id"})

    effective_room_id = room_id or (req.room_id if req else None)

    # Same lookup shape as heartbeat_space above (canary, space or network).
    graph_uri, subject = _graph_of(space_id)

    sparql = f"""PREFIX mom: <{MOM}>
SELECT ?endpointUrl WHERE {{
  GRAPH <{graph_uri}> {{
    <{subject}> mom:endpointUrl ?endpointUrl .
  }}
}}"""
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            f"{OXIGRAPH_ENDPOINT}/query",
            content=sparql,
            headers={
                "Content-Type": "application/sparql-query",
                "Accept": "application/sparql-results+json",
            },
        )
        resp.raise_for_status()
    bindings = resp.json().get("results", {}).get("bindings", [])
    if not bindings:
        raise HTTPException(
            status_code=404,
            detail={"error": "no_endpoint", "message": "Space has no registered endpoint URL"},
        )

    if not bot_keys.key_exists(space_id):
        public_key, tutorial = bot_keys.generate_and_store(space_id)
    else:
        public_key = bot_keys.get_public_key(space_id)
        tutorial = bot_keys.TUTORIAL_TEMPLATE.format(space_id=space_id, public_key=public_key)

    if effective_room_id:
        room_iri = _sparql_iri(f"urn:mak:room/{effective_room_id}")
        if room_iri:
            update = (
                f"PREFIX mom: <{MOM}>\n"
                f"INSERT DATA {{ <{room_iri}> mom:botRoom <{subject}> . }}"
            )
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    upd = await client.post(
                        f"{OXIGRAPH_ENDPOINT}/update",
                        content=update,
                        headers={"Content-Type": "application/sparql-update"},
                    )
                    upd.raise_for_status()
            except Exception as e:
                logger.warning("mom:botRoom write failed for %s/%s (non-fatal): %s", effective_room_id, space_id, e)

    return {"public_key": public_key, "tutorial": tutorial, "space_id": space_id}


@app.get("/claim/{token}")
async def claim_link(token: str):
    if not _TOKEN_RE.match(token):
        logger.warning("claim attempt rejected — invalid token format: %.40s", token)
        raise HTTPException(status_code=400, detail="Invalid token format")
    logger.info("claim attempt: %s", token)
    raise HTTPException(status_code=422, detail="Not implemented yet")


@app.post("/api/validate-url")
async def validate_url(req: UrlRequest):
    result = await _fetch_and_validate(req.url)
    result.pop("_data", None)
    result.pop("_source", None)
    # Subset info already in result from _fetch_and_validate
    return result


# Read-url fetches up to 2 MiB for anyone and answers what it read: a cap for the whole service,
# not per caller (behind two proxies the link handler sees one address for everybody).
READ_URL_MAX = 30
READ_URL_WINDOW_SECONDS = 60
_read_url_times: list[datetime] = []


@app.post("/api/read-url")
async def read_url(req: UrlRequest):
    """A space or network file, parsed and validated, written nowhere (#84): `{validation, record}`.

    `validation` is validate-url's answer; `record` is the file as plain JSON (read_record.py),
    null when the file could not be read. Home starts tile A from it (the browser cannot fetch
    another origin)."""
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(seconds=READ_URL_WINDOW_SECONDS)
    _read_url_times[:] = [t for t in _read_url_times if t > cutoff]
    if len(_read_url_times) >= READ_URL_MAX:
        retry_after = READ_URL_WINDOW_SECONDS - int((now - _read_url_times[0]).total_seconds())
        raise HTTPException(status_code=429, detail={"error": "rate_limited", "retry_after_seconds": max(retry_after, 1)})
    _read_url_times.append(now)

    result = await _fetch_and_validate(req.url)
    result.pop("_data", None)
    source = result.pop("_source", None)
    return {"validation": result, "record": read_record(source, result.get("lat"), result.get("lon"))}


@app.post("/api/register-url")
async def register_url(req: UrlRequest, background_tasks: BackgroundTasks):
    result = await _fetch_and_validate(req.url)
    data = result.pop("_data", {})
    source = result.pop("_source", None)

    if not result.get("reachable") or not result.get("schema_valid") or not result.get("coords_found"):
        raise HTTPException(status_code=422, detail={"validation": result})

    name = result["name_found"]
    lat = result["lat"]
    lon = result["lon"]

    slug = _slug(name)
    if not slug:
        raise HTTPException(status_code=422, detail={"error": "space name contains no ASCII-compatible characters; cannot generate a URI slug"})

    is_turtle = source is not None and source.kind == "turtle"
    kind = result["kind"]  # a network or a space, as _fetch_and_validate read the file

    # Dedup by endpointUrl first: if any existing graph (seeded OR confirmed) already
    # carries this URL, reuse its URI. Prevents a duplicate graph when the same real
    # space was seeded under a compound slug (name+city) and later self-registered
    # under the name-only slug, or the coordinator registers twice.
    existing_endpoint_uri = await _find_graph_by_endpoint(OXIGRAPH_ENDPOINT, req.url)
    if existing_endpoint_uri:
        logger.info("[register] endpoint-dedup: %r already exists as %s — reusing URI", req.url, existing_endpoint_uri)
        graph_uri = existing_endpoint_uri
        space_uri = existing_endpoint_uri
        # Drop any orphaned seeded graph with the same name but a different URI
        # (e.g. compound-slug seed openfab-ixelles alongside confirmed openfab).
        orphan_uri = await _find_seeded_graph_by_name(OXIGRAPH_ENDPOINT, name, kind)
        if orphan_uri and orphan_uri != existing_endpoint_uri:
            logger.info("[register] dropping orphaned seeded graph %s (same name, different slug)", orphan_uri)
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    await client.post(
                        f"{OXIGRAPH_ENDPOINT}/update",
                        content=f"DROP GRAPH <{orphan_uri}>",
                        headers={"Content-Type": "application/sparql-update"},
                    )
            except httpx.HTTPError as e:
                logger.warning("[register] DROP orphan %s failed (non-fatal): %s", orphan_uri, e)
    else:
        # Claim-merge: if a bundle-seeded graph (mom:source starts with "scraped-")
        # exists with the same name, claim it in place — same URI, drop+reinsert as
        # self-registered. Handles the VOW/RFF Path B → coordinator flow without
        # needing to parse a city out of the SpaceAPI address string.
        claimed_uri = await _find_seeded_graph_by_name(OXIGRAPH_ENDPOINT, name, kind)
        if claimed_uri:
            logger.info("[register] claim-merge: %r matches seeded graph %s", name, claimed_uri)
            graph_uri = claimed_uri
            space_uri = claimed_uri
        else:
            # Each kind under its own prefix (M1): a network and a space of the same name no
            # longer share a graph, and their ids differ (`<slug>`, `network_<slug>`).
            graph_uri = space_uri = f"{_KIND_PREFIX[kind]}{slug}"

    # The record found sits under the other kind's prefix: a network registered before M1
    # (urn:mak:space/<slug>), or a file that changed kind. It moves to its own prefix, under its
    # name's slug, and the old graph is dropped in the same update: registering again migrates it.
    moved_from = None
    other_prefix = _KIND_PREFIX["space" if kind == "network" else "network"]
    if graph_uri.startswith(other_prefix):
        moved_from = graph_uri
        graph_uri = space_uri = f"{_KIND_PREFIX[kind]}{slug}"
        logger.info("[register] %r is a %s: moving %s to %s", name, kind, moved_from, graph_uri)

    # The snapshot and the first tick go under the id the map uses for this graph (_id_of), as
    # the heartbeat does: a claimed seed or a network must not write under another record's name.
    if space_uri.startswith(tuple(_KIND_PREFIX.values())):
        slug = _id_of(space_uri)

    cls: dict = {}
    reg_observed_at = mint_observed_at()
    # The subset ladder (pin → card → SpaceAPI) is a space's: a network has no pin and its hours
    # are contact hours, so it gets no subset and no "Level up" hint (M1, 2026-11-19).
    if kind != "network":
        try:
            schema_obj = SpaceAPISchema.model_validate(data)
            cls = classify_subset(schema_obj)
        except Exception as e:
            logger.warning("classify_subset failed for %s (non-fatal): %s", slug, e)

    sparql_update = _build_sparql_update(
        graph_uri, space_uri, name, lat, lon, req.url, data,
        subset=cls.get("subset", ""), next_unlock=cls.get("next_unlock"),
        turtle_fields=source.turtle.fields if is_turtle else None,
        profile_url=safe_iri(req.url.split("#", 1)[0]) if is_turtle else None,
        kind=kind,
    )
    if moved_from:
        sparql_update = f"DROP SILENT GRAPH <{moved_from}> ;\n{sparql_update}"

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            upd = await client.post(
                f"{OXIGRAPH_ENDPOINT}/update",
                content=sparql_update,
                headers={"Content-Type": "application/sparql-update"},
            )
            upd.raise_for_status()
    except Exception as e:
        logger.error("Oxigraph UPDATE failed: %s", e)
        raise HTTPException(status_code=502, detail={"error": "triplestore_write_failed"})

    # Snapshot store gets the registration payload so heartbeat ticks can
    # diff against it. No mom:rawContent / snapshot-graph write (Story 3.10).
    try:
        payload, media_type, raw_text = snapshot_parts(source) if source is not None else (data, None, None)
        write_snapshot(slug, reg_observed_at, payload, fetch_status="ok", media_type=media_type, raw_text=raw_text)
    except Exception as snap_err:
        logger.warning("snapshot store write failed for %s: %s", slug, snap_err)

    # The response below is complete once the Oxigraph write and the snapshot land —
    # nothing the client renders depends on the tick or the rematerialize. Both are
    # slow (remote fetch; whole-corpus SPARQL + ~3k snapshot reads) and together they
    # used to push the request past nginx's proxy_read_timeout, so the coordinator was
    # told "failed" about a registration that had in fact succeeded. Defer them.
    async def _finish_registration() -> None:
        # Fire one tick so the new space lights up on the map
        # (writes mom:observedAt/updatedAt/openNow into urn:mak:space/<slug>).
        try:
            await run_space_pipeline(
                uid=slug,
                endpoint_url=req.url,
                graph_uri=graph_uri,
                subject=space_uri,
                oxigraph_endpoint=OXIGRAPH_ENDPOINT,
            )
        except Exception as e:
            logger.warning("[register] initial heartbeat for %s failed (non-fatal): %s", slug, e)

        try:
            await _rematerialize_geojson()
        except Exception as e:
            logger.error("GeoJSON rematerialization failed (non-fatal): %s", e)

    background_tasks.add_task(_finish_registration)

    logger.info("registered space: %s (%s)", name, space_uri)
    return {
        "status": "confirmed",
        "space_uri": space_uri,
        # The map's id for it (_id_of): `<slug>`, or `network_<slug>` for a network (M1). Clients take
        # this rather than parsing space_uri.
        "id": slug,
        "space_name": name,
        "kind": kind,
        "subset": result.get("subset"),
        "subset_score": result.get("subset_score"),
        "unlock_message": result.get("unlock_message"),
        "next_subset": result.get("next_subset"),
        "next_unlock": result.get("next_unlock"),
    }


@app.get("/api/space/{space_id}/snapshots")
async def get_space_snapshots(space_id: str):
    """Fetch ingestion history snapshots for a space."""
    if not re.match(r'^[a-zA-Z0-9_-]+$', space_id):
        return []
    sparql_query = f"""PREFIX mom: <https://mapsofmaking.org/ns/mom#>

SELECT ?graph ?snapshotDate ?snapshotSummary ?lastHttpStatus
WHERE {{
  GRAPH ?graph {{
    ?space <{MOM}snapshotDate> ?snapshotDate ;
           <{MOM}snapshotSummary> ?snapshotSummary .
    OPTIONAL {{ ?space <{MOM}lastHttpStatus> ?lastHttpStatus }}
  }}
  FILTER (STRSTARTS(STR(?graph), "urn:mak:space/{space_id}/"))
}}
ORDER BY DESC(?snapshotDate)
"""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{OXIGRAPH_ENDPOINT}/query",
                content=sparql_query,
                headers={
                    "Content-Type": "application/sparql-query",
                    "Accept": "application/sparql-results+json",
                },
            )
            resp.raise_for_status()
            bindings = resp.json().get("results", {}).get("bindings", [])
    except Exception as e:
        logger.warning("Failed to fetch snapshots for space %s: %s", space_id, e)
        return []

    snapshots = []
    for b in bindings:
        snapshot = {
            "date": b.get("snapshotDate", {}).get("value", ""),
            "summary": b.get("snapshotSummary", {}).get("value", ""),
            "http_status": int(b.get("lastHttpStatus", {}).get("value", 0)) if b.get("lastHttpStatus", {}).get("value") else 0,
        }
        snapshots.append(snapshot)

    return snapshots


# ── One space as the map draws it (Story 14.4 S3, mom-home #13) ─────────────
#
# Home reads the pin back after registering: the coordinator sees where the map
# put them, never a drawing of where home thinks they are. Read from the same
# spaces.geojson the map loads (so it lags the registration until the background
# rematerialize lands: 404 means "not on the map yet", ask again). The file is
# ~4.6 MB, so it is parsed once per change (its mtime), not per request.

_pin_cache: dict = {"mtime": None, "by_id": {}}


def _features_by_id() -> dict:
    path = Path(GEOJSON_OUTPUT)
    try:
        mtime = path.stat().st_mtime_ns
    except FileNotFoundError:
        return {}
    if _pin_cache["mtime"] != mtime:
        data = json.loads(path.read_text())
        _pin_cache["by_id"] = {
            f["properties"]["id"]: f for f in data.get("features", []) if f.get("properties", {}).get("id")
        }
        _pin_cache["mtime"] = mtime
    return _pin_cache["by_id"]


@app.get("/api/space/{space_id}/pin")
async def get_space_pin(space_id: str):
    if not _SPACE_ID_RE.match(space_id):
        raise HTTPException(status_code=400, detail={"error": "bad_space_id"})
    feature = _features_by_id().get(space_id)
    if feature is None:
        raise HTTPException(status_code=404, detail={"error": "not_on_map"})
    props = feature.get("properties", {})
    lon, lat = feature.get("geometry", {}).get("coordinates", [None, None])[:2]
    return {
        "id": space_id,
        "name": props.get("name", ""),
        "lat": lat,
        "lon": lon,
        "city": props.get("city", ""),
        "country": props.get("country", ""),
        "address": props.get("address", ""),
        # Tile C (Story 14.6 S2, mom-home #37): the card's hours as the map holds them, to show the change landed.
        "opening_hours": props.get("opening_hours", ""),
        # Tile C's logo (14.6 S6, mom-home #41): the address the map draws the card's logo from.
        "logo": props.get("logo", ""),
    }


@app.get("/api/space-by-endpoint")
async def get_space_by_endpoint(url: str):
    """The map's id for a space file's address, or 404 (Story 14.4 S4, mom-home #14).

    Home asks it at sign-in: tile B is done when the map holds the space's address.
    Read from Oxigraph (the registration itself), not from spaces.geojson, which
    lags. Same lookup register-url dedups with.
    """
    if safe_iri(url.strip()) is None:
        raise HTTPException(status_code=400, detail={"error": "bad_url"})
    graph = await _find_graph_by_endpoint(OXIGRAPH_ENDPOINT, url)
    # A network's id is network_<slug> (M1); a network not yet moved off urn:mak:space/ keeps its slug.
    space_id = _id_of(graph) if graph else None
    if not space_id or not _SPACE_ID_RE.match(space_id):
        raise HTTPException(status_code=404, detail={"error": "not_registered"})
    return {"id": space_id}


@app.get("/api/space/{space_id}/raw")
async def get_space_raw(space_id: str):
    """Fetch raw endpoint JSON for a space from the cached snapshot.

    Note: live re-fetch is intentionally NOT done here — endpoint freshness is
    the responsibility of the periodic heartbeat (Epic 3), which flips the space
    to broken/stale states when the endpoint stops responding.
    """
    if not re.match(r'^[a-zA-Z0-9_-]+$', space_id):
        return {"error": "no_snapshot", "message": "This space has no cached endpoint content yet."}

    # snapshot_store (SQLite) is the only raw-payload source. mom:rawContent
    # triples were retired in Story 3.10.
    snap = read_snapshot(space_id)
    if snap is None or not snap.get("payload"):
        return {"error": "no_snapshot", "message": "This space has no cached endpoint content yet."}
    media_type = snap.get("media_type") or "application/json"
    if media_type == "text/turtle":
        # Story 14.7 AC3: the source as written. The contact is read from it, not from the
        # index (handles stay out of the graph by decision), for the card to show: a list of
        # {type, value} (mom-home #39), or a dict in snapshots read before it. The card takes both.
        payload = snap["payload"] if isinstance(snap["payload"], dict) else {}
        out = {"raw": snap.get("raw_text") or "", "mediaType": media_type, "snapshotDate": snap.get("observed_at", "")}
        contact = payload.get("contact") or {}
        if contact:
            out["contact"] = contact
        return out
    return {
        "raw": snap["payload"],
        "mediaType": media_type,
        "snapshotDate": snap.get("observed_at", ""),
    }


# ── Geocode proxy (Story 9.3 / AC6) ─────────────────────────────────────────

class GeocodeRequest(BaseModel):
    # A space sends its address and city (as before); a network sends only `area` (2026-11-19).
    address: str = ""
    city: str = ""
    postcode: str = ""
    # country_code is now DERIVED, not demanded (Story 9.12 §2): the wizard no
    # longer sends it. Kept optional so it still sharpens the query when present.
    country_code: str = ""
    # An ISO 3166-1 (`BE`) or 3166-2 (`BE-VLG`) code: the area a network serves.
    area: str = ""
    # An area by its name, anywhere in the world ("Flanders"), and the language its names come
    # back in: the areas it may be (2026-11-19). None: not this shape; "" is refused.
    area_search: Optional[str] = None
    lang: Optional[str] = None


_NO_RESULT = {"lat": None, "lon": None, "country_code": None, "postcode": None, "display_name": None}


def _area_query(area: str) -> tuple[Any, dict]:
    """The Nominatim request for an ISO 3166 code: a country by its code (structured), a
    subdivision by its code (Nominatim indexes them; the answer is checked below)."""
    cc = area[:2].lower()
    if len(area) == 2:
        return {"country": area}, {"featuretype": "country", "country_codes": cc}
    # No featuretype for a subdivision: geopy sends it as `featureType`, which Nominatim reads
    # differently and answers with the provinces inside the region (BE-VLG gave West-Vlaanderen,
    # 2026-11-19). Several answers are asked; `_pick_area` keeps the area itself.
    return area, {"country_codes": cc, "exactly_one": False, "limit": 5}


def _area_matches(area: str, address: dict) -> bool:
    """Is Nominatim's answer the area asked for? A country by its code; a subdivision by its
    ISO3166-2-lvl<n> key (Flanders comes back as `state`, Brussels as `region`: the key is the test)."""
    if (address.get("country_code") or "").upper() != area[:2]:
        return False
    if len(area) == 2:
        return True
    # The deepest ISO3166-2 level is the place itself: a province inside Flanders also carries
    # `ISO3166-2-lvl4: BE-VLG`, but its own code (lvl6) is BE-VWV.
    levels = _iso_levels(address)
    return bool(levels) and str(address[levels[-1]]).upper() == area


def _iso_levels(address: dict) -> list[str]:
    """The ISO3166-2-lvl<n> keys of a Nominatim address, shallowest first."""
    return sorted((k for k in address if k.startswith("ISO3166-2-lvl")), key=lambda k: int(k.rsplit("lvl", 1)[1] or 0))


def _pick_area(area: str, location: Any) -> Any:
    """The first answer that is the area itself (Nominatim gives one, or a list when asked for several)."""
    for loc in (location if isinstance(location, list) else [location] if location is not None else []):
        if _area_matches(area, loc.raw.get("address", {}) or {}):
            return loc
    return None


# What an area search keeps: a country, or a subdivision Nominatim files as one of these.
# Cities, towns, counties, streets are left out (Brussels the city, Scotland County, Paris), but for
# a county that is a region under another name (Brussels-Capital, below).
_AREA_TYPES = ("country", "state", "region", "province")
MAX_AREA_SEARCH = 100
MAX_CANDIDATES = 5
_LANG_RE = re.compile(r"^[a-z]{2}$")


def _own_code(raw: dict) -> Optional[str]:
    """The ISO code of the place itself, or None. A country: its country_code. A subdivision: the
    ISO3166-2 key Nominatim puts right after the place's own component, when it is the deepest one;
    a province without a code of its own carries only its parent's (`province, state, lvl4`)."""
    address = raw.get("address") or {}
    cc = str(address.get("country_code") or "").upper()
    kind = raw.get("addresstype")
    if kind == "country":
        return clean_area(cc)
    keys = list(address)
    if kind == "county":
        # A region Nominatim files as a county: Brussels-Capital comes back `county, region, lvl4` with
        # both components its own name (seen live, 2026-11-19). A real county (Scotland County, North
        # Carolina: `county, state, lvl4`) has another name under its state and stays out.
        kind = next((k for k in keys if k in _AREA_TYPES[1:] and raw.get("name") and address[k] == raw.get("name")), None)
    if kind not in _AREA_TYPES[1:] or kind not in keys or keys.index(kind) + 1 >= len(keys):
        return None
    own = keys[keys.index(kind) + 1]
    levels = _iso_levels(address)
    if not levels or own != levels[-1]:
        return None
    code = clean_area(str(address[own]))
    return code if code and len(code) > 2 and code[:2] == cc else None


def _answers(location: Any) -> list[Any]:
    """Nominatim's answers as a list (it gives one, a list, or None)."""
    return location if isinstance(location, list) else [location] if location is not None else []


def _area_candidates(location: Any) -> list[dict[str, Any]]:
    """The countries and subdivisions among Nominatim's answers, each once, in Nominatim's order."""
    out: list[dict[str, Any]] = []
    for loc in _answers(location):
        raw = loc.raw or {}
        code = _own_code(raw)
        if not code or any(c["code"] == code for c in out):
            continue
        name = clean_area_name(raw.get("name")) or clean_area_name((loc.address or "").split(",")[0])
        out.append({"code": code, "name": name, "display_name": loc.address, "lat": loc.latitude,
                    "lon": loc.longitude, "fidelity": "country" if len(code) == 2 else "region"})
    return out


# ── The ISO 3166 list, offline (mapsofmaking/maps_of_making#87, 2026-11-20) ──────────────────────
# Nominatim has no fuzzy match ("region bruxellles capitale" found nothing) and answers "Brussels"
# with the city, so an area search first reads pycountry's ISO 3166 list: every country and every
# subdivision (all are official areas), under every name pycountry has for it (its local name and
# each translation), compared casefolded and without accents, typos forgiven by difflib.
_AREA_FUZZY_CUTOFF = 0.9    # 'region bruxellles capitale' ~ 'region de bruxelles capitale': 0.93;
                            # the noise sits below (Scotland ~ Southland 0.82, Flanders ~ Landes 0.86)
_AREA_FUZZY_MIN = 5         # shorter than that, a near name is another place ("Gent", "Bern")
_AREA_FUZZY_MAX = 3
# A candidate that is not one of Nominatim's own answers has no centre yet: it is asked by its code
# (the `{area}` path, one Nominatim call each at 1 req/s), at most this many per search.
MAX_CENTRE_LOOKUPS = 3
# What Nominatim files a town as: the areas it sits in are offered instead (Brussels → BE-BRU).
_CITY_TYPES = frozenset({"city", "town", "village", "hamlet", "municipality", "suburb", "borough",
                         "city_district", "quarter", "neighbourhood"})
# An area's centre by code, (lat, lon), or None when Nominatim doesn't know the code: areas don't move.
_centres: dict[str, Optional[tuple[float, float]]] = {}
_JOINERS = {"and", "y", "et", "und", "e", "i"}


def _fold(text: str) -> str:
    """A name as compared: casefolded, accents and punctuation gone, one space between words."""
    text = "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c)).casefold()
    return " ".join(re.sub(r"[\W_]+", " ", text).split())


def _uninvert(name: str) -> Optional[str]:
    """ISO files some names inverted ("Bruxelles-Capitale, Région de"): the name as said, or None."""
    head, sep, tail = name.partition(", ")
    return f"{tail} {head}" if sep and ", " not in tail else None


def _said(name: str) -> str:
    """A name to show: un-inverted when the part after the comma is a short title ("Région wallonne",
    "City of Bristol"), kept when it is a list ("Southern Nations, Nationalities and Peoples")."""
    tail = name.partition(", ")[2].split()
    flipped = _uninvert(name)
    return flipped if flipped and len(tail) <= 3 and not _JOINERS & set(tail) else name


def _iso_locales(domain: str) -> list[str]:
    root = Path(pycountry.LOCALES_DIR)
    return sorted(p.name for p in root.iterdir() if (p / "LC_MESSAGES" / f"{domain}.mo").exists())


def _catalogue(domain: str, lang: str) -> gettext.GNUTranslations:
    with open(Path(pycountry.LOCALES_DIR) / lang / "LC_MESSAGES" / f"{domain}.mo", "rb") as f:
        return gettext.GNUTranslations(f)


@functools.lru_cache(maxsize=None)
def _translator(domain: str, lang: str) -> gettext.NullTranslations:
    return gettext.translation(domain, pycountry.LOCALES_DIR, languages=[lang], fallback=True)


@functools.lru_cache(maxsize=1)
def _iso_index() -> tuple[dict[str, tuple[str, ...]], tuple[str, ...]]:
    """Every folded name → the codes it names (countries first), and the names as a list for difflib.
    Built once, on the first search (about a second, some 55,000 names, about 13 MB held)."""
    index: dict[str, list[str]] = {}

    def add(name: str, code: str) -> None:
        for part in name.split(";"):
            for said in (part.strip(), _uninvert(part.strip())):
                key = _fold(said or "")
                if key and code not in index.setdefault(key, []):
                    index[key].append(code)

    for domain, items in (("iso3166-1", pycountry.countries), ("iso3166-2", pycountry.subdivisions)):
        # Read once and let go: every locale's catalogue held for good is some 23 MB (gettext.translation
        # keeps each it opens), so the files are read directly; only the languages asked for stay (_translator).
        translators = [gettext.NullTranslations()] + [_catalogue(domain, lang) for lang in _iso_locales(domain)]
        for item in items:
            code = item.alpha_2 if domain == "iso3166-1" else item.code
            names = [item.name] + [getattr(item, a, None) for a in ("common_name", "official_name")]
            for name in filter(None, names):
                for t in translators:
                    add(t.gettext(name), code)
    frozen = {k: tuple(v) for k, v in index.items()}
    return frozen, tuple(frozen)


def _iso_matches(text: str) -> tuple[list[str], list[str]]:
    """The ISO codes `text` names exactly, then those it nearly names (a typo), each once."""
    index, keys = _iso_index()
    key = _fold(text)
    exact = [c for c in index.get(key, ()) if clean_area(c)]
    near: list[str] = []
    if len(key) >= _AREA_FUZZY_MIN:
        for k in difflib.get_close_matches(key, keys, n=10, cutoff=_AREA_FUZZY_CUTOFF):
            near += [c for c in index[k] if clean_area(c) and c not in exact and c not in near]
    return exact, near[:_AREA_FUZZY_MAX]


def _iso_name(code: str, lang: str) -> str:
    """An ISO area's name in `lang` when pycountry has it, else its local name."""
    if len(code) == 2:
        item, domain = pycountry.countries.get(alpha_2=code), "iso3166-1"
        base = item and (getattr(item, "common_name", None) or item.name)
    else:
        item, domain = pycountry.subdivisions.get(code=code), "iso3166-2"
        base = item and item.name
    return clean_area_name(_said(_translator(domain, lang).gettext(base))) if base else ""


def _city_areas(location: Any) -> list[tuple[str, str]]:
    """The areas Nominatim's towns sit in, deepest first (Gent: Oost-Vlaanderen, then Vlaanderen), as
    (code, name): each ISO3166-2 key of a town's address that is a real subdivision, named by the
    address component just before it."""
    out: list[tuple[str, str]] = []
    for loc in _answers(location):
        raw = loc.raw or {}
        if raw.get("addresstype") not in _CITY_TYPES:
            continue
        address = raw.get("address") or {}
        keys = list(address)
        for level in reversed(_iso_levels(address)):
            code = clean_area(str(address[level]))
            if not code or len(code) == 2 or pycountry.subdivisions.get(code=code) is None or any(c == code for c, _ in out):
                continue
            before = keys[keys.index(level) - 1] if keys.index(level) else ""
            name = "" if not before or before.startswith("ISO3166") else clean_area_name(str(address[before]))
            out.append((code, name))
    return out


async def _area_centre(code: str) -> Optional[tuple[float, float]]:
    """An area's centre, asked by its code like `{area}` (cached; a Nominatim error is not)."""
    if code not in _centres:
        query, kwargs = _area_query(code)
        loc = _pick_area(code, await _nominatim(query, **kwargs))
        _centres[code] = (loc.latitude, loc.longitude) if loc is not None else None
    return _centres[code]


async def _area_search(text: str, lang: str) -> list[dict[str, Any]]:
    """The areas `text` may be, in this order, each code once, at most MAX_CANDIDATES: those the ISO
    list names exactly, Nominatim's own areas, the areas Nominatim's towns sit in, those the ISO list
    nearly names. One Nominatim search, then a centre asked for each candidate it didn't give
    (cached, at most MAX_CENTRE_LOOKUPS); one with no centre is left out (home pins the pick)."""
    # Off the event loop: the first search builds the index (about a second), each one runs difflib.
    exact, near = await asyncio.get_running_loop().run_in_executor(None, _iso_matches, text)
    found = await _nominatim(text, exactly_one=False, limit=10, language=lang)
    own = {c["code"]: c for c in _area_candidates(found)}
    towns = _city_areas(found)
    named = dict(towns)
    out: list[dict[str, Any]] = []
    lookups = 0
    for code in dict.fromkeys([*exact, *own, *(c for c, _ in towns), *near]):
        if len(out) >= MAX_CANDIDATES:
            break
        if code in own:
            out.append(own[code])
            continue
        if code not in _centres:
            if lookups >= MAX_CENTRE_LOOKUPS:
                continue
            lookups += 1
            try:
                await _area_centre(code)
            except HTTPException:
                continue
        centre = _centres.get(code)
        name = named.get(code) or _iso_name(code, lang)
        if centre is None or not name:
            continue
        country = _iso_name(code[:2], lang) if len(code) > 2 else ""
        out.append({"code": code, "name": name, "display_name": f"{name}, {country}" if country else name,
                    "lat": centre[0], "lon": centre[1], "fidelity": "country" if len(code) == 2 else "region"})
    return out


async def _nominatim(query: Any, **kwargs):
    try:
        return await asyncio.get_running_loop().run_in_executor(
            None, lambda: _geocode(query, addressdetails=True, **kwargs)
        )
    except (GeocoderTimedOut, GeocoderUnavailable, GeocoderServiceError) as exc:
        logger.warning("Nominatim unavailable for query %r: %s", query, exc)
        raise HTTPException(status_code=503, detail={"error": "geocoding_unavailable"})
    except Exception as exc:
        logger.warning("Nominatim unexpected error for query %r: %s", query, exc)
        raise HTTPException(status_code=503, detail={"error": "geocoding_unavailable"})


@app.post("/api/geocode")
async def geocode(req: GeocodeRequest):
    """Proxy Nominatim geocoding for home.mapsofmaking.org and the bot — 1 req/s rate-limited (RateLimiter).

    Three shapes:
    - a space: `{address, city, postcode?, country_code?}` (as before);
    - a network: `{area}`, an ISO 3166-1/-2 code (`BE`, `BE-VLG`), 2026-11-19: the centre
      of that area, Nominatim's point for it;
    - a network looking for its area by name: `{area_search, lang?}` (2026-11-19), answered
      `{candidates: [{code, name, display_name, lat, lon, fidelity}]}`, at most 5, maybe none:
      the countries and subdivisions with an ISO code of their own, names in `lang` (default en).
      Since #87 (2026-11-20) the ISO list is read first (typos forgiven) and a town brings the
      areas it sits in; a candidate Nominatim's search didn't place costs one more call (its centre,
      cached), so a search may take a few seconds of the shared 1 req/s.
      422 for an empty or over-long search or a lang that is not two letters.

    Returns {lat, lon, country_code, postcode, display_name, fidelity, area} on success,
    nulls on no-result (and `fidelity`/`area` still say what was asked), 422 when neither
    shape is given or the area is not an ISO code, 503 on error. country_code is DERIVED
    from Nominatim address components (Story 9.12 §2: "ask the address, derive the rest").
    `fidelity` is mom:geolocationFidelity's value for the pin: `exact` (with a street),
    `city`, `region` (a subdivision), `country`.
    The 1 req/s limit is this process's, shared by every caller; there is no per-IP
    cap in front of it (the old Hetzner nginx one is gone).
    """
    if req.area_search is not None:
        text = req.area_search.strip()
        if not text or len(text) > MAX_AREA_SEARCH:
            raise HTTPException(status_code=422, detail={"error": "bad_area_search", "message": f"area_search is a name, 1 to {MAX_AREA_SEARCH} characters"})
        lang = (req.lang if req.lang is not None else "en").strip().lower()
        if not _LANG_RE.match(lang):
            raise HTTPException(status_code=422, detail={"error": "bad_lang", "message": "lang is a two-letter language code, e.g. en"})
        return {"candidates": await _area_search(text, lang)}

    if req.area:
        area = clean_area(req.area)
        if area is None:
            raise HTTPException(status_code=422, detail={"error": "bad_area", "message": "area is an ISO 3166-1 or 3166-2 code, e.g. BE or BE-VLG"})
        fidelity = "country" if len(area) == 2 else "region"
        query, kwargs = _area_query(area)
        location = _pick_area(area, await _nominatim(query, **kwargs))
        if location is None:
            return {**_NO_RESULT, "fidelity": None, "area": area}
        return {
            "lat": location.latitude,
            "lon": location.longitude,
            "country_code": area[:2],
            "postcode": None,
            "display_name": location.address,
            "fidelity": fidelity,
            "area": area,
        }

    if not (req.address.strip() or req.city.strip()):
        raise HTTPException(status_code=422, detail={"error": "nothing_to_geocode", "message": "send address and city (a space) or area (a network)"})

    # Drop empty parts so a missing postcode/country doesn't poison the query.
    query = ", ".join(p for p in (req.address, req.city, req.postcode, req.country_code) if p)
    location = await _nominatim(query)

    if location is None:
        return {**_NO_RESULT, "fidelity": None, "area": None}

    # Derive what Bernard pulls from the address (Story 9.12 §2): ISO country code
    # (uppercased to match the wizard) and postcode. Either may be absent for some
    # results → None, and the wizard handles the gap (manual country fallback;
    # postcode simply stays empty).
    addr = location.raw.get("address", {}) or {}
    cc = addr.get("country_code", "")
    return {
        "lat": location.latitude,
        "lon": location.longitude,
        "country_code": cc.upper() if cc else None,
        "postcode": addr.get("postcode") or None,
        "display_name": location.address,
        "fidelity": "exact" if req.address.strip() else "city",
        "area": None,
    }
