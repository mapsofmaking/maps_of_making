# Story 14.5: Tile B, Self-Host Door — The File, the Walkthrough, Honest Limits

Status: backlog — small; depends on 14.1, 14.2

## Story

As a space coordinator who wants to host the file myself,
I want the file and a short way to put it online,
So that I'm on the map without an account here, and I know what that choice leaves to me.

## Acceptance Criteria

### AC1 — The file
**Then** the door shows the space's JSON (genjson export) with a copy button. No download link: copy is
what works everywhere, and genjson's Export stays available in tile A.

### AC2 — The walkthrough
**Then** Bernard's GitLab walkthrough (Story 9.8 copy) follows, and its last beat registers the raw URL
on the map itself: step 2 reads "Register on the map using its address", and one button, "Bring me back on
the map →", opens mapsofmaking.org on its "Add your space" drawer, where the address is pasted (the normal
path, `/api/register-url`). Tile B is done when the map has registered the URL (storyboard B3, 2026-10-30)
**And** this door stays `.json` (common, SpaceAPI-shaped); only the pod door writes Turtle.

### AC3 — Honest limits, never a nag
**Given** the self-host branch
**When** the coordinator opens a tile that needs a pod (`onb:needsPod`)
**Then** Bernard says what it needs ("That one needs a pod I can reach with your permission. A file on
GitLab can't hold it. Your call.") and offers the pod door once, as a plain button
**And** the word "pod" does not unlock on this branch.

## Dev Notes
- Self-direction is the point: this door must stay as easy as the other. Review copy against bible §3
  (never rank the user's choices) before merge.
