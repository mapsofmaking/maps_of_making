"""What a network adds to a space file: its kind, the areas it serves, how coarse its pin is.

A network (not a space) registers too: typed `mom:Network, schema:Organization` in Turtle,
`"mom": {"kind": "network", ...}` in SpaceAPI JSON. It has no address; it serves one or more
areas, ISO 3166-1 (`BE`) or ISO 3166-2 (`BE-VLG`) codes, and sits at the centre of its area
with `mom:geolocationFidelity` saying so. Decided with Nicolas, 2026-11-19
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

# ISO 3166-1 alpha-2, or ISO 3166-2: the country, a hyphen, one to three letters or digits.
AREA_RE = re.compile(r"^[A-Z]{2}(-[A-Z0-9]{1,3})?$")


def clean_area(value: Any) -> Optional[str]:
    """`value` as an ISO 3166-1/-2 code (upper case), or None."""
    if not isinstance(value, str):
        return None
    code = value.strip().upper()
    return code if AREA_RE.match(code) else None


def clean_areas(values: Iterable[Any]) -> list[str]:
    """The valid codes among `values`, unique and sorted (a graph has no order), at most MAX_AREAS."""
    out = sorted({c for c in (clean_area(v) for v in values) if c})
    return out[:MAX_AREAS]


def clean_fidelity(value: Any) -> Optional[str]:
    if not isinstance(value, str):
        return None
    v = value.strip().lower()
    return v if v in FIDELITIES else None


def clean_kind(value: Any) -> str:
    """'network' when said so, else 'space' (every file before 2026-11-19 is a space)."""
    return "network" if isinstance(value, str) and value.strip().lower() == "network" else "space"


def country_of(areas: list[str]) -> Optional[str]:
    """The one country all `areas` are in, or None (none, or several)."""
    countries = {a[:2] for a in areas}
    return countries.pop() if len(countries) == 1 else None
