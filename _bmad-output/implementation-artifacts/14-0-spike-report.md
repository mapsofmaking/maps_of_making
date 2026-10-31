# Spike 14.0 report: account to first write (OD-2)

Status: **done** (2026-10-31). Line chosen, stories 14.3 and 14.4 updated.

Run on a throwaway instance, `pod-test.mapsofmaking.org` (solid-css-overlay 7.2.0-9, same skin as
`pod.`), because CSS 7.2 cannot delete accounts (nicolasdb/solid-css-overlay#17). The page was the
real app origin, `https://home.mapsofmaking.org/?spike` (temporary `src/spike.ts` in mom-home), signing
in with the app's real Client ID Document. Driven by Playwright 1.64.1: Chromium 156 and Firefox on the
host, WebKit in Playwright's Ubuntu image. **Safari on iOS is not verified** (no device; Playwright's
WebKit does not reproduce Safari's tracking protection).

## Result: the app chooses the flow

| Variant | Chromium | Firefox | WebKit |
|---|---|---|---|
| **login**: after creating, the app logs in through the account API (`POST controls.password.login`, `credentials: "include"`) | A: consent only, 5.3 s | A, 5.3 s | A, 7.4 s |
| **cleared**: same, cookies cleared before sign-in (tab closed, came back) | B: login, consent, 7.0 s | B, 7.3 s | B, 8.2 s |
| **nologin**: account, password, pod created with the token only (pocpod0 `registerAccount`) | B, 6.5 s | B, 6.7 s | B, 8.0 s |

Times: "Create" to `spike.txt` written (`201`). Every run wrote the file. No flow C.

- `css-account` is set on `pod-test.mapsofmaking.org` by the account-API **login**, not by account
  creation: creating with the `CSS-Account-Token` header sets nothing.
- The cross-origin call works: CSS answers the home origin with credentialed CORS
  (`access-control-allow-origin: https://home.mapsofmaking.org`, `allow-credentials: true`).
- The consent page names the app by its Client ID Document: "This app runs at **home.mapsofmaking.org**",
  "Calls itself Maps of Making home", client id `https://home.mapsofmaking.org/id.jsonld`.
- So **14.3 should log in through the account API right after creating the pod** (it holds the email and
  passphrase at that moment). Flow A for anyone who goes straight on; flow B for anyone who comes back
  later, or a browser that drops the cookie (Safari, unverified). Bernard's line has to fit both.

## Pages and their words (solid-css-overlay, ADR 009)

**Consent** (`/.account/oidc/consent/`, shown in A and B): "An app wants to use your pod. If you authorize
it, this app can read and change the data in your pod, acting as the WebID you choose below. Only authorize
apps you recognise. This app runs at home.mapsofmaking.org. Check this address: your sign-in can only go back
there." Then "Choose the WebID — your name on the web — this app will act as", one radio, "Let this app stay
signed in", **Authorize** / Cancel / Edit account / Use a different account.

**Login** (`/.account/login/password/`, B only): "Log in. Your pod is your own space on the web. Log in with
the email and password you chose when you signed up." Email, Password, Stay logged in, **Log in** / Cancel,
Create an account, Forgot your password?

To review:
- "password" here, "passphrase" in tile B (B2's form and Bernard). One word for both.
- "WebID" appears on consent long before the words strip unlocks it (peers, last tiles). The page defines it
  ("your name on the web"); fine, or the words table notes it.
- "Edit account", "Use a different account", "Create an account" are exits from the flow a newcomer does not
  need there.
- Both pages carry a theme button; MoM is Daylight only.

## Line before the redirect (chosen by Nicolas)

"— Your pod opens its own page now. If it asks for your passphrase, use the one you just made. Then press Authorize for home.mapsofmaking.org."

Decided with it: "passphrase" everywhere, the pod pages included (solid-css-overlay #27). Raised from the
consent page: agents' WebIDs listed beside the person's (solid-css-overlay #25).

## Cleanup

`src/spike.ts` removed from mom-home (`d4ea113`, deployed); `pod-test` wiped (`down -v`) and its gateway
block removed (vps-infra #4). Production `mom-pods` updated to 7.2.0-11 on the way (an `update.sh` bug,
solid-css-overlay #26).

Screenshots: scratchpad `spike/shots/` (not committed).

## Is a pod name free? (14.3 AC2)

| Probe | Result |
|---|---|
| `HEAD https://<name>.pod.mapsofmaking.org/` for a name that exists (`nicolasdb`) | `401` |
| the same for a name that cannot exist (`zz-free-name-check-914`) | `401` |
| the same for `atelier-du-canal` | `401` |
| `GET https://pod.mapsofmaking.org/.account/` controls | `password.login`, `password.forgot`, `password.reset`, `account.create`, `main.index`, `main.logins`, html `register`; **no name-availability control** |

- `*.pod.mapsofmaking.org` resolves for every name (wildcard) and the server answers `401` to every
  unauthenticated request, so **a HEAD cannot tell a free name from a taken one**.
- The account API (CSS 0.5 controls) offers no check either. The name is only tested when the pod is
  created.
- So 14.3 AC2 can't check live without creating. Options: (a) check at creation and answer "That address
  is taken" with nothing lost (the S2 frame already draws it, `sayTaken`); (b) ask the provider for a check
  endpoint (solid-css-overlay change). Rate limit: none needed for (a).

