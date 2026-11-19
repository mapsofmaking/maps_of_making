"""What a network adds to a space file: its kind, the areas it serves, how coarse its pin is.

A network (not a space) registers too: typed `mom:Network, schema:Organization` in Turtle,
`"mom": {"kind": "network", ...}` in SpaceAPI JSON. It has no address; it serves one or more
areas and sits at the centre of its area with `mom:geolocationFidelity` saying so. An area is
an ISO 3166-1 (`BE`) or ISO 3166-2 (`BE-VLG`) code and its name ("Flanders"): one
`schema:AdministrativeArea` node per area in Turtle, `{"code", "name"}` in JSON; a bare code
(the first shape) is still read, without a name. Decided with Nicolas, 2026-11-19
(docs/reference/space-file.md). The Turtle reader and the JSON extractor both clean values
here, so the two formats keep writing the same statements.

Pure functions, no I/O.
"""
from __future__ import annotations

import re
from typing import Any, Iterable, Optional

KINDS = ("space", "network")
# The ontology's values (mom.ttl, mom:geolocationFidelity); 'region' added 2026-11-19 for networks.
FIDELITIES = ("exact", "approximate", "city", "region", "country")
MAX_AREAS = 10
MAX_AREA_NAME = 200

# ISO 3166-1 alpha-2, or ISO 3166-2: the country, a hyphen, one to three letters or digits.
AREA_RE = re.compile(r"^[A-Z]{2}(-[A-Z0-9]{1,3})?$")
# Control characters never belong in a name; the map's query uses two of them as separators.
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


def clean_area(value: Any) -> Optional[str]:
    """`value` as an ISO 3166-1/-2 code (upper case), or None."""
    if not isinstance(value, str):
        return None
    code = value.strip().upper()
    return code if AREA_RE.match(code) else None


def clean_area_name(value: Any) -> str:
    """`value` as an area's name: one line, trimmed, at most MAX_AREA_NAME characters; "" when none."""
    if not isinstance(value, str):
        return ""
    return " ".join(_CONTROL.sub(" ", value).split())[:MAX_AREA_NAME]


def _area(value: Any) -> Optional[dict[str, str]]:
    """One area, {code, name}, from a bare code or a {code, name} object; None when the code is not ISO."""
    if isinstance(value, dict):
        code = clean_area(value.get("code"))
        return {"code": code, "name": clean_area_name(value.get("name"))} if code else None
    code = clean_area(value)
    return {"code": code, "name": ""} if code else None


def clean_areas(values: Iterable[Any]) -> list[dict[str, str]]:
    """The valid areas among `values` (bare codes or {code, name}), as [{code, name}]: one per code,
    sorted by code (a graph has no order), at most MAX_AREAS. Two of one code: a name beats none,
    then the smaller name, so the same file always reads the same."""
    best: dict[str, str] = {}
    for area in filter(None, map(_area, values)):
        code, name = area["code"], area["name"]
        if code not in best or (name and (not best[code] or name < best[code])):
            best[code] = name
    return [{"code": c, "name": best[c]} for c in sorted(best)][:MAX_AREAS]


def clean_fidelity(value: Any) -> Optional[str]:
    if not isinstance(value, str):
        return None
    v = value.strip().lower()
    return v if v in FIDELITIES else None


def clean_kind(value: Any) -> str:
    """'network' when said so, else 'space' (every file before 2026-11-19 is a space)."""
    return "network" if isinstance(value, str) and value.strip().lower() == "network" else "space"


def country_of(areas: Iterable[dict[str, str]]) -> Optional[str]:
    """The one country all `areas` are in, or None (none, or several)."""
    countries = {a["code"][:2] for a in areas}
    return countries.pop() if len(countries) == 1 else None
