"""Read a Turtle space file (Story 14.7): what the map keeps from `space.ttl`.

The pod door (14.4) writes Turtle; the self-host door (14.5) writes SpaceAPI
JSON. This reads the first so that `triples_for` writes the same statements for
both (docs/reference/space-file.md). The result's `fields` has the shape
`extract_core` + `extract_mom` produce for JSON: CURIE keys, same values.

The file is untrusted: a pod has other writers. Only the allow-list below is
read, every IRI that can reach a SPARQL `<...>` is checked, lengths are capped.
Email and the Matrix room are not graph fields (the index does not hold them);
they come back in `contact`, for the card to show from the source.

Pure function: no HTTP, no SPARQL, no Oxigraph. Errors are values.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Optional
from urllib.parse import unquote, urldefrag, urlparse

from rdflib import BNode, Graph, Literal, URIRef
from rdflib.namespace import RDF

SCHEMA = "https://schema.org/"
SCHEMA_HTTP = "http://schema.org/"
MOM = "https://mapsofmaking.org/ns/mom#"

MAX_TRIPLES = 5000
_CAPS = {"name": 200, "description": 5000, "hours": 500, "street": 300, "city": 200, "postcode": 30, "iri": 2000, "contact": 300}

# What may not appear in an IRI that is written between < and > in SPARQL.
_BAD_IRI = re.compile(r"[\x00-\x20<>\"{}|\\^`]")
_NETWORK_IRI = re.compile(r"^urn:mak:network/[a-z0-9_-]{1,64}$")
_COUNTRY = re.compile(r"^[A-Za-z]{2}$")


@dataclass
class ParsedSpace:
    """`fields`: graph fields (CURIE keys). `contact`: email / matrix, not in the graph. `error`: why nothing was read."""

    fields: dict[str, Any] = field(default_factory=dict)
    contact: dict[str, str] = field(default_factory=dict)
    error: Optional[str] = None
    error_code: Optional[str] = None

    @property
    def name(self) -> Optional[str]:
        return self.fields.get("schema:name")

    @property
    def lat(self) -> Optional[float]:
        return (self.fields.get("schema:geo") or {}).get("lat")

    @property
    def lon(self) -> Optional[float]:
        return (self.fields.get("schema:geo") or {}).get("lon")


def _fail(code: str, message: str) -> ParsedSpace:
    return ParsedSpace(error=message, error_code=code)


def safe_iri(value: str, networks: bool = False) -> Optional[str]:
    """The IRI if it can be written into SPARQL as <...>, else None. http(s) only; `urn:mak:network/<slug>` when `networks`."""
    if not isinstance(value, str) or not value or len(value) > _CAPS["iri"] or _BAD_IRI.search(value):
        return None
    if networks and _NETWORK_IRI.match(value):
        return value
    parts = urlparse(value)
    if parts.scheme in ("http", "https") and parts.netloc:
        return value
    return None


def _norm(term: Any) -> Any:
    """`http://schema.org/x` is read as `https://schema.org/x`."""
    if isinstance(term, URIRef) and str(term).startswith(SCHEMA_HTTP):
        return URIRef(SCHEMA + str(term)[len(SCHEMA_HTTP):])
    return term


def _text(value: Any, cap: int) -> Optional[str]:
    if not isinstance(value, Literal):
        return None
    out = str(value).strip()
    return out[:cap] if out else None


def _number(value: Any) -> Optional[float]:
    if not isinstance(value, Literal):
        return None
    try:
        n = float(str(value).strip())
    except ValueError:
        return None
    return n if n == n and abs(n) != float("inf") else None


class _View:
    """The graph read through the schema.org namespace fix."""

    def __init__(self, graph: Graph):
        self.triples: list[tuple[Any, Any, Any]] = [(s, _norm(p), _norm(o)) for s, p, o in graph]

    def objects(self, subject: Any, predicate: str) -> list[Any]:
        p = URIRef(predicate)
        return [o for s, pp, o in self.triples if s == subject and pp == p]

    def one(self, subject: Any, predicate: str) -> Any:
        found = self.objects(subject, predicate)
        return found[0] if found else None

    def subjects_of_type(self, *types: str) -> list[Any]:
        wanted = {URIRef(t) for t in types}
        seen: list[Any] = []
        for s, p, o in self.triples:
            if p == RDF.type and o in wanted and isinstance(s, URIRef) and s not in seen:
                seen.append(s)
        return seen


def _pick_subject(view: _View, base_url: str) -> tuple[Optional[Any], Optional[ParsedSpace]]:
    typed = view.subjects_of_type(MOM + "Space", SCHEMA + "Place")
    if len(typed) == 1:
        return typed[0], None
    doc = urldefrag(base_url)[0]
    own = URIRef(doc + "#space")
    if len(typed) > 1:
        if own in typed:
            return own, None
        return None, _fail("several_spaces", "The file describes more than one space; the map reads one space per file.")
    if view.objects(own, SCHEMA + "name"):
        return own, None
    named = []
    for s, p, o in view.triples:
        if p == URIRef(SCHEMA + "name") and isinstance(s, URIRef) and s not in named:
            named.append(s)
    if len(named) == 1:
        return named[0], None
    return None, _fail("no_space", "No space found in the file: expected a node typed mom:Space or schema:Place with a schema:name.")


def _address(view: _View, subject: Any, fields: dict[str, Any]) -> None:
    node = view.one(subject, SCHEMA + "address")
    if node is None or isinstance(node, Literal):
        return
    street = _text(view.one(node, SCHEMA + "streetAddress"), _CAPS["street"])
    postcode = _text(view.one(node, SCHEMA + "postalCode"), _CAPS["postcode"])
    city = _text(view.one(node, SCHEMA + "addressLocality"), _CAPS["city"])
    country = _text(view.one(node, SCHEMA + "addressCountry"), 60)
    # The string the JSON path writes: "<street>, <postcode> <city>, <CC>" (parse_locality_from_free_address reads it).
    locality = " ".join(p for p in (postcode, city) if p)
    composed = ", ".join(p for p in (street, locality, country) if p)
    if composed:
        fields["mom:address"] = composed
    if city:
        fields["schema:addressLocality"] = city
    if country and _COUNTRY.match(country):
        fields["mom:countryCode"] = country.upper()


def _geo(view: _View, subject: Any, fields: dict[str, Any]) -> None:
    node = view.one(subject, SCHEMA + "geo")
    if node is None or isinstance(node, Literal):
        return
    lat = _number(view.one(node, SCHEMA + "latitude"))
    lon = _number(view.one(node, SCHEMA + "longitude"))
    if lat is not None and lon is not None and abs(lat) <= 90 and abs(lon) <= 180:
        fields["schema:geo"] = {"lat": lat, "lon": lon}


def _iri_field(view: _View, subject: Any, predicate: str) -> Optional[str]:
    o = view.one(subject, predicate)
    raw = str(o) if isinstance(o, (URIRef, Literal)) else ""
    return safe_iri(raw.strip())


def _member_of(view: _View, subject: Any) -> list[str]:
    out: list[str] = []
    for o in view.objects(subject, MOM + "memberOf"):
        raw = str(o).strip()
        if isinstance(o, Literal) and raw and ":" not in raw:
            raw = f"urn:mak:network/{raw.lower()}"  # the JSON path's slug rule
        ok = safe_iri(raw, networks=True)
        if ok and ok not in out:
            out.append(ok)
    return sorted(out)  # a graph has no order; the written statements should not depend on it


def _contact(view: _View, subject: Any) -> dict[str, str]:
    out: dict[str, str] = {}
    email = _text(view.one(subject, SCHEMA + "email"), _CAPS["contact"])
    if email:
        out["email"] = email
    for node in view.objects(subject, SCHEMA + "contactPoint"):
        if isinstance(node, Literal):
            continue
        kind = _text(view.one(node, SCHEMA + "contactType"), 40)
        url = view.one(node, SCHEMA + "url")
        if kind and kind.lower() == "matrix" and isinstance(url, (URIRef, Literal)):
            room = str(url).strip()
            marker = "matrix.to/#/"
            if marker in room:
                room = unquote(room.split(marker, 1)[1])[: _CAPS["contact"]]
                if room and not _BAD_IRI.search(room):
                    out["matrix"] = room
                    break
    return out


def parse_space_turtle(text: str, base_url: str) -> ParsedSpace:
    """Read `text` (Turtle) fetched from `base_url`. `fields` may lack a name or coordinates: the caller reports that, as for JSON."""
    graph = Graph()
    try:
        graph.parse(data=text, format="turtle", publicID=urldefrag(base_url)[0])
    except Exception as exc:  # rdflib raises BadSyntax, ValueError, ...: all mean "not Turtle we can read"
        detail = str(exc).strip().splitlines()[0][:200] if str(exc).strip() else exc.__class__.__name__
        return _fail("invalid_turtle", f"Invalid Turtle: {detail}")
    if len(graph) > MAX_TRIPLES:
        return _fail("too_large", f"The file holds {len(graph)} statements; the map reads up to {MAX_TRIPLES}.")

    view = _View(graph)
    subject, failure = _pick_subject(view, base_url)
    if failure:
        return failure

    fields: dict[str, Any] = {}
    name = _text(view.one(subject, SCHEMA + "name"), _CAPS["name"])
    if name:
        fields["schema:name"] = name
    _geo(view, subject, fields)
    _address(view, subject, fields)
    for curie, predicate, cap in (("schema:description", SCHEMA + "description", _CAPS["description"]),
                                  ("schema:openingHours", SCHEMA + "openingHours", _CAPS["hours"])):
        value = _text(view.one(subject, predicate), cap)
        if value:
            fields[curie] = value
    for curie, predicate in (("schema:url", SCHEMA + "url"), ("schema:logo", SCHEMA + "logo")):
        iri = _iri_field(view, subject, predicate)
        if iri:
            fields[curie] = iri
    members = _member_of(view, subject)
    if members:
        fields["mom:memberOf"] = members
    return ParsedSpace(fields=fields, contact=_contact(view, subject))
