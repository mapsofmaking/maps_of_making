"""Fetch a space file and say what it is: JSON, Turtle, or neither (Story 14.7).

One place for what register (`main._fetch_and_validate`) and the heartbeat
(`pipeline.fetch_snapshot`) both need, so the two cannot drift:

- the request asks for Turtle first (a CSS pod would otherwise answer with
  full-IRI JSON-LD that the JSON path cannot read), JSON after;
- the answer is told apart by its Content-Type, and by its content when the
  server is vague: GitLab and GitHub raw serve `.json` and `.ttl` both as
  text/plain, and the self-host door (14.5) relies on that, so an unknown type
  is sniffed (JSON first, then Turtle), never refused for its label;
- a page that is neither (HTML, an error page) is refused with the media type
  the server actually sent;
- what is read is capped, and Turtle is parsed off the event loop.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import httpx

_scripts_dir = os.environ.get("SCRIPTS_DIR") or str(Path(__file__).resolve().parents[2] / "scripts")
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)

from spaceapi_extract.turtle import ParsedSpace, parse_space_turtle  # noqa: E402

ACCEPT = "text/turtle, application/ld+json;q=0.9, application/json;q=0.8"
MAX_FETCH_BYTES = 2 * 1024 * 1024
MAX_TURTLE_BYTES = 1024 * 1024

JSON_TYPE = "application/json"
TURTLE_TYPE = "text/turtle"

_TURTLE_TYPES = {"text/turtle", "application/x-turtle"}
_JSON_TYPES = {"application/json", "application/ld+json", "text/json"}
_REFUSED_TYPES = {"text/html", "application/xhtml+xml", "application/pdf", "application/zip"}
_REFUSED_PREFIXES = ("image/", "audio/", "video/", "font/")


@dataclass
class Source:
    """What a response turned out to be.

    kind: `json` | `turtle` (usable), or `invalid_json` | `turtle_error` | `refused` | `too_large` (not, see `error`).
    media_type: what it is (`application/json`, `text/turtle`); `sent`: what the server said it was.
    """

    kind: str
    media_type: str
    sent: str = ""
    text: str = ""
    data: Any = None
    turtle: Optional[ParsedSpace] = None
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.kind in ("json", "turtle")


@dataclass
class Fetched:
    status_code: int
    headers: httpx.Headers
    source: Optional[Source]  # None unless the status was 200


def _sent(content_type: Optional[str]) -> str:
    return (content_type or "").split(";")[0].strip().lower()


def _label(sent: str) -> str:
    return sent or "no content type"


def _json(body: bytes, sent: str, strict: bool) -> Source:
    try:
        return Source("json", JSON_TYPE, sent, data=json.loads(body))
    except json.JSONDecodeError as exc:
        detail = f"Invalid JSON at line {exc.lineno} col {exc.colno}: {exc.msg}"
    except ValueError as exc:
        detail = f"Invalid JSON: {exc.__class__.__name__}"
    if strict:
        return Source("invalid_json", JSON_TYPE, sent, error=detail)
    raise ValueError(detail)


def _turtle(text: str, size: int, sent: str, url: str) -> Source:
    if size > MAX_TURTLE_BYTES:
        return Source("turtle_error", TURTLE_TYPE, sent, error=f"The Turtle file is {size // 1024} KiB; the map reads up to {MAX_TURTLE_BYTES // 1024} KiB.")
    parsed = parse_space_turtle(text, url)
    if parsed.error:
        return Source("turtle_error", TURTLE_TYPE, sent, text=text, turtle=parsed, error=parsed.error)
    return Source("turtle", TURTLE_TYPE, sent, text=text, turtle=parsed)


def read_source(content_type: Optional[str], body: bytes, url: str) -> Source:
    """Tell what `body` is. Pure and synchronous (the Turtle parse is CPU work): call it off the event loop."""
    sent = _sent(content_type)
    if sent in _REFUSED_TYPES or sent.startswith(_REFUSED_PREFIXES):
        return Source("refused", sent, sent, error=f"The server sent {_label(sent)}; the map reads JSON or Turtle.")
    text = body.decode("utf-8-sig", errors="replace")
    if sent in _TURTLE_TYPES:
        return _turtle(text, len(body), sent, url)
    if sent in _JSON_TYPES or sent.endswith("+json"):
        return _json(body, sent, strict=True)

    # The server did not say (text/plain, octet-stream, nothing): look at the content.
    if not text.strip():
        return Source("refused", sent, sent, error=f"The server sent an empty answer ({_label(sent)}); the map reads JSON or Turtle.")
    if text.lstrip().startswith("<"):
        return Source("refused", sent, sent, error=f"The server sent {_label(sent)} that looks like a web page; the map reads JSON or Turtle.")
    try:
        return _json(body, sent, strict=False)
    except ValueError:
        pass
    turtle = _turtle(text, len(body), sent, url)
    if turtle.kind == "turtle" or (turtle.turtle and turtle.turtle.error_code != "invalid_turtle"):
        return turtle  # readable Turtle, or Turtle with a clear reason (no space, several, too many statements)
    return Source("refused", sent, sent, error=f"The response is neither JSON nor Turtle (the server sent {_label(sent)}).")


async def fetch_source(client: httpx.AsyncClient, url: str) -> Fetched:
    """GET `url` as Turtle-or-JSON and say what came back. Network errors propagate (the caller owns them)."""
    async with client.stream("GET", url, headers={"Accept": ACCEPT}) as resp:
        if resp.status_code != 200:
            return Fetched(resp.status_code, resp.headers, None)
        sent = _sent(resp.headers.get("content-type"))
        body = bytearray()
        async for chunk in resp.aiter_bytes():
            body.extend(chunk)
            if len(body) > MAX_FETCH_BYTES:
                msg = f"The file is over {MAX_FETCH_BYTES // 1024 // 1024} MiB; the map reads smaller files."
                return Fetched(200, resp.headers, Source("too_large", sent, sent, error=msg))
        headers = resp.headers
    source = await asyncio.to_thread(read_source, headers.get("content-type"), bytes(body), url)
    return Fetched(200, headers, source)


def as_spaceapi(parsed: ParsedSpace) -> dict:
    """The parsed Turtle in SpaceAPI's shape, for `classify_subset` and the validators. Never used to write the graph."""
    f = parsed.fields
    out: dict[str, Any] = {}
    if f.get("schema:name"):
        out["space"] = f["schema:name"]
    geo = f.get("schema:geo")
    if geo:
        loc = {"lat": geo["lat"], "lon": geo["lon"]}
        if f.get("mom:address"):
            loc["address"] = f["mom:address"]
        if f.get("mom:countryCode"):
            loc["country_code"] = f["mom:countryCode"]
        out["location"] = loc
    for src, dst in (("schema:url", "url"), ("schema:logo", "logo"), ("schema:description", "description"), ("schema:openingHours", "opening_hours")):
        if f.get(src):
            out[dst] = f[src]
    # SpaceAPI's contact is one value per key, of its own keys: the first email, phone and Matrix room.
    # The full list of handles stays in the snapshot for the card (snapshot_parts).
    contact: dict[str, str] = {}
    for h in parsed.contact:
        if h["type"] in ("email", "phone", "matrix") and h["type"] not in contact:
            contact[h["type"]] = h["value"]
    if contact:
        out["contact"] = contact
    return out


def snapshot_parts(source: Source) -> tuple[Any, str, Optional[str]]:
    """(payload, media_type, raw_text) for the snapshot store. JSON: its own payload, no separate text; Turtle: the fields and contact read, and the text as written."""
    if source.kind == "turtle" and source.turtle:
        return {"fields": source.turtle.fields, "contact": source.turtle.contact}, TURTLE_TYPE, source.text
    return source.data, JSON_TYPE, None
