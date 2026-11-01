"""Story 14.7 S1: the map reads a Turtle space file, and reads it like the JSON one.

Offline: no Oxigraph, no HTTP. The parity test is AC5: the two fixtures
(docs/reference/space-file.md's example, as Turtle and as SpaceAPI JSON) give the
same statements in the space's graph. The one difference, by decision, is
`schema:contactJson`: the JSON path keeps contact in the index, the Turtle path
leaves email and Matrix in the source (they come back as `contact`).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from rdflib import Graph
from rdflib.compare import isomorphic

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "infra" / "link_handler"))

from spaceapi_extract import extract_core, extract_mom, parse_space_turtle, triples_for  # noqa: E402
from spaceapi_extract.turtle import MAX_TRIPLES, safe_iri  # noqa: E402

FIXTURES = REPO_ROOT / "tests" / "fixtures" / "space"
URL = "https://pod.mapsofmaking.org/atelier/space.ttl"
SUBJECT = "urn:mak:space/atelier-du-canal"
PREFIXES = "@prefix schema: <https://schema.org/> .\n@prefix mom: <https://mapsofmaking.org/ns/mom#> .\n"


def _ttl() -> str:
    return (FIXTURES / "atelier-du-canal.ttl").read_text()


def _json_fields() -> dict:
    payload = json.loads((FIXTURES / "atelier-du-canal.json").read_text())
    return {**extract_core(payload), **extract_mom(payload)}


def _graph(fields: dict) -> Graph:
    """What the map writes for these fields, read back as a graph."""
    g = Graph()
    g.parse(data="\n".join(triples_for(SUBJECT, fields)), format="turtle")
    return g


def _space(body: str, base: str = URL):
    return parse_space_turtle(PREFIXES + body, base)


# ── AC5: one table, held by a test ──────────────────────────────────────────

def test_parity_turtle_and_json_write_the_same_statements():
    from_json = _json_fields()
    from_json.pop("schema:contactJson")  # the one decided difference
    parsed = parse_space_turtle(_ttl(), URL)
    assert parsed.error is None
    assert parsed.fields == from_json
    assert isomorphic(_graph(parsed.fields), _graph(from_json))


def test_the_turtle_contact_is_the_json_contact():
    contact = json.loads(_json_fields()["schema:contactJson"])
    assert parse_space_turtle(_ttl(), URL).contact == contact


def test_the_fixture_reads_as_the_reference_doc_says():
    f = parse_space_turtle(_ttl(), URL).fields
    assert f["schema:name"] == "Atelier du Canal"
    assert f["schema:geo"] == {"lat": 50.8391, "lon": 4.3297}
    assert f["mom:address"] == "Rue du Canal 12, 1070 Anderlecht, BE"
    assert f["schema:addressLocality"] == "Anderlecht"
    assert f["mom:countryCode"] == "BE"
    assert f["schema:description"] == "Open workshop for repairs and prototypes."


# ── Subject, namespace, allow-list ──────────────────────────────────────────

def test_http_schema_org_is_read_as_https():
    text = ('@prefix s: <http://schema.org/> .\n<#space> a s:Place ; s:name "Lab" ; '
            's:geo [ s:latitude 1.5 ; s:longitude 2.5 ] ; s:url <https://lab.example/> .')
    p = parse_space_turtle(text, URL)
    assert p.fields["schema:name"] == "Lab"
    assert p.fields["schema:geo"] == {"lat": 1.5, "lon": 2.5}
    assert p.fields["schema:url"] == "https://lab.example/"


def test_only_the_allow_list_is_copied():
    p = _space('<#space> a mom:Space ; schema:name "Lab" ; schema:taxID "BE0123" ; schema:birthDate "1990-01-01" ;'
               ' schema:telephone "+32 1" ; <https://other.example/secret> "x" ; mom:endpointUrl <https://x.example/e> ;'
               ' mom:updatedAt "2020-01-01T00:00:00Z" .')
    assert p.fields == {"schema:name": "Lab"}


def test_a_pod_file_with_other_nodes_reads_only_the_space():
    p = _space('<#me> a schema:Person ; schema:name "A Person" .\n<#space> a mom:Space ; schema:name "Lab" .')
    assert p.fields["schema:name"] == "Lab"


def test_two_spaces_are_refused():
    p = _space('<#a> a mom:Space ; schema:name "A" .\n<#b> a mom:Space ; schema:name "B" .')
    assert p.error_code == "several_spaces" and p.fields == {}


def test_two_spaces_one_of_them_the_own_node_reads_the_own_node():
    p = _space('<#space> a mom:Space ; schema:name "Mine" .\n<#other> a mom:Space ; schema:name "Other" .')
    assert p.fields["schema:name"] == "Mine"


def test_untyped_single_named_node_is_the_space():
    p = _space('<#thing> schema:name "Lab" .')
    assert p.fields["schema:name"] == "Lab"


def test_no_space_at_all():
    p = _space('<#me> a schema:Person .')
    assert p.error_code == "no_space"


def test_invalid_turtle_says_so():
    p = parse_space_turtle("this is { not turtle", URL)
    assert p.error_code == "invalid_turtle" and p.error.startswith("Invalid Turtle")


def test_too_many_statements_are_refused():
    body = "".join(f'<#n{i}> schema:name "n{i}" .\n' for i in range(MAX_TRIPLES + 1))
    assert _space(body).error_code == "too_large"


# ── What the caller reports as for JSON: no name, no coordinates ────────────

def test_missing_name_and_coordinates_are_missing_not_errors():
    p = _space('<#space> a mom:Space ; schema:description "x" .')
    assert p.error is None and p.name is None and p.lat is None


def test_without_a_street_the_address_is_postcode_city_country():
    p = _space('<#space> a mom:Space ; schema:name "Lab" ; schema:address [ schema:postalCode "1070" ;'
               ' schema:addressLocality "Anderlecht" ; schema:addressCountry "be" ] .')
    assert p.fields["mom:address"] == "1070 Anderlecht, be"
    assert p.fields["mom:countryCode"] == "BE"


def test_a_country_name_is_not_a_country_code():
    p = _space('<#space> a mom:Space ; schema:name "Lab" ; schema:address [ schema:addressLocality "Gent" ;'
               ' schema:addressCountry "Belgium" ] .')
    assert "mom:countryCode" not in p.fields
    assert p.fields["mom:address"] == "Gent, Belgium"


@pytest.mark.parametrize("lat, lon", [("91", "4"), ("50", "181"), ("-91", "0"), ('"NaN"^^<http://www.w3.org/2001/XMLSchema#double>', "4"), ('"x"', "4")])
def test_coordinates_out_of_range_or_not_numbers_are_missing(lat, lon):
    p = _space(f'<#space> a mom:Space ; schema:name "Lab" ; schema:geo [ schema:latitude {lat} ; schema:longitude {lon} ] .')
    assert p.lat is None


def test_zero_coordinates_are_valid():
    p = _space('<#space> a mom:Space ; schema:name "Lab" ; schema:geo [ schema:latitude 0 ; schema:longitude 0 ] .')
    assert (p.lat, p.lon) == (0.0, 0.0)


def test_lengths_are_capped():
    p = _space(f'<#space> a mom:Space ; schema:name "{"n" * 1000}" ; schema:description "{"d" * 9000}" .')
    assert len(p.fields["schema:name"]) == 200 and len(p.fields["schema:description"]) == 5000


# ── Untrusted IRIs never reach a SPARQL <...> ───────────────────────────────

@pytest.mark.parametrize("iri", [
    r"https://evil.example/\u003E\u0020DROP\u0020ALL",   # ">" and spaces, as Turtle escapes
    r"https://evil.example/\u0022x",   # a quote
    r"https://evil.example/a\u007Bb",   # a brace
    "javascript:alert(1)",
    "file:///etc/passwd",
    "ftp://x.example/",
    "urn:mak:space/other",
    "https://",
])
def test_hostile_iris_are_dropped(iri):
    p = _space(f'<#space> a mom:Space ; schema:name "Lab" ; schema:url <{iri}> ; schema:logo <{iri}> ; mom:memberOf <{iri}> .')
    for key in ("schema:url", "schema:logo"):
        if key in p.fields:  # whatever is kept is a plain http(s) IRI
            assert safe_iri(p.fields[key]) == p.fields[key]
    assert "mom:memberOf" not in p.fields


def test_a_relative_iri_resolves_against_the_pod_document():
    p = _space('<#space> a mom:Space ; schema:name "Lab" ; schema:logo <logo.svg> .')
    assert p.fields["schema:logo"] == "https://pod.mapsofmaking.org/atelier/logo.svg"


def test_what_is_written_for_hostile_iris_is_one_statement_each():
    p = _space(r'<#space> a mom:Space ; schema:name "Lab" ; schema:url <https://evil.example/\u003E\u0020DROP\u0020ALL> .')
    assert len(triples_for(SUBJECT, p.fields)) == 1


def test_member_of_takes_network_iris_and_slugs():
    p = _space('<#space> a mom:Space ; schema:name "Lab" ; mom:memberOf <urn:mak:network/be>, "VOW", <https://net.example/n> .')
    assert p.fields["mom:memberOf"] == ["https://net.example/n", "urn:mak:network/be", "urn:mak:network/vow"]


def test_a_name_with_quotes_survives_as_a_literal():
    p = _space(r'<#space> a mom:Space ; schema:name "The \"Lab\" } DROP" .')
    out = triples_for(SUBJECT, p.fields)
    assert len(out) == 1 and isomorphic(_graph(p.fields), _graph({"schema:name": 'The "Lab" } DROP'}))


def test_the_matrix_room_comes_from_the_matrix_to_link():
    p = _space('<#space> a mom:Space ; schema:name "Lab" ; schema:contactPoint [ schema:contactType "matrix" ;'
               ' schema:url <https://matrix.to/#/%23room:matrix.org> ] ; schema:contactPoint [ schema:contactType "Phone" ;'
               ' schema:url <https://x.example/> ] .')
    assert p.contact == {"matrix": "#room:matrix.org"}
