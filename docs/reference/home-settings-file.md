# Settings file — `settings/mom-home.ttl`

> What the home app (`home.mapsofmaking.org`) keeps on the pod of whoever signs
> in, and how it writes it. Code: `src/settings/home.ts` in mom-home. Why it
> belongs to the person and not to a space:
> [People and spaces](../explanation/home-people-and-spaces.md).

## Where

| | |
|---|---|
| File | `<signer's pod root>settings/mom-home.ttl` |
| Name | the app's `SESSION_ID` (`src/config.ts`) + `.ttl`: a fork gets its own file |
| Beside it | `settings/README.md`, written once, never over one already there |
| Registered | in the private Type Index, if the profile (or its `pim:preferencesFile`) names one: `solid:forClass onb:HomeSettings` |
| Not touched | `pim:preferencesFile` itself: left to the pod |

## Terms

Namespace `onb:` = `https://mapsofmaking.org/ns/onboarding#` (draft, with the
tile tree; moves to the ontology repo once stable).

| Term | On | Value | Meaning |
|---|---|---|---|
| `onb:HomeSettings` | `<#settings>` | class | the settings of one person, for this app |
| `onb:folded` | `<#settings>` | `xsd:boolean`, absent = never set | the hex panel's fold; unset, a desktop arrives unfolded and a phone folded |
| `onb:seenTutorial` | `<#settings>` | a tile's IRI in the tree, repeated | a tile whose first open (its tutorial) was seen; the next opens go to its tool |

Never in this file: what is done. Done is read from a space's own data.

```turtle
@prefix onb: <https://mapsofmaking.org/ns/onboarding#> .
<#settings> a onb:HomeSettings ;
  onb:folded true ;
  onb:seenTutorial <https://mapsofmaking.org/onboarding/space-coordinator#change> .
```

## How it is written

| Case | Request |
|---|---|
| First write | `PUT` with `If-None-Match: *`; 412 (another tab created it) → change that one instead |
| Every change after | read with its ETag, change, `PUT` with `If-Match`; on 412 read and change again, once; a second 412 is a conflict |
| README | `PUT` with `If-None-Match: *`, after the first write; 412 = already there, left alone |
| Type Index | after the first write, one registration appended by the same conditional write, skipped if the file is already listed |

A write the pod refuses leaves the screen as chosen for this visit and says
so ("Your pod didn't take that change. It holds for this visit.").
