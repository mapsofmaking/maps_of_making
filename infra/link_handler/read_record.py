"""What a space or network file holds, as plain JSON, for home to start a form from (#84).

`POST /api/read-url` answers this beside the validation: the same readers as register
(`extract_core` + `extract_mom` for SpaceAPI JSON, `parse_space_turtle` for Turtle), so what
home pre-fills is what the map would keep. Nothing here writes.

`unmapped` names what the readers leave out, so home can say "not carried over" instead of
dropping it silently: JSON top-level keys (and keys inside `location`, `mom`, `ext_fab`), or
Turtle predicates (full IRIs). `api` and `api_compatibility` are SpaceAPI's own bookkeeping,
not the space's: a writer sets them again, so they are not listed.

Pure functions, no I/O.
"""
from __future__ import annotations

from typing import Any, Optional

# The record's keys, in the order a reader expects them. None / [] when the file has nothing.
_FROM_FIELDS = (
    ("name", "schema:name"),
    ("address", "mom:address"),
    ("country_code", "mom:countryCode"),
    ("timezone", "mom:timeZone"),
    ("logo", "schema:logo"),
    ("url", "schema:url"),
    ("description", "schema:description"),
    ("opening_hours", "schema:openingHours"),
    ("geolocationFidelity", "mom:geolocationFidelity"),
)
_LISTS = (("memberOf", "mom:memberOf"), ("sdgs", "mom:sdgs"), ("knowsAbout", "schema:knowsAbout"), ("areaServed", "schema:areaServed"))

# SpaceAPI JSON: what extract_core / extract_mom read. Keys inside the dicts below are checked one by one.
_JSON_READ = {"space", "name", "schema:name", "url", "schema:url", "logo", "schema:logo", "contact",
              "description", "schema:description", "opening_hours", "schema:openingHours",
              "schema:knowsAbout", "knowsAbout", "specialties", "memberOf", "location", "mom",
              "api", "api_compatibility"}
_LOCATION_READ = {"lat", "lon", "address", "country_code", "timezone"}
_MOM_READ = {"kind", "memberOf", "sdgs", "areaServed", "geolocationFidelity"}


def record_of(fields: dict[str, Any], kind: str, contact: dict[str, Any], unmapped: list[str]) -> dict[str, Any]:
    """The plain record from a reader's CURIE fields."""
    geo = fields.get("schema:geo") or {}
    rec: dict[str, Any] = {key: fields.get(curie) for key, curie in _FROM_FIELDS}
    rec["lat"] = geo.get("lat")
    rec["lon"] = geo.get("lon")
    rec["contact"] = contact
    for key, curie in _LISTS:
        rec[key] = list(fields.get(curie) or [])
    rec["kind"] = kind
    rec["unmapped"] = unmapped
    return rec


def json_unmapped(data: dict[str, Any], fields: dict[str, Any]) -> list[str]:
    """The keys of a SpaceAPI payload no reader takes, sorted. `fields`: what the readers took (for ext_fab.sdgs, ext.tags)."""
    out = [k for k in data if k not in _JSON_READ and k not in ("ext", "ext_fab")]
    loc = data.get("location")
    if isinstance(loc, dict):
        out += [f"location.{k}" for k in loc if k not in _LOCATION_READ]
    mom = data.get("mom")
    if isinstance(mom, dict):
        out += [f"mom.{k}" for k in mom if k not in _MOM_READ]
    mom_sdgs = isinstance(mom, dict) and mom.get("sdgs") is not None
    tags_from_keys = any(data.get(k) for k in ("schema:knowsAbout", "knowsAbout", "specialties"))
    for block, used, used_when in (("ext_fab", "sdgs", not mom_sdgs and "mom:sdgs" in fields),
                                   ("ext", "tags", not tags_from_keys and "schema:knowsAbout" in fields)):
        if block not in data:
            continue
        value = data[block]
        if not isinstance(value, dict) or not used_when:
            out.append(block)  # nothing read from it: the whole block stays behind
        else:
            out += [f"{block}.{k}" for k in value if k != used]
    return sorted(out)


def json_contact(data: dict[str, Any]) -> dict[str, Any]:
    """SpaceAPI's own contact dict, as the file has it ({} when absent or not a dict)."""
    contact = data.get("contact")
    return dict(contact) if isinstance(contact, dict) else {}


def turtle_contact(handles: list[dict[str, str]]) -> tuple[dict[str, str], list[str]]:
    """Turtle's handles in SpaceAPI's contact shape: one value per type, the first in the reader's order.
    A second handle of a type does not fit the dict: it is named in unmapped as `contact.<type>`."""
    contact: dict[str, str] = {}
    extra: list[str] = []
    for h in handles:
        if h["type"] in contact:
            if f"contact.{h['type']}" not in extra:
                extra.append(f"contact.{h['type']}")
        else:
            contact[h["type"]] = h["value"]
    return contact, extra


def read_record(source: Any) -> Optional[dict[str, Any]]:
    """The record a usable `source.Source` holds (JSON or Turtle); None for anything else."""
    from spaceapi_extract import extract_core, extract_mom, kind_of

    if source is None or not source.ok:
        return None
    if source.kind == "turtle":
        parsed = source.turtle
        contact, extra = turtle_contact(parsed.contact)
        return record_of(parsed.fields, parsed.kind, contact, sorted(parsed.unread + extra))
    data = source.data
    if not isinstance(data, dict):
        return None
    fields = {**extract_core(data), **extract_mom(data)}
    return record_of(fields, kind_of(data), json_contact(data), json_unmapped(data, fields))
