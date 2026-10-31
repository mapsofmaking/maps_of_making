# Spike 14.0 report: account to first write (OD-2)

Status: **partial**. The protocol (three browsers, flows A/B/C) is not run yet: it needs a page on a name
same-site with `pod.mapsofmaking.org` and a Client ID Document for it. What follows was observed
without creating anything (2026-10-31).

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

## Still to run

Protocol steps 1-6 per browser (Firefox, Chrome, Safari iOS), flow A/B/C, the cookie-cleared path, and the
write of `spike.txt`.
