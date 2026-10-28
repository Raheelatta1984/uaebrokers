# Credential storage / XSS / cookie / header review — 2026-10-28

Scope: the vulnerability class "credentials readable by JavaScript" (tokens in
`localStorage`/`sessionStorage`/IndexedDB/JS-set cookies) and the controls that make that
attack possible or survivable — XSS sinks, cookie attributes, CORS/CSRF, Content-Security-
Policy and security headers, exposed developer tooling, supply-chain pinning.

Method: the repository was scanned with the checks in
[`docs/prompts/security-credential-storage-hardening-prompt.md`](../prompts/security-credential-storage-hardening-prompt.md)
(Phase 1), the running application was probed with `curl`, and every claim below cites the
file and line it was taken from. Baseline test run before any change:
`python -m pytest tests -q` → **108 passed, 1 warning** (the known Starlette `TestClient`
deprecation warning).

## Applicability verdict

| Tier | Verdict | Why |
|---|---|---|
| **A — credential exposure fix** | **Not applicable** | There is no authentication. The only credential-like value is a per-tab reconciliation session ID (`secrets.token_urlsafe(12)`, 96 bits — `app/main.py:82`) held in a JavaScript variable (`app/static/app.js:5`, set at `:1075`) and sent as a custom `X-Session` header (`app/static/app.js:83`, `:921`). It is never written to `localStorage`, `sessionStorage`, IndexedDB, a cookie or a URL. The only `localStorage` use stores boolean UI preferences for the Quality tab under `reconiq-quality-section-preferences-v1` (`app/static/app.js:193`, `:225`), parsed inside `try/catch` and coerced with `Boolean()`. No cookies are set anywhere; no CORS middleware exists, so cross-site requests cannot carry the custom header — this is the app's incidental CSRF protection and is retained. |
| **B — defence in depth** | **Applicable** | No security headers of any kind were sent on `/`, `/api/health` or `/static/app.js` (runtime probe). No `Content-Security-Policy`, `X-Content-Type-Options`, `Referrer-Policy`, `X-Frame-Options`, `Permissions-Policy`; no `Cache-Control: no-store` on API responses that carry uploaded broker data. Swagger UI is served at `/api/docs` in every environment (`app/main.py:36`) and loads scripts from `cdn.jsdelivr.net` with an inline `<script>`. |
| **C — supply chain + regression guards** | **Applicable** | `requirements.txt` is entirely `>=` ranges with no lockfile and no hashes (`requirements.txt:1-9`); CI installs from it fresh on every run (`.github/workflows/tests.yml:19`); no dependency-audit step; no Dependabot/Renovate; GitHub Actions pinned by tag, not SHA (`.github/workflows/tests.yml:15-16`). |

## Findings

| # | Severity | Finding | Evidence | Recommended action | Tier |
|---|---|---|---|---|---|
| 1 | Info | No JWT/credential is stored in web storage; session ID lives in memory and travels in a custom header. | `app/static/app.js:5,83,193,225,921,1075`; `app/main.py:82` | None now. When real authentication arrives use `__Host-session` (HttpOnly; Secure; SameSite=Lax; Path=/) plus an `Origin` check — not web storage. Record as design guidance. | A |
| 2 | Medium | No Content-Security-Policy. A single missed escape would allow script injection *and* exfiltration (`fetch` to an attacker origin) with nothing to stop either. | runtime probe: no CSP header on any route; `app/main.py` has no middleware | Enforce `default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; font-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'`. Feasible because the app has **no inline scripts, no `eval`, and no external origins** (`app/static/index.html:385` is the only script tag; scans 1.5/1.6 empty). | B |
| 3 | Low | Three inline `style=` attributes in rendered templates block a strict `style-src`. | `app/static/app.js:654,852,878` | Move to CSS classes / CSSOM (`element.style.width`), so `style-src 'self'` can be enforced without `'unsafe-inline'`. | B |
| 4 | Low | Missing `X-Content-Type-Options`, `Referrer-Policy`, `X-Frame-Options`, `Permissions-Policy`; no HSTS in production. | runtime probe | Add centrally in one middleware; HSTS and `upgrade-insecure-requests` only when `RECONIQ_ENV=production`. | B |
| 5 | Low | API responses containing uploaded broker/insurer data (`/api/upload`, `/api/reconcile`, `/api/export/*`) carry no `Cache-Control`. | runtime probe; `app/main.py:219-237,306-425,431-470` | `Cache-Control: no-store` on every `/api/*` response. | B |
| 6 | Low | Swagger UI (`/api/docs`) is exposed in all environments and pulls third-party script from a CDN with an inline bootstrap script. | `app/main.py:36`; runtime probe lists `cdn.jsdelivr.net`, `fastapi.tiangolo.com`, 1 inline `<script>` | Serve docs only when `RECONIQ_ENV` ≠ `production`; on that dev-only route send a documented, relaxed CSP limited to the CDN origins. | B |
| 7 | Info | HTML escaping is correct everywhere today but relies on per-call-site discipline (`escapeHtml()` around each interpolation; `toast()` uses `textContent`). | `app/static/app.js:48-52`, 22 `innerHTML` sites reviewed | Add a static regression test that fails if a user-controlled field is interpolated into markup without `escapeHtml(`, and a test that the helper still escapes `& < > " '`. | B/C |
| 8 | Medium | Dependencies are unpinned ranges with no hashes; every CI run and every `./run.sh` resolves whatever is newest on PyPI (supply-chain exposure). | `requirements.txt:1-9`; `.github/workflows/tests.yml:19`; `run.sh:9` | Keep direct dependencies in `requirements.in`; compile `requirements.txt` with `pip-compile --generate-hashes` (pip enforces hash-checking automatically). | C |
| 9 | Low | No vulnerability audit in CI. | `.github/workflows/tests.yml` | Add `pip-audit --strict --require-hashes --no-deps -r requirements.txt`. | C |
| 10 | Low | No automated dependency updates. | repo root | Add `.github/dependabot.yml` for `pip` and `github-actions`. | C |
| 11 | Low | GitHub Actions pinned by mutable tag. | `.github/workflows/tests.yml:15-16` | Pin to full commit SHAs with a version comment. | C |
| 12 | Info | Session store eviction (`MAX_SESSIONS = 40`, oldest first) and unbounded upload size are fine for a local single-user demo but are denial-of-service vectors on shared hosting. | `app/main.py:33-34,67-73,230` | Out of scope for this class; recorded as a follow-up before any multi-user deployment. | — |

## Plan

Tier A: no code change. Guidance recorded in Finding 1.

Tier B:
- `app/main.py`: `RECONIQ_ENV` flag (default `development`); docs URL `None` in production;
  one `@app.middleware("http")` adding the headers above; strict CSP everywhere except the
  dev-only `/api/docs` route, which gets a relaxed policy scoped to the Swagger CDN;
  `Cache-Control: no-store` on `/api/*`; HSTS + `upgrade-insecure-requests` only in production.
- `app/static/app.js` + `app/static/styles.css`: replace the three inline `style=` attributes
  with classes / CSSOM so `style-src 'self'` holds.
- `README.md`: document `RECONIQ_ENV` and the headers.

Tier C:
- `requirements.in` (direct deps) → `requirements.txt` compiled with hashes.
- `.github/workflows/tests.yml`: SHA-pinned actions, `pip-audit` step.
- `.github/dependabot.yml`.
- `tests/test_security.py`: headers on `/`, `/api/health`, `/static/app.js`; `no-store` on
  API; production flag disables docs and enables HSTS (subprocess); no credentials in
  browser storage (regression guard); escape-helper and interpolation guards.
- Repo conventions: new entry in `reconiq/releases.json` (0.3.1), the security suite added
  to the Quality catalogue and the recorded verification snapshot refreshed
  (`reconiq/quality.py`, literal in `tests/test_api.py`).

Deferred: Finding 12 (session eviction / upload size limits) — unrelated to this class and
needs a product decision on limits.

## Verification evidence

Tests (baseline → after): `python -m pytest tests -q` → 108 passed → **121 passed, 1 warning in
3.14s** (13 new tests in `tests/test_security.py`; the warning is the pre-existing Starlette
`TestClient` deprecation). `node --check app/static/app.js` → OK.

Static re-scan after the change: zero credential-like web-storage uses, zero JS-set cookies,
zero inline `style=` attributes in `app.js`/`index.html`, zero external origins in CSS.

Dependency lock: `requirements.txt` compiled with `pip-compile --generate-hashes` (1,207 SHA-256
hashes); a fresh `python -m venv` + `pip install -r requirements.txt` succeeds in hash-checking
mode and all runtime modules import. `pip-audit --strict --require-hashes -r requirements.txt`
→ **No known vulnerabilities found**. GitHub Actions pinned to the commits the moving `v4`/`v5`
tags currently resolve to (`actions/checkout` v4.4.0 `11d5960…`, `actions/setup-python` v5.6.0
`a26af69…`), so CI behaviour is unchanged.

Runtime probe, development mode (`uvicorn app.main:app`, port 8000):

| Route | CSP | nosniff | Referrer | XFO | Permissions | Cache-Control |
|---|---|---|---|---|---|---|
| `/` | strict | ok | ok | ok | ok | — |
| `/api/health` | strict | ok | ok | ok | ok | `no-store` |
| `/static/app.js` | strict | ok | ok | ok | ok | — |
| `/api/docs` | CDN-scoped | ok | ok | ok | ok | `no-store` |

Strict policy as sent: `default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'
data:; font-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors
'none'; form-action 'self'`. End-to-end under the middleware: session → demo load → reconcile →
CSV export all `200`, reconcile and export both `Cache-Control: no-store`, KPIs unchanged
(match rate 87.2 %, 18 exceptions — the README's demo expectation).

Runtime probe, production mode (`RECONIQ_ENV=production`, port 8001): all headers above plus
`Strict-Transport-Security: max-age=31536000; includeSubDomains` and `upgrade-insecure-requests`
in the CSP; `/api/docs` → **404**; `/openapi.json` and `/api/health` → 200.

CSRF posture retained: a cross-site `POST /api/reconcile` with `Origin: https://evil.example`
and no `X-Session` header → 404, and no `Access-Control-*` header is ever emitted, so a foreign
origin can neither carry the session header without a preflight nor read a response.

Not verified: no browser automation harness exists in the repository, so CSP behaviour in a real
browser was not exercised; the policy was derived from a complete inventory of the markup
(single external `<script src>`, no inline code, no external origins) and the three inline
styles were removed, which is the only class of violation the inventory could produce.

## Deviations from the run-book

- The work was done on the session's fixed branch `arena/8ba248a4-uaebrokers` rather than a
  freshly created `security/…` branch, because the environment pins the session to that branch.
- The working tree was not clean at the start: the only untracked file was the run-book itself,
  written earlier in this session; it was committed first rather than stashed.
- Branch cleanup operated on remote refs only (no checkout of `main`), for the same reason.
