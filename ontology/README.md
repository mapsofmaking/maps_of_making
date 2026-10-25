# Maps of Making ontology

The vocabulary of the [Maps of Making](https://mapsofmaking.org) map.

| Prefix | Namespace | File |
|---|---|---|
| `mom:` | `https://mapsofmaking.org/ns/mom#` | `mom.ttl`, `sup.ttl` |
| `core:` | `https://mapsofmaking.org/ns/core#` | `core.ttl` |
| `iop:` | `https://mapsofmaking.org/ns/iop#` | `iop/iop.ttl` |
| crosswalk | `https://mapsofmaking.org/ns/crosswalks/mom-to-okw` | `crosswalks/mom-to-okw.ttl` |

Until 2026-10-25 the namespace was `https://nicolasdb.github.io/mapsofmaking_ontology/…`,
which never resolved. The map's data moved with it.

**This repository is the source of truth.** The map repo
([mapsofmaking/maps_of_making](https://github.com/mapsofmaking/maps_of_making))
carries it as a git subtree under `ontology/`: change it here first, then
`git subtree pull` there. CI checks that every file parses and that no IRI
uses the old namespace (`scripts/check.py`).
