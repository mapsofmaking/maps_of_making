# Story 14.0: Spike — From Account Creation to First Write, Observed Live (OD-2)

Status: done (report: 14-0-spike-report.md)

## Story

As the person responsible for the onboarding narration (Nicolas),
I want to walk the real sequence once, on each browser, and see every page the provider shows,
So that the narration is written for the flow that actually happens, not the one we hope for.

## Question

After the home app creates an account (the same-site `css-account` cookie is set by CSS), and then
starts the Solid-OIDC sign-in, what does the coordinator see?

- **Flow A:** the consent page only ("Allow home.mapsofmaking.org to…"), then back in the app.
- **Flow B:** the login page (email + passphrase again), then consent, then back.
- **Flow C:** something else (an error, a dead end, a stock page in jargon).

## Setup

- A throwaway page on `home.mapsofmaking.org` (or a staging subdomain of `mapsofmaking.org`: it must
  be same-site with `pod.`), carrying the pocpod0 sequence (`registerAccount`: create → password → pod) and
  one Solid-OIDC login with the app's Client ID Document, then one write (`spike.txt`) to the new pod.
- Test accounts only, deleted afterwards. Instance: `pod.mapsofmaking.org` with open registration on.

## Protocol

For each of Firefox, Chrome, and Safari on iOS (Safari's tracking protection is the one most likely to
treat the cookie differently):

1. Fresh private window. Create the account from the page.
2. Record: was the cookie stored? (DevTools, or the account API answering the next call with no token.)
3. Start the sign-in. Screenshot every provider page shown, with its address bar.
4. Record the time from "Create it" to back in the app, and every word the coordinator has to read.
5. Write `spike.txt`; record the result.
6. Repeat once with the cookie cleared between creation and sign-in (a coordinator who closes the tab and
   comes back): that path must also make sense.

## Done when

- A short report in `_bmad-output/implementation-artifacts/14-0-spike-report.md`: flow observed per
  browser, screenshots, and which provider pages need their words reviewed (solid-css-overlay, ADR 009).
- Nicolas has read it against the narration and chosen the line before the redirect. Drafts, in Bernard's
  register, to start from:
  - Flow A: "One more door. It asks whether this app may write to your pod. Say yes if you mean it."
  - Flow B: "One more door. The pod asks for your passphrase again. Its door, not mine."
- Stories 14.3 and 14.4 updated with the observed flow.

## Notes
- The fetch to the account API needs `credentials: "include"`, and CSS must answer with credentialed CORS
  for the home origin. If the cookie is never stored, that is the first thing to check.
- A Flow B result is not a failure. It is one more page to write well, and the provider's own login is
  where the address bar names the server (kit ADR 010 point 3).
- Also record how to ask whether a pod name is free without creating anything (Story 14.3 AC2 checks it
  live): what a HEAD on `https://<name>.pod.mapsofmaking.org/` answers for a free and a taken name, or
  whether the account API offers a check. Note any rate limit the gateway would need for it.
