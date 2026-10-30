# The hex view — where each tile sits, and why

> "What you can do" in the home app (`home.mapsofmaking.org`, Epic 14): one hex
> per thing a space coordinator can do, revealed as they go. This document is
> the one to open before adding a tile, so the new one lands where the rest of
> the view says it should.
>
> Rules approved 2026-10-30, read back from the tile tree drawn on the "Onboard
> Storyboard" canvas. The app is not built yet; the tree is.

## Where the positions live

Every tile is a subject in `onboarding.ttl` (mom-home repo, `public/`). Its place is two axial
hex coordinates written by hand:

```turtle
:change a onb:Tile ;
  onb:q 2 ; onb:r -1 ;          # column 2, one step up
  onb:requiresAll :keep ;
```

On screen, `x = q + r/2` and `y = r` (in hex units). Nothing computes these:
the app reads them and draws. Which tiles show (done, open, coming, fog) is
computed from `onb:requiresAll` / `onb:requiresAny` and what the pod already
holds; *where* they show is not.

## Three loose rules

1. **Left to right is how far along you are.** Column 0 is "Describe your
   space", column 1 "Publish it", then the first workbench tiles (2), the
   deeper ones (3), and the tiles that only open once people start doing them
   (4).
2. **Three bands, by what the tile is about.**
   - **Up: your file works for you.** Update it once → Let it answer for you
     → Answer where people talk; Show up on another map → Bridge two maps.
   - **Middle: your network.** Join your network → Find your peers → Help a
     space join.
   - **Down: life in your space.** Post an event, Share your events, Hand over
     the space.
3. **A tile touches what it needs** (at least one of its requirements). Open
   a tile and the fog next to it clears: the view reads as growing out of
   what you just did. "Share your events" touches both of its requirements
   (Join your network, Post an event); "Bridge two maps" touches one of its
   two (Another map).

The rules are loose on purpose. Two tiles break rule 3 today, each two hexes
from what it needs, because the band mattered more:

| Tile | Needs | Sits |
|---|---|---|
| Show up on another map | Publish it | up band, column 3 |
| Hand over the space | Publish it | down band, under Post an event |

## Adding a tile

1. Pick its band from what it is about, not from what it needs.
2. Put it at the outer edge of that band, touching at least one tile it
   requires. A hex has six sides, so each band can keep widening outward.
3. If it can't touch a requirement, say why in a comment on the tile.
4. It first shows as fog, and the folded row's "+ N to discover" counts it:
   that count is also where new features appear as they are built.

## Why by hand, not computed

A layout computed from the requirements (depth = longest path, lane = band)
would move existing tiles every time one is added. People find their tiles by
place as much as by name, so a tile, once placed, stays put. The cost is a
check nobody runs yet; a small validator would do it: no two tiles on one
hex, every tile touching a requirement or carrying its exception, every tile
in a band (that needs an `onb:lane` value, not in the tree yet).

## See also

- [`mapsofmaking/mom-home`](https://github.com/mapsofmaking/mom-home) `public/onboarding.ttl` — the tree: positions, requirements, cues, Bernard's lines, words, pictos (`onb:icon`)
- Stories 14.1 (AC3 fog rules, AC7 the hex view as drawn) in `_bmad-output/implementation-artifacts/`
- The Maps of Making design system, Workbench group: `HexTile`, `HexRow`, `TilePicto`
