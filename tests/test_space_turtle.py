"""Story 14.7 S1: the map reads a Turtle space file, and reads it like the JSON one.

Offline: no Oxigraph, no HTTP. The parity test is AC5: the two fixtures
(docs/reference/space-file.md's example, as Turtle and as SpaceAPI JSON) give the
same statements in the space's graph. The one difference, by decision, is
`schema:contactJson`: the JSON path keeps contact in the index, the Turtle path
leaves the contact handles in the source (they come back as `contact`, a list).
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

from spaceapi_extract import extract_core, extract_mom, kind_of, parse_space_turtle, triples_for  # noqa: E402
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
    handles = parse_space_turtle(_ttl(), URL).contact
    assert {h["type"]: h["value"] for h in handles} == contact


def test_every_handle_home_writes_reaches_the_card():
    """The contract (handles.ttl, pinned in mom-home): every kind, two of one, blank and named contact points."""
    p = parse_space_turtle((FIXTURES / "handles.ttl").read_text(), URL)
    assert p.error is None
    assert sorted((h["type"], h["value"]) for h in p.contact) == sorted([
        ("email", "contact@atelierducanal.example"), ("email", "atelier@atelierducanal.example"),
        ("phone", "+32 2 123 45 67"), ("matrix", "#atelier:matrix.org"), ("signal", "https://signal.group/#atelier"),
        ("telegram", "https://t.me/atelierducanal"), ("discord", "https://discord.gg/atelier"),
        ("discord", "https://discord.gg/repaircafe"), ("mattermost", "https://chat.example.org/atelier"),
        ("link", "https://forum.atelierducanal.example/"),
    ])
    # Contact points come in a fixed order whatever the graph's: by kind, then value.
    assert [h["type"] for h in p.contact[3:]] == ["matrix", "signal", "telegram", "discord", "discord", "mattermost", "link"]


def test_a_handle_the_map_cant_show_safely_is_left_out():
    p = _space('<#space> a mom:Space ; schema:name "Lab" ; schema:email "not an address" ; schema:telephone "call us" ;'
               ' schema:contactPoint [ schema:contactType "Discord" ; schema:url <javascript:alert(1)> ] ,'
               ' [ schema:contactType "Fax" ; schema:url <https://fax.example/> ] ,'
               ' [ schema:contactType "Telegram" ; schema:url <https://t.me/ok> ] .')
    assert p.contact == [{"type": "telegram", "value": "https://t.me/ok"}]


def test_handles_are_capped():
    points = " , ".join(f'[ schema:contactType "Link" ; schema:url <https://x.example/{i}> ]' for i in range(40))
    p = _space(f'<#space> a mom:Space ; schema:name "Lab" ; schema:contactPoint {points} .')
    assert len(p.contact) == 20


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
    assert p.contact == [{"type": "matrix", "value": "#room:matrix.org"}]  # "Phone" is not a contact-point kind: a number is schema:telephone


# ── A network (2026-11-19): mom:Network, schema:Organization; areas served, not an address ──

NETWORK_URL = "https://pod.mapsofmaking.org/maakbib/space.ttl"


def _network_json() -> dict:
    return json.loads((FIXTURES / "maakbib.json").read_text())


def test_network_parity_turtle_and_json_write_the_same_statements():
    payload = _network_json()
    from_json = {**extract_core(payload), **extract_mom(payload)}
    from_json.pop("schema:contactJson")
    parsed = parse_space_turtle((FIXTURES / "maakbib.ttl").read_text(), NETWORK_URL)
    assert parsed.error is None and parsed.kind == "network" and kind_of(payload) == "network"
    assert parsed.fields == from_json
    assert isomorphic(_graph(parsed.fields), _graph(from_json))


def test_the_network_fixture_reads_as_the_reference_doc_says():
    f = parse_space_turtle((FIXTURES / "maakbib.ttl").read_text(), NETWORK_URL).fields
    assert f["schema:name"] == "Maakbib"
    assert f["schema:geo"] == {"lat": 51.0378, "lon": 4.2406}
    assert f["schema:areaServed"] == [{"code": "BE-VLG", "name": "Flanders"}]
    assert f["mom:geolocationFidelity"] == "region"
    assert f["mom:countryCode"] == "BE"  # from its area: a network has no address
    assert "mom:address" not in f and "schema:addressLocality" not in f
    assert f["schema:url"] == "https://maakbib.be/"


def test_a_space_file_is_still_a_space():
    assert parse_space_turtle(_ttl(), URL).kind == "space"
    assert kind_of(json.loads((FIXTURES / "atelier-du-canal.json").read_text())) == "space"


def test_areas_are_iso_codes_upper_cased_sorted_and_capped():
    codes = ", ".join(f'"{c}"' for c in ["be-wal", "BE-VLG", "Flanders", "BE_BRU", "B", "NL", "BE-VLG"] + [f"F{chr(65 + i)}" for i in range(15)])
    p = _space(f'<#space> a mom:Network ; schema:name "Net" ; schema:areaServed {codes} .')
    areas = [a["code"] for a in p.fields["schema:areaServed"]]
    assert len(areas) == 10 and areas[:3] == ["BE-VLG", "BE-WAL", "FA"]
    assert "FLANDERS" not in areas and "BE_BRU" not in areas and "B" not in areas
    assert "mom:countryCode" not in p.fields  # areas in several countries: no one country


def test_an_unknown_fidelity_is_left_out():
    p = _space('<#space> a mom:Network ; schema:name "Net" ; mom:geolocationFidelity "street" .')
    assert "mom:geolocationFidelity" not in p.fields


def test_an_organization_is_read_only_when_nothing_else_is_typed():
    p = _space('<#space> a mom:Space ; schema:name "Lab" .\n<#employer> a schema:Organization ; schema:name "Corp" .')
    assert p.fields["schema:name"] == "Lab" and p.kind == "space"
    p = _space('<#space> a mom:Network, schema:Organization ; schema:name "Net" .\n<#p> a schema:Person ; schema:name "A" .')
    assert p.fields["schema:name"] == "Net" and p.kind == "network"


def test_json_network_marker_is_cleaned_like_turtle():
    payload = {"space": "Net", "mom": {"kind": "Network", "areaServed": "be-vlg", "geolocationFidelity": "REGION"}}
    f = extract_core(payload)
    assert kind_of(payload) == "network"
    assert f["schema:areaServed"] == [{"code": "BE-VLG", "name": ""}]
    assert f["mom:geolocationFidelity"] == "region" and f["mom:countryCode"] == "BE"
    assert kind_of({"space": "Lab", "mom": {"kind": "fablab"}}) == "space"


def test_area_served_is_one_node_per_area():
    out = triples_for(SUBJECT, {"schema:areaServed": [{"code": "BE-BRU", "name": ""}, {"code": "BE-VLG", "name": 'Flanders "VL"'}]})
    s = "https://schema.org/"
    assert out == [
        f'<{SUBJECT}> <{s}areaServed> [ a <{s}AdministrativeArea> ; <{s}identifier> "BE-BRU" ] .',
        f'<{SUBJECT}> <{s}areaServed> [ a <{s}AdministrativeArea> ; <{s}identifier> "BE-VLG" ; <{s}name> "Flanders \\"VL\\"" ] .',
    ]


def test_a_snapshot_stored_with_bare_codes_still_writes_area_nodes():
    """The heartbeat may write fields from a snapshot stored before areas had names."""
    s = "https://schema.org/"
    assert triples_for(SUBJECT, {"schema:areaServed": ["be-vlg", "nope"]}) == [
        f'<{SUBJECT}> <{s}areaServed> [ a <{s}AdministrativeArea> ; <{s}identifier> "BE-VLG" ] .']


def test_a_bare_area_code_is_still_read_without_a_name():
    """The first shape (2026-11-19, before areas had names): a literal code in Turtle, a string in JSON."""
    p = _space('<#space> a mom:Network ; schema:name "Net" ; schema:areaServed "be-vlg" .')
    assert p.fields["schema:areaServed"] == [{"code": "BE-VLG", "name": ""}]
    f = extract_core({"space": "Net", "mom": {"kind": "network", "areaServed": ["BE-VLG", {"code": "nl", "name": "Netherlands"}]}})
    assert f["schema:areaServed"] == [{"code": "BE-VLG", "name": ""}, {"code": "NL", "name": "Netherlands"}]


def test_areas_are_one_per_code_named_when_any_is_and_names_are_cleaned():
    body = """<#space> a mom:Network ; schema:name "Net" ;
      schema:areaServed "BE-VLG",
        [ schema:identifier "be-vlg" ; schema:name "Vlaanderen"@nl, "Flanders"@en ],
        [ schema:identifier "BE-VLG" ; schema:name "Zz" ],
        [ schema:identifier "Flanders" ; schema:name "Nope" ],
        [ schema:name "No code" ],
        [ schema:identifier "FR-IDF" ; schema:name "  Île-de-\\n France  " ],
        [ schema:identifier "DE-BY" ; schema:name "%s" ] .""" % ("B" * 300)
    areas = _space(body).fields["schema:areaServed"]
    # Flanders: three statements of one code; a name beats none, then the smaller one ("Flanders" < "Zz").
    # A name with no code is kept after the coded ones (2026-11-23); a bad code is still left out.
    assert areas == [{"code": "BE-VLG", "name": "Flanders"}, {"code": "DE-BY", "name": "B" * 200},
                     {"code": "FR-IDF", "name": "Île-de- France"}, {"code": "", "name": "No code"}]
    assert _space(body).fields.get("mom:countryCode") is None  # several countries


def test_a_json_area_list_is_cleaned_like_turtle():
    raw = [{"code": "be-wal", "name": "Wallonia"}, {"code": "BE-WAL"}, {"name": "No code"}, {"code": "BE_BRU"}, 42, "BE-VLG"]
    f = extract_core({"space": "Net", "location": {"lat": 1, "lon": 2}, "mom": {"kind": "network", "areaServed": raw}})
    assert f["schema:areaServed"] == [{"code": "BE-VLG", "name": ""}, {"code": "BE-WAL", "name": "Wallonia"},
                                      {"code": "", "name": "No code"}]
    assert f["mom:countryCode"] == "BE"  # a named area names no country


# ── #73: a pod file keeps the SDGs and the topics an import carried ─────────

def test_sdgs_and_topics_read_like_the_json_ones():
    payload = {"space": "zz Topics", "location": {"lat": 50.8, "lon": 4.3},
               "knowsAbout": ["welding", "3D printing"], "mom": {"sdgs": [9, 4, 12]}}
    from_json = {**extract_core(payload), **extract_mom(payload)}
    parsed = _space("""<#space> a mom:Space ; schema:name "zz Topics" ;
      schema:geo [ schema:latitude 50.8 ; schema:longitude 4.3 ] ;
      schema:knowsAbout "welding", "3D printing" ; mom:sdgs 9, 4, 12 .""")
    assert parsed.fields["mom:sdgs"] == [4, 9, 12]
    assert parsed.fields["schema:knowsAbout"] == ["3D printing", "welding"]
    assert isomorphic(_graph(parsed.fields), _graph(from_json))
    assert parsed.unread == []


def test_a_goal_outside_1_to_17_or_a_topic_that_is_not_text_is_left_out():
    parsed = _space("""<#space> a mom:Space ; schema:name "zz" ;
      schema:knowsAbout <https://example.org/welding>, "  ", "ok" ; mom:sdgs 0, 18, 3.5, "x", 17, 17 .""")
    assert parsed.fields["mom:sdgs"] == [17]
    assert parsed.fields["schema:knowsAbout"] == ["ok"]



def test_a_named_area_without_an_iso_code_is_kept_after_the_coded_ones():
    """2026-11-23: "Benelux", "South East Asia" have no ISO code; the name is kept, sorted after the codes."""
    from spaceapi_extract.area import clean_areas, country_of
    areas = clean_areas([{"name": "South East Asia"}, {"code": "BE", "name": "Belgium"}, {"name": "Benelux"},
                         {"name": "benelux"}, {"code": "nope", "name": "Bad"}, "Benelux", {"code": "", "name": ""}])
    assert areas == [{"code": "BE", "name": "Belgium"}, {"code": "", "name": "Benelux"}, {"code": "", "name": "South East Asia"}]
    assert country_of(areas) == "BE"
    assert country_of([{"code": "", "name": "Benelux"}]) is None


def test_a_named_area_node_is_read_and_written_without_an_identifier():
    p = _space('<#space> a mom:Network ; schema:name "Net" ; schema:areaServed [ a schema:AdministrativeArea ; schema:name "Benelux" ] .')
    assert p.fields["schema:areaServed"] == [{"code": "", "name": "Benelux"}]
    assert "mom:countryCode" not in p.fields
    s = "https://schema.org/"
    assert triples_for(SUBJECT, {"schema:areaServed": [{"code": "", "name": "Benelux"}]}) == [
        f'<{SUBJECT}> <{s}areaServed> [ a <{s}AdministrativeArea> ; <{s}name> "Benelux" ] .']
    f = extract_core({"space": "Net", "mom": {"kind": "network", "areaServed": [{"name": "South East Asia"}]}})
    assert f["schema:areaServed"] == [{"code": "", "name": "South East Asia"}]
