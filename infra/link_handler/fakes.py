"""Test doubles shared by the Story 14.7 tests: a space file served over HTTP and a fake Oxigraph."""
from __future__ import annotations

import re
from pathlib import Path

from pytest_httpserver import HTTPServer
from rdflib import Graph
from werkzeug.wrappers import Response

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "space"
TTL = (FIXTURES / "atelier-du-canal.ttl").read_text()
JSON_TEXT = (FIXTURES / "atelier-du-canal.json").read_text()


def serve(server: HTTPServer, body: str, content_type: str, path: str = "/space") -> str:
    """Serve `body` at `path` (replacing what was there) and return its URL."""
    server.clear()
    server.expect_request(path).respond_with_data(body, content_type=content_type)
    return server.url_for(path)


class FakeOxigraph:
    """Answers lookups with nothing and keeps every update it is sent."""

    def __init__(self):
        self.server = HTTPServer(host="127.0.0.1", port=0)
        self.updates: list[str] = []

    def __enter__(self):
        self.server.start()
        self.server.expect_request("/query", method="POST").respond_with_json({"results": {"bindings": []}, "boolean": False})
        self.server.expect_request("/update", method="POST").respond_with_handler(self._update)
        return self

    def _update(self, request):
        self.updates.append(request.get_data(as_text=True))
        return Response("", status=204)

    def __exit__(self, *exc):
        self.server.stop()

    @property
    def url(self) -> str:
        return self.server.url_for("").rstrip("/")


def inserted(update: str) -> Graph:
    """Every `INSERT DATA { GRAPH <g> { … } }` block of a SPARQL update, read as one graph."""
    g = Graph()
    for body in re.findall(r"INSERT DATA \{\s*GRAPH <[^>]+> \{(.*?)\}\s*\}", update, re.S):
        g.parse(data=body, format="turtle")
    return g
