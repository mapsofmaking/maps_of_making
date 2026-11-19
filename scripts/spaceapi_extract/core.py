"""Extract SpaceAPI v15 core fields to schema.org keys."""
from __future__ import annotations

import json
from typing import Any

from .area import clean_areas, clean_fidelity, clean_kind, country_of


def extract_core(payload: dict) -> dict[str, Any]:
    """Extract SpaceAPI v15 core fields from a payload dict.

    Returns a CURIE-keyed dict suitable for triples_for().
    Handles both SpaceAPI v14 flat keys (space, url, location.lat) and
    JSON-LD schema.org keys (schema:name, schema:geo, schema:url).

    Pure function — no HTTP, no SPARQL, no Oxigraph.
    """
    fields: dict[str, Any] = {}

    name = payload.get("space") or payload.get("name") or payload.get("schema:name")
    if name and isinstance(name, str):
        fields["schema:name"] = name

    loc = payload.get("location") or {}
    lat = loc.get("lat")
    lon = loc.get("lon")
    if lat is not None and lon is not None:
        try:
            fields["schema:geo"] = {"lat": float(lat), "lon": float(lon)}
        except (TypeError, ValueError):
            pass

    url = payload.get("url") or payload.get("schema:url")
    if url and isinstance(url, str):
        fields["schema:url"] = url

    logo = payload.get("logo") or payload.get("schema:logo")
    if logo and isinstance(logo, str):
        fields["schema:logo"] = logo

    contact = payload.get("contact")
    if isinstance(contact, dict):
        fields["schema:contactJson"] = json.dumps(contact, separators=(",", ":"))

    desc = payload.get("description") or payload.get("schema:description")
    if desc and isinstance(desc, str):
        fields["schema:description"] = desc

    hours = payload.get("opening_hours") or payload.get("schema:openingHours")
    if hours and isinstance(hours, str):
        fields["schema:openingHours"] = hours

    raw_tags = (
        payload.get("schema:knowsAbout")
        or payload.get("knowsAbout")
        or payload.get("specialties")
    )
    if not raw_tags:
        ext = payload.get("ext") or {}
        if isinstance(ext, dict):
            raw_tags = ext.get("tags")
    if isinstance(raw_tags, str):
        raw_tags = [raw_tags]
    if isinstance(raw_tags, list):
        tags = [str(t) for t in raw_tags if t]
        if tags:
            fields["schema:knowsAbout"] = tags

    # Tier-2 horizontal fields — nested under "mom": {} block (preferred) or bare top-level
    # fallbacks for SpaceAPI convention compat ("memberOf") and transition (ext_fab.sdgs).
    mom_block = payload.get("mom") or {}

    raw_member = mom_block.get("memberOf") or payload.get("memberOf")
    if isinstance(raw_member, str):
        raw_member = [raw_member]
    if isinstance(raw_member, list):
        slugs = [str(s).strip() for s in raw_member if isinstance(s, str) and s.strip()]
        if slugs:
            fields["mom:memberOf"] = [
                s if (":" in s or s.startswith("urn:")) else f"urn:mak:network/{s.lower()}"
                for s in slugs
            ]

    sdgs = mom_block.get("sdgs")
    if sdgs is None:
        ext_fab = payload.get("ext_fab") or {}
        if isinstance(ext_fab, dict):
            sdgs = ext_fab.get("sdgs")
    if isinstance(sdgs, list):
        cleaned = [int(s) for s in sdgs if isinstance(s, (int, float)) and 1 <= int(s) <= 17]
        if cleaned:
            fields["mom:sdgs"] = cleaned

    # A network (2026-11-19): the areas it serves and how coarse its pin is, after schema:geo
    # (the heartbeat's geo write clears the old fidelity before this one is written back).
    if isinstance(mom_block, dict):
        raw_areas = mom_block.get("areaServed")
        if isinstance(raw_areas, str):
            raw_areas = [raw_areas]
        areas = clean_areas(raw_areas) if isinstance(raw_areas, list) else []
        if areas:
            fields["schema:areaServed"] = areas
            cc = loc.get("country_code") if isinstance(loc, dict) else None
            if not (isinstance(cc, str) and cc) and country_of(areas):
                fields["mom:countryCode"] = country_of(areas)
        fidelity = clean_fidelity(mom_block.get("geolocationFidelity"))
        if fidelity:
            fields["mom:geolocationFidelity"] = fidelity

    return fields


def kind_of(payload: Any) -> str:
    """'network' or 'space': what a SpaceAPI payload says it is (`mom.kind`)."""
    mom_block = payload.get("mom") if isinstance(payload, dict) else None
    return clean_kind(mom_block.get("kind")) if isinstance(mom_block, dict) else "space"
