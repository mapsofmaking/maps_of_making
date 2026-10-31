# People and spaces — who signs in, and what they act on

> The home app (`home.mapsofmaking.org`, Epic 14) is signed into by a WebID.
> That WebID is not always a space. This document is the one to open before
> anything reads or writes "the space" or "what is done": it says which of the
> two each thing belongs to, and which paths the app keeps open.
>
> Decided with Nicolas, 2026-10-31, while building Story 14.1 (S6). Most of
> the relations below are not built; the app is shaped so none of them is
> closed off.

## Two kinds of signer

Whoever signs in is one of:

- **a space's own account.** "Publish it" (14.3) creates a pod for the
  space, and its account follows the space's role mailbox, so a handover
  (the last tile) passes it on without anything breaking.
- **a person.** Their own pod, their own profile. A person may coordinate one
  space, several, or none yet; be a member of spaces, collectives and
  networks; sit on a network's board for a space.

The app never assumes the WebID *is* the space. That one assumption would
close every path below.

## Two kinds of state

| State | Belongs to | Lives in |
|---|---|---|
| The hex panel's fold, the tutorials seen | **the person signed in**: it is what they have learned | `settings/mom-home.ttl` in the signer's own pod ([reference](../reference/home-settings-file.md)) |
| What is done (published, hours updated, joined…) | **a space** | the space's own data, read each time, never stored as progress |

Settings follow the person, done follows a space. A tutorial seen once is
seen for every space that person works on; a space's progress is the same
whoever looks at it.

**Done needs a space as input.** Every done check (`src/tiles/done.ts` in
mom-home) takes the space being worked on: the IRI of its card, registered
as a `mom:Space` instance in a Type Index. Having a pod proves nothing about a
space: a person's pod has storage too. (S6 first counted "Publish it" as done
for any pod; corrected the same day.) Until the lookup exists (14.3/14.4),
no space is found and nothing counts as done.

## The relations, kept open

None of these is built. Each is a separate relation, with the vocabulary the
rest of the stack already uses (solid-kit ADR 006: membership is a handshake
read from both sides; `acl:delegates` for acting on someone's behalf):

| Relation | Shape | Example |
|---|---|---|
| **Membership** | `org:memberOf`, declared by the member and recognised by the organisation: a handshake | a person is a member of a space, a collective, a network; a space is a member of several networks |
| **A role in a membership** | `org:Membership` with `org:member`, `org:organization`, `org:role` (W3C org) | a person is a member of a space *as its coordinator* |
| **Representation** | a membership in a network whose role is the board, held *for* a space | a coordinator sits on the network's board as the space's representative |
| **Delegation** | `acl:delegates` in the space's profile, as for agents | the space lets its coordinator act for it |

**Coordinating is a role, not membership.** Being a member says who you
belong to; a role says what you do there. A role may later open more tools
in the workbench. What a person may actually change is decided by the
space's pod (its access rules), never by a role written in a profile: the
app reads roles to know what to show, the pod decides what is allowed.

**A person's own data stays theirs.** A profile may carry a place, as coarse
as the person chooses (a city, a country). People don't have a place on the
map. A space's member count, if it is ever shown, is a **sum** of recognised
memberships, never a list of names.

## What this means for the app

- **Several spaces per person** is a picker in the header ("Signed in as
  Nicolas · Atelier du Canal ▾"), not a rewrite: settings already follow the
  person and done already takes the space.
- **A space in several networks** changes nothing here: memberships are in
  the space's own data, one per network.
- **A fork for another vertical** gets its own settings file: its name comes
  from the app's `SESSION_ID`.

## See also

- [Settings file](../reference/home-settings-file.md) — the terms in `settings/mom-home.ttl`
- [The hex view](home-hex-view.md) — where each tile sits
- Story 14.1 (`_bmad-output/implementation-artifacts/14-1-…`), AC4
- solid-kit ADR 006 — membership and publication by pull
