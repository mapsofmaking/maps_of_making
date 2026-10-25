"""Checks the ontology: every Turtle file parses, the JSON-LD context parses,
and no IRI uses the old namespace (nicolasdb.github.io, which never resolved).
Run: python scripts/check.py   (needs rdflib)"""
import json
import pathlib
import sys

from rdflib import Graph

ROOT = pathlib.Path(__file__).resolve().parent.parent
OLD = "nicolasdb.github.io/mapsofmaking_ontology"
failed = False

for ttl in sorted(ROOT.rglob("*.ttl")):
    rel = ttl.relative_to(ROOT)
    try:
        n = len(Graph().parse(ttl, format="turtle"))
        print(f"ok   {rel}: {n} triples")
    except Exception as e:  # noqa: BLE001 - report every broken file, then fail
        print(f"FAIL {rel}: {e}")
        failed = True

for ctx in sorted(ROOT.rglob("*.jsonld")):
    rel = ctx.relative_to(ROOT)
    try:
        json.loads(ctx.read_text())
        print(f"ok   {rel}: valid JSON")
    except ValueError as e:
        print(f"FAIL {rel}: {e}")
        failed = True

for f in sorted(ROOT.rglob("*")):
    if f.is_file() and ".git" not in f.parts and f.suffix in {".ttl", ".jsonld", ".csv"}:
        for i, line in enumerate(f.read_text().splitlines(), 1):
            # The one allowed mention is the comment that records the move.
            if OLD in line and not line.lstrip().startswith("#"):
                print(f"FAIL {f.relative_to(ROOT)}:{i}: old namespace: {line.strip()}")
                failed = True

sys.exit(1 if failed else 0)
