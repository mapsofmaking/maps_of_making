"""Unit tests for scripts/spaceapi_extract (AC 8).

Pure functions only — no HTTP, no Oxigraph, no SPARQL execution.
"""
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from spaceapi_extract import extract_core, extract_mom, triples_for, escape_literal
from spaceapi_extract.address import parse_locality_from_free_address

# Freshness predicates that must NEVER appear in extractor output (AC 8 final bullet)
_FRESHNESS = frozenset({"mom:observedAt", "mom:updatedAt", "mom:openNow", "mom:lastOpenChange"})

_MOM_NS = "https://mapsofmaking.org/ns/mom#"
_SCHEMA_NS = "https://schema.org/"


# ── Shared test payloads ──────────────────────────────────────────────────────

def _mother_sand_payload() -> dict:
    return {
        "api": "0.13",
        "api_compatibility": "15",
        "space": "Mother Sand",
        "logo": "https://mapsofmaking.org/mother-sands-logo.png",
        "url": "https://mothersand.example.org",
        "location": {
            "lat": 51.65,
            "lon": 1.7,
            "address": "Maunsell Fort, North Sea",
            "country_code": "sol-3",
            "timezone": "UTC+0",
        },
        "contact": {
            "email": "bernard@mothersand.example.org",
            "irc": "#mothersand",
        },
        "state": {"open": False, "lastchange": 1715000000},
        "ext_mom": {"canary": True, "simulatedAge": None},
    }


def _v15_full_payload() -> dict:
    return {
        "space": "FabLab Test",
        "logo": "https://example.org/logo.png",
        "url": "https://example.org",
        "location": {
            "lat": 50.85,
            "lon": 4.35,
            "address": "123 Maker St",
            "country_code": "BE",
            "timezone": "Europe/Brussels",
        },
        "contact": {"email": "info@example.org", "twitter": "@example"},
        "description": "A test makerspace",
        "opening_hours": "Mo-Fr 18:00-22:00",
        "state": {"open": True, "lastchange": 1700000000},
        "specialties": ["3d-printing", "laser-cutting"],
    }


def _v14_minimal_payload() -> dict:
    return {
        "api": "0.13",
        "space": "Legacy Space",
        "url": "https://legacy.example.org",
        "location": {"lat": 48.85, "lon": 2.35},
    }


# ── escape_literal ────────────────────────────────────────────────────────────

def test_escape_literal_wraps_in_quotes():
    assert escape_literal("hello") == '"hello"'


def test_escape_literal_escapes_double_quote():
    assert escape_literal('say "hi"') == '"say \\"hi\\""'


def test_escape_literal_escapes_newline():
    assert escape_literal("line1\nline2") == '"line1\\nline2"'


def test_escape_literal_escapes_backslash():
    assert escape_literal("back\\slash") == '"back\\\\slash"'


# ── extract_core: Mother Sand ────────────────────────────────────────────────

def test_extract_core_mother_sand_name():
    assert extract_core(_mother_sand_payload())["schema:name"] == "Mother Sand"


def test_extract_core_mother_sand_geo():
    geo = extract_core(_mother_sand_payload())["schema:geo"]
    assert geo == {"lat": 51.65, "lon": 1.7}


def test_extract_core_mother_sand_url():
    assert extract_core(_mother_sand_payload())["schema:url"] == "https://mothersand.example.org"


def test_extract_core_mother_sand_logo():
    assert extract_core(_mother_sand_payload())["schema:logo"] == "https://mapsofmaking.org/mother-sands-logo.png"


def test_extract_core_mother_sand_contact_json():
    cj = extract_core(_mother_sand_payload()).get("schema:contactJson", "")
    assert "bernard@mothersand.example.org" in cj


# ── extract_mom: Mother Sand ─────────────────────────────────────────────────

def test_extract_mom_mother_sand_address():
    assert extract_mom(_mother_sand_payload())["mom:address"] == "Maunsell Fort, North Sea"


def test_extract_mom_mother_sand_country_code():
    assert extract_mom(_mother_sand_payload())["mom:countryCode"] == "sol-3"


def test_extract_mom_mother_sand_timezone():
    assert extract_mom(_mother_sand_payload())["mom:timeZone"] == "UTC+0"


# ── extract_core: v15 full ────────────────────────────────────────────────────

def test_extract_core_v15_all_fields():
    f = extract_core(_v15_full_payload())
    assert f.get("schema:name") == "FabLab Test"
    assert f.get("schema:url") == "https://example.org"
    assert f.get("schema:logo") == "https://example.org/logo.png"
    assert f.get("schema:description") == "A test makerspace"
    assert f.get("schema:openingHours") == "Mo-Fr 18:00-22:00"
    assert set(f.get("schema:knowsAbout", [])) == {"3d-printing", "laser-cutting"}


def test_extract_mom_v15_all_fields():
    f = extract_mom(_v15_full_payload())
    assert f.get("mom:address") == "123 Maker St"
    assert f.get("mom:countryCode") == "BE"
    assert f.get("mom:timeZone") == "Europe/Brussels"


# ── extract_core: v14 minimal ─────────────────────────────────────────────────

def test_extract_core_v14_minimal():
    f = extract_core(_v14_minimal_payload())
    assert f.get("schema:name") == "Legacy Space"
    assert f.get("schema:url") == "https://legacy.example.org"
    assert "schema:description" not in f
    assert "schema:openingHours" not in f
    assert "schema:knowsAbout" not in f


def test_extract_mom_v14_minimal_no_location_fields():
    f = extract_mom(_v14_minimal_payload())
    assert "mom:address" not in f
    assert "mom:countryCode" not in f
    assert "mom:timeZone" not in f


# ── Empty / missing optional fields → no None values ──────────────────────────

def test_extract_core_no_none_values():
    f = extract_core({"space": "Minimal", "location": {"lat": 0.0, "lon": 0.0}})
    assert all(v is not None for v in f.values())


def test_extract_mom_no_none_values():
    f = extract_mom({"location": {"country_code": "DE", "timezone": "Europe/Berlin"}})
    assert all(v is not None for v in f.values())


def test_extract_mom_empty_payload():
    f = extract_mom({})
    assert not f


# ── Freshness predicates NEVER in extractor output (AC 8 final bullet) ────────

@pytest.mark.parametrize("payload_fn", [
    _mother_sand_payload, _v15_full_payload, _v14_minimal_payload,
])
def test_freshness_predicates_absent_from_extractors(payload_fn):
    p = payload_fn()
    all_keys = set(extract_core(p)) | set(extract_mom(p))
    leaked = all_keys & _FRESHNESS
    assert not leaked, f"Freshness predicates leaked into extractor output: {leaked}"


# ── triples_for type awareness ────────────────────────────────────────────────

def test_triples_for_plain_literal():
    t = triples_for("urn:test", {"schema:name": "My Space"})
    assert len(t) == 1
    assert f"<{_SCHEMA_NS}name>" in t[0]
    assert '"My Space"' in t[0]


def test_triples_for_iri_for_url():
    t = triples_for("urn:test", {"schema:url": "https://example.org"})
    assert len(t) == 1
    assert "<https://example.org>" in t[0]
    assert '"https://' not in t[0]


def test_triples_for_iri_for_logo():
    t = triples_for("urn:test", {"schema:logo": "https://example.org/logo.png"})
    assert len(t) == 1
    assert "<https://example.org/logo.png>" in t[0]


def test_triples_for_blank_node_for_geo():
    t = triples_for("urn:test", {"schema:geo": {"lat": 51.5, "lon": 4.0}})
    assert len(t) == 1
    assert "51.5" in t[0]
    assert "4.0" in t[0]
    assert f"<{_SCHEMA_NS}latitude>" in t[0]
    assert f"<{_SCHEMA_NS}longitude>" in t[0]


def test_triples_for_multi_value_knowsabout():
    t = triples_for("urn:test", {"schema:knowsAbout": ["3d-printing", "laser-cutting"]})
    assert len(t) == 2
    assert all(f"<{_SCHEMA_NS}knowsAbout>" in tr for tr in t)


def test_triples_for_boolean():
    t = triples_for("urn:test", {"mom:openNow": True})
    assert len(t) == 1
    assert "XMLSchema#boolean" in t[0]
    assert '"true"' in t[0]


def test_triples_for_datetime():
    iso = "2026-05-22T10:00:00Z"
    t = triples_for("urn:test", {"mom:lastOpenChange": iso})
    assert len(t) == 1
    assert "XMLSchema#dateTime" in t[0]
    assert iso in t[0]


def test_triples_for_skips_none():
    t = triples_for("urn:test", {"schema:name": "X", "schema:description": None})
    assert len(t) == 1


def test_triples_for_empty_geo_skipped():
    t = triples_for("urn:test", {"schema:geo": {}})
    assert t == []


# ── Round-trip: Mother Sand through full extractor + triples_for ─────────────

def test_mother_sand_round_trip_address_and_country():
    p = _mother_sand_payload()
    core = extract_core(p)
    mom = extract_mom(p)
    all_triples = triples_for("urn:mak:canary/mother-sands", core) + \
                  triples_for("urn:mak:canary/mother-sands", mom)
    triple_str = "\n".join(all_triples)
    assert "Maunsell Fort, North Sea" in triple_str
    assert "sol-3" in triple_str
    assert "UTC+0" in triple_str
    assert "Mother Sand" in triple_str


# ── parse_locality_from_free_address (city/tag search fix, project_spaceapi_missing_locality_knowsabout) ──

def test_parse_locality_three_segment_address():
    city, postcode, country = parse_locality_from_free_address("Forchheimer Str. 2, 91083 Baiersdorf, DE")
    assert city == "Baiersdorf"
    assert postcode == "91083"
    assert country == "DE"


def test_parse_locality_nl_glued_postcode():
    city, postcode, country = parse_locality_from_free_address("Some St 1, 1217EH Hilversum, NL")
    assert city == "Hilversum"
    assert postcode == "1217EH"
    assert country == "NL"


def test_parse_locality_two_segment_address():
    city, postcode, country = parse_locality_from_free_address("9052 Zwijnaarde, Belgium")
    assert city == "Zwijnaarde"
    assert postcode == "9052"
    assert country is None


def test_parse_locality_single_segment_no_comma_unparseable():
    city, postcode, country = parse_locality_from_free_address("Maunsell Fort North Sea")
    assert (city, postcode, country) == (None, None, None)


def test_parse_locality_non_string_input_returns_all_none():
    assert parse_locality_from_free_address(None) == (None, None, None)


# ── extract_mom: schema:addressLocality derived from free-text address ────────

def test_extract_mom_derives_address_locality_from_baiersdorf_style_address():
    payload = {"location": {"lat": 49.65, "lon": 11.03, "address": "Forchheimer Str. 2, 91083 Baiersdorf, DE"}}
    assert extract_mom(payload)["schema:addressLocality"] == "Baiersdorf"


def test_extract_mom_no_address_locality_when_address_absent():
    payload = {"location": {"lat": 49.65, "lon": 11.03}}
    assert "schema:addressLocality" not in extract_mom(payload)
