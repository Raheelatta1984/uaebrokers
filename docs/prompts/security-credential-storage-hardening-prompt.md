# =====================================================================================
# SECURITY HARDENING RUN — credential storage · XSS · cookies · headers · supply chain
# Paste this entire file as ONE message to a coding agent with shell + git + gh access.
# =====================================================================================

## CONFIG (edit these, then run)
DEFAULT_BRANCH=auto                 # auto = detect with gh; or e.g. main
WORK_BRANCH="security/credential-storage-hardening-$(date +%Y%m%d)"
APPLY_SCOPE=all                     # all | defence-in-depth-only | report-only
MERGE_STRATEGY=squash               # squash | merge | rebase
AUTO_MERGE=true                     # merge when checks are green; never bypass protections
BRANCH_CLEANUP_MODE=merged-only     # own-branch-only | merged-only | all-unprotected (destructive; archives tags first)
PROTECTED_BRANCH_PATTERNS="main master develop dev staging production gh-pages release/* hotfix/*"
CSP_MODE=auto                       # auto | enforce | report-only | skip
LEGACY_TOKEN_GRACE_DAYS=0           # >0 keeps accepting "Authorization: Bearer" from browsers during migration
APP_URL=""                          # optional, e.g. http://localhost:3000 — enables runtime header/cookie checks
DRY_RUN=false                       # true = analyse + diff + report only; no commit/PR/merge/delete

## YOUR ROLE
You are a senior application-security engineer working inside this repository. Detect and
remediate ONE vulnerability class end-to-end, then open, merge and clean up a PR:

  Credentials (JWTs, session tokens, API keys) readable by JavaScript — typically stored in
  localStorage / sessionStorage / IndexedDB / JS-set cookies — so a single XSS bug or a
  compromised front-end dependency can exfiltrate them; plus the controls that make that
  attack possible or survivable: XSS sinks, cookie attributes (HttpOnly, Secure, SameSite,
  __Host-), CORS/CSRF, Content-Security-Policy and security headers, exposed dev tooling,
  and supply-chain pinning.

Apply these nuances (do NOT cargo-cult "always use HttpOnly cookies"):
- HttpOnly stops token THEFT via XSS, not token USE via XSS (session riding). Preventing XSS
  (escaping + CSP) remains the primary control.
- Moving auth from a header to a cookie ADDS CSRF exposure. A cookie fix is incomplete without
  SameSite PLUS an Origin/Referer check or CSRF token on unsafe methods.
- A custom auth header (X-Session, Authorization) gives incidental CSRF protection because
  cross-site requests need a CORS preflight. Never remove it without replacing that protection.
- SameSite=Strict breaks "arrive logged-in from an external link". Default to Lax.
- credentials:"include" is only for cross-origin calls; same-origin uses the default. Never
  pair credentials with Access-Control-Allow-Origin:* or a reflected Origin.
- An in-memory JS variable beats web storage (not persistent, not cross-tab) but is still
  readable by injected script; it is not a complete fix on its own.

## GROUND RULES
1. Evidence before claims: every finding cites path:line. Every "not applicable" states what
   you searched and what you found.
2. Decide applicability BEFORE editing anything (PHASE 2 gate).
3. Minimal, conventional diffs following the repo's style, test runner, CI layout and commit
   conventions. No drive-by refactors or reformatting.
4. Never commit, print or log secret values. Never rotate secrets in code.
5. Never weaken an existing protection to make something pass: no 'unsafe-inline'/'unsafe-eval'
   in script-src, no SameSite=None without a documented cross-site need, no disabling tests,
   no relaxing CORS.
6. Never force-push, never `gh pr merge --admin`, never bypass branch protection or required
   reviews, never delete protected branches, the default branch, or branches with open PRs.
7. User-visible behaviour changes (e.g. forced re-login) go in the PR under "Behaviour change".
8. If a step's precondition fails: stop that step, record it in the final report, continue
   with whatever remains safe. Never silently skip.
9. DRY_RUN=true: run PHASES 0–4, create no commits/PRs/merges/deletions; print diff + report.

# -------------------------------------------------------------------------------------
# PHASE 0 — PREFLIGHT
# -------------------------------------------------------------------------------------
```bash
set -uo pipefail
test -z "$(git status --porcelain)" || { echo "STOP: working tree is dirty"; exit 1; }
gh auth status || { echo "STOP: gh not authenticated"; exit 1; }
[ "$DEFAULT_BRANCH" = auto ] && DEFAULT=$(gh repo view --json defaultBranchRef -q .defaultBranchRef.name) || DEFAULT="$DEFAULT_BRANCH"
gh repo view --json isFork,nameWithOwner -q '"\(.nameWithOwner) fork=\(.isFork)"'
gh api "repos/{owner}/{repo}/branches/$DEFAULT/protection" -q '{required_reviews: .required_pull_request_reviews.required_approving_review_count, checks: .required_status_checks.contexts}' 2>/dev/null || echo "no branch protection (or no permission to read it)"
git fetch --prune origin && git checkout "$DEFAULT" && git pull --ff-only && git checkout -b "$WORK_BRANCH"
```
Then run the project's existing test / lint / type-check / build commands ONCE and record the
BASELINE result (which checks pass/fail before you touch anything). If the baseline is red,
note exactly which checks fail; you may proceed, but PHASE 6 must not auto-merge unless your
PR's own CI is green and the failures are demonstrably pre-existing.
Monorepo: repeat PHASE 1 per app/package; one consolidated report and one PR unless the repo
convention says otherwise.

# -------------------------------------------------------------------------------------
# PHASE 1 — DISCOVERY (read-only; record path:line for everything)
# -------------------------------------------------------------------------------------
Define a scanner that skips vendored/built code, then run EVERY check below and keep the raw
output for the report. Use `rg` instead of `grep -r` if available (same patterns).
```bash
EXCL="--exclude-dir=node_modules --exclude-dir=.git --exclude-dir=dist --exclude-dir=build --exclude-dir=.next --exclude-dir=.nuxt --exclude-dir=.output --exclude-dir=vendor --exclude-dir=coverage --exclude-dir=.venv --exclude-dir=venv --exclude-dir=__pycache__ --exclude-dir=target --exclude-dir=out --exclude-dir=.svelte-kit"
scan() { echo "### $1"; grep -rniE $EXCL --exclude='*.lock' --exclude='*-lock.json' --exclude='*.min.js' --exclude='*.map' --exclude='*.svg' -e "$2" . || echo "(no matches)"; echo; }
```

### 1.1 Stack detection
```bash
ls -la; for f in package.json next.config.* nuxt.config.* angular.json vite.config.* svelte.config.* requirements*.txt pyproject.toml Pipfile manage.py go.mod Gemfile composer.json pom.xml build.gradle* *.csproj vercel.json netlify.toml Dockerfile docker-compose*.yml; do ls $f 2>/dev/null; done
ls .github/workflows 2>/dev/null; find . -name 'nginx*.conf' -not -path '*/node_modules/*' 2>/dev/null
grep -oE '"(react|next|vue|nuxt|@angular/core|svelte|express|fastify|koa|hapi|nestjs|@nestjs/core|next-auth|@auth/core|@clerk/[a-z-]+|@auth0/[a-z-]+|@supabase/[a-z-]+|firebase|@azure/msal-browser|jsonwebtoken|jose|passport|express-session|cookie-session|helmet|cors|csurf|csrf-csrf|redux-persist|zustand|pinia)"' package.json 2>/dev/null | sort -u
grep -iE '^(django|flask|fastapi|starlette|pyjwt|python-jose|authlib|django-csp|flask-talisman|flask-wtf|itsdangerous|fastapi-csrf-protect)' requirements*.txt pyproject.toml Pipfile 2>/dev/null
```
Classify as one or more of: browser front-end · server/API · SSR framework · mobile (RN/Expo) ·
static site · CLI/library (CLI/library = out of scope → "not applicable", still do Tier C).

### 1.2 Credentials in script-readable storage (client code)
```bash
scan "web-storage credential writes/reads" '(localStorage|sessionStorage)\.(setItem|getItem|removeItem)[[:space:]]*\([^,)]{0,40}(token|jwt|auth|session|secret|api[_-]?key|credential|refresh|id_token|access)'
scan "web-storage bracket access" '(localStorage|sessionStorage)\[[^]]{0,40}(token|jwt|auth|session)'
scan "React Native AsyncStorage" 'AsyncStorage\.(setItem|getItem|multiSet)'
scan "JS-set cookies (can never be HttpOnly)" 'document\.cookie[[:space:]]*=|Cookies\.set\(|js-cookie|universal-cookie|useCookies\('
scan "IndexedDB / localforage" 'indexedDB|localforage|idb-keyval|createStore\('
scan "Bearer built from storage" 'Bearer.{0,80}(getItem|localStorage|sessionStorage|AsyncStorage)'
scan "persisted state slices (check for auth/token slices)" 'redux-persist|persistedstate|createJSONStorage|partialize|persist\(|whitelist:|blacklist:'
scan "tokens embedded in HTML state" '__(INITIAL_STATE|PRELOADED_STATE|NEXT_DATA|NUXT|APOLLO_STATE)__'
scan "tokens in URLs" '[?&](token|access_token|id_token|jwt|session_id|sessionid|api_key|apikey)='
scan "vendor auth SDK storage config" 'cacheLocation|persistSession|setPersistence|browserLocalPersistence|indexedDBLocalPersistence|storeAuthStateInCookie|useRefreshTokens'
```
Vendor SDKs: configure, do not patch internals.
| SDK | Risky default | Preferred |
|---|---|---|
| Auth0 SPA SDK | cacheLocation:'localstorage' | cacheLocation:'memory' + useRefreshTokens + rotation, or server-side/BFF |
| Firebase Auth | IndexedDB persistence | browserSessionPersistence/inMemoryPersistence + server session cookies for SSR |
| Supabase JS | localStorage session | @supabase/ssr cookie clients for Next/SSR; otherwise document the trade-off |
| MSAL.js | sessionStorage | memoryStorage where UX allows; still script-readable → document |
| NextAuth/Auth.js, Clerk, Lucia, Django/Rails/Laravel/Spring sessions | cookie-based | verify attributes only (1.3) |

### 1.3 Cookie attributes (server code + config)
```bash
scan "cookie set sites" 'Set-Cookie|set_cookie\(|setCookie\(|res\.cookie\(|cookies\(\)\.set\(|cookieStore|http\.SetCookie\(|ResponseCookie|CookieBuilder|express-session|cookie-session|SessionMiddleware\(|SESSION_COOKIE_|CSRF_COOKIE_|session_store|server\.servlet\.session\.cookie|config/session'
scan "cookie attribute keywords (verify each auth cookie)" 'httponly|http_only|secure[[:space:]]*[:=]|samesite|same_site|https_only|__Host-|__Secure-'
```
Every cookie that authenticates requests MUST have: HttpOnly; Secure (prod; dev may relax only
over plain http); SameSite=Lax (Strict only by decision); Path=/; no Domain unless cross-subdomain
is required; __Host- prefix when Secure + Path=/ + no Domain hold; sensible Max-Age. Record
the actual attributes of each.

### 1.4 CORS and CSRF
```bash
scan "CORS config" 'cors\(|CORSMiddleware|Access-Control-Allow-Origin|allow_origins|CORS_ALLOW_ALL_ORIGINS|CORS_ORIGIN_ALLOW_ALL|CORS_ALLOWED_ORIGINS|allowedOrigins|rack-cors|origin:[[:space:]]*(true|.?\*)'
scan "credentialed CORS (High if combined with * or reflected origin)" 'allow_credentials|credentials:[[:space:]]*true|supports_credentials|allowCredentials|Access-Control-Allow-Credentials|withCredentials|credentials:[[:space:]]*.include'
scan "CSRF defences present?" 'csrf|csurf|xsrf|protect_from_forgery|VerifyCsrfToken|CsrfViewMiddleware|antiforgery|X-Requested-With|same_site|sameSite|samesite'
```
If any cookie authenticates requests, confirm at least one of: SameSite Lax/Strict AND an
Origin/Referer check on POST/PUT/PATCH/DELETE; a synchroniser or double-submit token; or a
mandatory custom header with non-permissive CORS. Record which — or "none".

### 1.5 XSS sinks (the precondition for the attack)
```bash
scan "DOM sinks" 'innerHTML|outerHTML|insertAdjacentHTML|document\.write|srcdoc|dangerouslySetInnerHTML|v-html|\[innerHTML\]|bypassSecurityTrust|trustAsHtml|\.html\(|\.(append|prepend|after|before|replaceWith)\([[:space:]]*.?<'
scan "code execution sinks" '[^a-zA-Z_.]eval\(|new Function\(|(setTimeout|setInterval)\([[:space:]]*[^a-zA-Z_(]|javascript:'
scan "server-template raw output" '\|[[:space:]]*safe\b|Markup\(|mark_safe\(|\{!!|html_safe|\braw\(|<%==|template\.HTML\(|th:utext|Html\.Raw|\{\{\{|\| *raw'
```
For EACH hit: what is the data source (URL params, forms, headers, uploaded file contents,
webhook payloads, DB fields users can write = user-controlled) and is it escaped? Note whether
escaping is per-call-site discipline (fragile) or structural (auto-escaping templates,
textContent, an escaping tagged-template helper).

### 1.6 Security headers and CSP
```bash
scan "existing header mechanisms" 'helmet|SecurityMiddleware|django-csp|CSP_|talisman|secure_headers|content_security_policy|Content-Security-Policy|X-Content-Type-Options|Referrer-Policy|X-Frame-Options|Strict-Transport-Security|Permissions-Policy|frame-ancestors|add_header|headers\(\)'
scan "inline scripts / handlers / styles (affects CSP strictness)" '<script[^>]*>[^<[:space:]]|on(click|load|error|mouseover|submit|change)=|style="'
scan "third-party origins to allowlist or remove" '<(script|link|img|iframe)[^>]+(src|href)="https?://|fetch\("https?://|axios\.[a-z]+\("https?://|sentry|gtag|googletagmanager|analytics|stripe|maps\.googleapis|fonts\.googleapis|cdn\.'
```
Keep an inventory of every inline block/attribute and every external origin by directive
(script-src, style-src, font-src, img-src, connect-src, frame-src).

### 1.7 Third-party scripts without SRI and exposed tooling
```bash
scan "CDN scripts (check for integrity= on each)" '<script[^>]+src="https?://[^"]+"[^>]*>'
scan "SRI present" 'integrity="sha(256|384|512)-'
scan "exposed tooling / debug" 'docs_url|redoc_url|swagger|openapi|graphiql|playground|debug_toolbar|DEBUG[[:space:]]*=[[:space:]]*True|devtool|productionBrowserSourceMaps|sourcemap|source-map'
git ls-files | grep -iE '(^|/)\.env($|\.)' | grep -viE 'example|sample|template' || echo "(no .env files tracked)"
```

### 1.8 Supply chain
```bash
echo "lockfiles tracked:"; git ls-files | grep -E '(^|/)(package-lock\.json|yarn\.lock|pnpm-lock\.yaml|bun\.lockb?|poetry\.lock|Pipfile\.lock|go\.sum|Gemfile\.lock|composer\.lock|Cargo\.lock|packages\.lock\.json)$' || echo "(NONE)"
grep -cE -- '--hash=' requirements*.txt 2>/dev/null; grep -E '^[A-Za-z0-9_.\[\]-]+[[:space:]]*(>=|~=|\*|$)' requirements*.txt 2>/dev/null | head -20
grep -rnE 'npm (install|ci)|yarn install|pnpm install|pip install|poetry install|bundle install|composer install|go mod download' .github/workflows 2>/dev/null
grep -rniE 'audit|pip-audit|osv-scanner|govulncheck|bundler-audit|snyk|trivy|grype' .github/workflows 2>/dev/null || echo "(no dependency audit step in CI)"
ls .github/dependabot.yml renovate.json .renovaterc* 2>/dev/null || echo "(no Dependabot/Renovate)"
grep -rnE 'uses:[[:space:]]*[^@ ]+@v?[0-9]' .github/workflows 2>/dev/null && echo "^ actions pinned by TAG (should be 40-char SHA)" || true
grep -rnE 'uses:[[:space:]]*[^@ ]+@[0-9a-f]{40}' .github/workflows 2>/dev/null | wc -l | xargs echo "actions pinned by SHA:"
```

### 1.9 Token design (only if JWTs exist)
```bash
scan "JWT libraries" 'jsonwebtoken|[^a-z]jose[^a-z]|pyjwt|python-jose|authlib|jjwt|nimbus|golang-jwt|jwt-go|ruby-jwt|php-jwt|System\.IdentityModel\.Tokens\.Jwt'
scan "JWT verification settings" 'algorithms?[[:space:]]*[:=]|\.decode\(|\.verify\(|expiresIn|exp[[:space:]]*[:=]|maxAge|refresh_?token|audience|issuer|jwks'
```
Require: algorithm allowlist (alg:none rejected, no HS/RS confusion); verify not decode; exp
enforced; access-token lifetime ≤ 60 min (ideally ≤ 15); refresh rotation with reuse detection;
server-side revocation on logout; issuer/audience checks; signing secret not in repo.

### 1.10 Runtime probe (only if the app can run locally or APP_URL is set)
Start the app with the repo's documented command in the background and wait for the port, then:
```bash
BASE="${APP_URL:-http://localhost:${PORT:-3000}}"
for p in / /api /api/health /health; do echo "== $BASE$p"; curl -sS -m 10 -D - -o /dev/null "$BASE$p" 2>/dev/null | grep -iE '^(HTTP/|content-security-policy|content-security-policy-report-only|x-content-type-options|referrer-policy|x-frame-options|strict-transport-security|permissions-policy|cache-control|set-cookie|access-control-allow-origin|access-control-allow-credentials)' || echo "(unreachable)"; done
for p in /docs /api/docs /swagger /swagger-ui /graphql /__debug__/ /redoc; do printf '%s -> ' "$p"; curl -sS -m 10 -o /dev/null -w '%{http_code}\n' "$BASE$p"; done
```

# -------------------------------------------------------------------------------------
# PHASE 2 — VERDICT AND PLAN (gate: no edits before this is written)
# -------------------------------------------------------------------------------------
Write `docs/security/credential-storage-review-$(date +%Y-%m-%d).md` (or the repo's docs
location) with:
1. Applicability verdict per tier:
   - Tier A (credential exposure fix): APPLICABLE if 1.2 finds browser-readable credentials,
     1.3 finds missing cookie attributes, or 1.4 finds credentialed wildcard/reflected CORS or
     no CSRF defence. NOT APPLICABLE if no auth exists, or auth is already cookie-based with
     correct attributes and CSRF defence. DECISION REQUIRED if changing the auth transport
     would break non-browser consumers (mobile apps, public API clients, OAuth flows you
     cannot verify).
   - Tier B (defence in depth — headers/CSP/no-store/exposed tooling): applicable to every
     project that serves HTML or an API.
   - Tier C (supply chain + regression guards): applicable to every project with
     dependencies or CI.
2. Findings table: `# | Severity (Critical/High/Medium/Low/Info) | Finding | Evidence path:line | Recommended action | Tier`.
3. Plan: exact files to change, tests to add, anything deferred and why.
Gate: APPLY_SCOPE=report-only → commit only this document and jump to PHASE 5.
Tier A = DECISION REQUIRED → implement Tiers B and C, write the Tier A proposal (design,
migration steps, grace period) into the document, and say so in the PR.

# -------------------------------------------------------------------------------------
# PHASE 3 — IMPLEMENT
# -------------------------------------------------------------------------------------
### Tier A — move credentials out of script-readable storage (only if APPLICABLE)
Preferred for same-origin UI + API: opaque server-side session ID in a cookie
`__Host-session=<id>; HttpOnly; Secure; SameSite=Lax; Path=/` backed by a server-side store
(external store — Redis/DB — if serverless or multi-instance). If a JWT is genuinely required
(separate API domain, several client types): BFF / token-handler pattern — short-lived access
token IN MEMORY ONLY, refresh token in an HttpOnly cookie scoped to the refresh path with
rotation and reuse detection.
Server:
- Issue the cookie on login; clear it on logout with identical attributes AND invalidate the
  server-side session/refresh token.
- CSRF for unsafe methods: validate Origin (fallback Referer) against a configured allowlist,
  OR a synchroniser/double-submit token, in addition to SameSite. Keep any existing mandatory
  custom-header check.
- Same-origin apps: no CORS at all. If cross-origin is unavoidable: exact-match allowlist +
  Access-Control-Allow-Credentials:true; never *.
- LEGACY_TOKEN_GRACE_DAYS>0 → keep accepting the old header for that period with a dated TODO
  and a log warning; otherwise cut over and document the forced re-login.
- Non-browser clients keep Authorization: Bearer; only the browser path changes.
Browser:
- Remove every credential write/read to web storage and the manual Authorization header for
  same-origin calls; use credentials:'same-origin' ('include' only when cross-origin).
- On boot, purge legacy keys once (localStorage.removeItem('<old key>')) so tokens already in
  users' browsers are destroyed.
- 401 → login route; 403 (CSRF) → refresh token/page.
- Persisted-state libs: exclude the auth slice (partialize/blacklist).
- Vendor SDKs: change configuration per the 1.2 table; never patch SDK internals.
- Mobile (RN/Expo): expo-secure-store / react-native-keychain instead of AsyncStorage.
Recipes (adapt to repo conventions):
```
Express      app.use(helmet({contentSecurityPolicy: csp})); res.cookie('__Host-session', id, {httpOnly:true, secure:true, sameSite:'lax', path:'/', maxAge});
             CSRF middleware: on unsafe methods compare req.get('origin') (fallback referer) with ALLOWED_ORIGINS → 403
Next.js      cookies().set('__Host-session', id, {httpOnly:true, secure:true, sameSite:'lax', path:'/'}); static headers in next.config headers();
             nonce-based CSP in middleware.ts (Next emits inline scripts)
FastAPI      response.set_cookie("__Host-session", sid, httponly=True, secure=True, samesite="lax", path="/"); @app.middleware("http") for headers;
             dependency that checks Origin/Referer on unsafe methods
Django       SESSION_COOKIE_HTTPONLY=True SESSION_COOKIE_SECURE=True SESSION_COOKIE_SAMESITE="Lax" CSRF_COOKIE_SECURE=True
             SECURE_CONTENT_TYPE_NOSNIFF=True SECURE_REFERRER_POLICY="strict-origin-when-cross-origin" X_FRAME_OPTIONS="DENY"
             SECURE_HSTS_SECONDS (TLS only); django-csp; keep CsrfViewMiddleware
Flask        SESSION_COOKIE_HTTPONLY/SECURE/SAMESITE; flask-talisman for headers/CSP; Flask-WTF CSRF or Origin check
Rails        session_store ..., secure: Rails.env.production?, httponly: true, same_site: :lax; protect_from_forgery with: :exception;
             config/initializers/content_security_policy.rb
Spring Boot  server.servlet.session.cookie.http-only=true / .secure=true / .same-site=lax; http.headers(...); csrf() with CookieCsrfTokenRepository for SPAs
Laravel      config/session.php http_only=true secure=true same_site='lax'; Sanctum cookie auth for SPAs; keep VerifyCsrfToken; headers middleware
Go           http.SetCookie(w, &http.Cookie{Name:"__Host-session", Value:id, Path:"/", HttpOnly:true, Secure:true, SameSite:http.SameSiteLaxMode}); Origin check or gorilla/csrf
ASP.NET Core CookieBuilder{HttpOnly=true, SecurePolicy=Always, SameSite=Lax}; antiforgery; header middleware
Static hosts vercel.json headers / netlify.toml or _headers / nginx add_header
```

### Tier B — defence in depth (ALWAYS; add centrally in middleware/platform config)
```
Content-Security-Policy      per CSP_MODE (below)
X-Content-Type-Options       nosniff
Referrer-Policy              strict-origin-when-cross-origin
X-Frame-Options              DENY   (legacy complement to frame-ancestors)
Permissions-Policy           camera=(), microphone=(), geolocation=(), payment=()   (remove any the app uses)
Strict-Transport-Security    max-age=31536000; includeSubDomains   (only if every environment on that hostname is HTTPS; never localhost; no preload)
Cache-Control                no-store   on authenticated/sensitive API responses and file exports
```
Baseline CSP: `default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:;
font-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none';
form-action 'self'` + `upgrade-insecure-requests` in production. Extend directives ONLY with
origins verified in 1.6. 'unsafe-inline' is allowed in style-src only if inline styles exist
and cannot be moved cheaply — never in script-src.
CSP_MODE=auto: ENFORCE the full policy if 1.6 found no inline scripts/handlers, no eval-style
code, and every external origin is enumerated. Otherwise enforce the safe subset
(frame-ancestors, object-src, base-uri, form-action) in Content-Security-Policy and ship the
full policy in Content-Security-Policy-Report-Only (both headers may coexist) with a follow-up.
Frameworks that emit inline scripts (Next, Nuxt, SvelteKit, Angular SSR): implement the
documented nonce/hash pattern if standard for that version; otherwise report-only + follow-up.
Also: env-gate API docs/playgrounds off outside development; add integrity+crossorigin to any
remaining third-party <script> or self-host it; ensure DEBUG/source maps/.env never ship.

### Tier C — supply chain and regression guards (ALWAYS; non-breaking)
- Commit a lockfile if missing; switch CI to the deterministic install (npm ci /
  pip install --require-hashes / poetry install / bundle install --frozen).
- Add an audit step to CI failing on High/Critical with an allowlist file for accepted exceptions.
- Add .github/dependabot.yml per detected ecosystem (skip if Renovate exists).
- Pin GitHub Actions to 40-char commit SHAs with a `# vX.Y.Z` comment.
- Pin direct dependencies (hashes for Python where the toolchain supports it).
- Regression guard in CI (adapt source paths; allowlist file optional):
```yaml
- name: No credentials in web storage
  run: |
    ! grep -rniE --exclude-dir=node_modules --exclude-dir=dist --exclude-dir=build --exclude-dir=.next \
      '(localStorage|sessionStorage)\.(setItem|getItem)[[:space:]]*\([^,)]{0,40}(token|jwt|auth|secret|api[_-]?key|credential|refresh|id_token|access)' \
      src app public static 2>/dev/null | grep -vFf .security-storage-allowlist
```
- Tests in the project's runner asserting: every Tier B header on the root page and one API
  route; auth cookie attributes on the login response (HttpOnly; Secure; SameSite=…; __Host-);
  an unsafe request with `Origin: https://evil.example` is rejected (where cookies authenticate);
  docs routes return 404 when the production flag is set.
- Where HTML escaping is per-call-site, add a unit test for the escape helper (inputs:
  `<img src=x onerror=alert(1)>`, `"><script>`, `'`, `&`) — do not rewrite rendering wholesale.

# -------------------------------------------------------------------------------------
# PHASE 4 — VERIFY (all must pass before any PR)
# -------------------------------------------------------------------------------------
1. Full test suite + lint + type-check + build: green, compared against the PHASE 0 baseline.
   Do not claim to fix pre-existing failures and do not disable them.
2. Re-run the 1.2 scans: ZERO matches in client code except allowlisted vendor config.
3. Runtime (if the app runs locally / APP_URL set) — restart the app with your changes, then:
```bash
BASE="${APP_URL:-http://localhost:${PORT:-3000}}"
for p in / /api/health; do
  H=$(curl -sS -m 10 -D - -o /dev/null "$BASE$p"); echo "== $p"
  for h in content-security-policy x-content-type-options referrer-policy x-frame-options permissions-policy; do echo "$H" | grep -qi "^$h:" && echo "  ok   $h" || echo "  MISS $h"; done
done
# Login (adapt route/body): assert cookie attributes
LOGIN_ROUTE=/api/login; curl -sS -m 10 -c /tmp/cj -D - -o /dev/null -X POST "$BASE$LOGIN_ROUTE" -H 'content-type: application/json' --data '{}' | grep -i '^set-cookie' | tee /tmp/sc
grep -qi 'httponly' /tmp/sc && grep -qi 'secure' /tmp/sc && grep -qi 'samesite=' /tmp/sc && echo "cookie attrs ok" || echo "cookie attrs MISSING (or no login route — state that)"
# CSRF: foreign Origin on an unsafe route must be rejected (expect 403)
UNSAFE_ROUTE=/api/profile; curl -sS -m 10 -b /tmp/cj -o /dev/null -w 'foreign-origin POST -> %{http_code}\n' -X POST "$BASE$UNSAFE_ROUTE" -H 'Origin: https://evil.example' -H 'content-type: application/json' --data '{}'
# Exposed tooling must be off when the production flag is set
for p in /docs /api/docs /swagger /graphql; do printf '%s -> ' "$p"; curl -sS -m 10 -o /dev/null -w '%{http_code}\n' "$BASE$p"; done
```
4. Run the audit tool (npm audit --audit-level=high / pip-audit / osv-scanner / bundler-audit /
   govulncheck / composer audit); record the summary.
5. If Playwright/Cypress exist, run the auth smoke test and check the console for CSP
   violations; otherwise state that no browser harness exists.
6. Put all evidence (commands + trimmed output) into the review document.

# -------------------------------------------------------------------------------------
# PHASE 5 — PULL REQUEST
# -------------------------------------------------------------------------------------
```bash
git add -A && git commit -m "security: harden credential storage, cookies, headers and supply chain" \
  -m "See docs/security/credential-storage-review-$(date +%Y-%m-%d).md"
git push -u origin "$WORK_BRANCH"
cat > /tmp/pr_body.md <<'EOF'
## Summary
<one paragraph>
## Applicability verdict
Tier A: <Applicable | Not applicable | Decision required> — <why>
Tier B: <…>   Tier C: <…>
## Findings
| # | Severity | Finding | Evidence | Action | Tier |
|---|---|---|---|---|---|
## Changes
- <file> — <what/why>
## Behaviour change
<forced re-login / CSP report-only / none>
## Not changed / follow-ups
- <item + reason>
## Verification evidence
<tests, headers verified, cookie attrs, CSRF probe, audit summary>
## Rollback
Revert the squash commit; users re-login; no data migration involved.
Review document: docs/security/credential-storage-review-<date>.md
EOF
gh pr create --base "$DEFAULT" --head "$WORK_BRANCH" --title "security: harden credential storage, cookies, headers and supply chain" --body-file /tmp/pr_body.md
gh pr edit --add-label security 2>/dev/null || true
```

# -------------------------------------------------------------------------------------
# PHASE 6 — MERGE
# -------------------------------------------------------------------------------------
```bash
PR=$(gh pr view --json number -q .number)
gh pr checks "$PR" --watch        # if checks fail: fix ONCE, push, watch again; still failing → stop and report
gh pr view "$PR" --json reviewDecision,mergeStateStatus -q '"review=\(.reviewDecision) state=\(.mergeStateStatus)"'
```
Merge only if ALL hold: AUTO_MERGE=true, DRY_RUN=false, checks green, no required review
pending. Then run exactly (as the last command, no pipes, no `--auto`, no `--admin`):
```bash
gh pr merge "$PR" --$MERGE_STRATEGY --delete-branch
```
If protection requires reviews or the merge is refused: leave the PR open, never use --admin
or force, report the blocker, keep the work branch (the PR needs it), and still run PHASE 7
for OTHER branches.

# -------------------------------------------------------------------------------------
# PHASE 7 — BRANCH CLEANUP (after merge)
# -------------------------------------------------------------------------------------
Invariants: never touch $DEFAULT; never delete a protected branch, a PROTECTED_BRANCH_PATTERNS
match, or a branch with an open PR; operate on origin only; archive every UNMERGED branch as a
tag before deleting it; if deletion is denied, report and stop (no elevated flags).
```bash
git checkout "$DEFAULT" && git pull --ff-only && git fetch --prune origin
OPEN_PRS=$(gh pr list --state open --limit 500 --json headRefName -q '.[].headRefName')
PROTECTED=$(gh api --paginate "repos/{owner}/{repo}/branches?protected=true" -q '.[].name' 2>/dev/null || true)
pattern_protected() { for pat in $PROTECTED_BRANCH_PATTERNS; do case "$1" in $pat) return 0;; esac; done; return 1; }
STAMP=$(date +%Y%m%d)
printf '%-55s %-7s %-7s %-10s %-7s %s\n' BRANCH MERGED OPENPR PROTECTED ACTION ARCHIVE_TAG
for b in $(git for-each-ref --format='%(refname:short)' refs/remotes/origin | sed 's#^origin/##' | grep -vx -e HEAD -e "$DEFAULT"); do
  merged=no; git merge-base --is-ancestor "origin/$b" "origin/$DEFAULT" 2>/dev/null && merged=yes
  openpr=no; grep -qx "$b" <<<"$OPEN_PRS" && openpr=yes
  prot=no;  { grep -qx "$b" <<<"$PROTECTED" || pattern_protected "$b"; } && prot=yes
  action=keep; tag=-
  if [ "$openpr" = no ] && [ "$prot" = no ]; then
    case "$BRANCH_CLEANUP_MODE" in
      own-branch-only) [ "$b" = "$WORK_BRANCH" ] && action=delete ;;
      merged-only)     { [ "$merged" = yes ] || [ "$b" = "$WORK_BRANCH" ]; } && action=delete ;;
      all-unprotected) action=delete; [ "$merged" = no ] && tag="archive/$b/$STAMP" ;;
    esac
  fi
  printf '%-55s %-7s %-7s %-10s %-7s %s\n' "$b" "$merged" "$openpr" "$prot" "$action" "$tag"
  if [ "$DRY_RUN" != true ] && [ "$action" = delete ]; then
    if [ "$tag" != - ]; then git tag -a "$tag" "origin/$b" -m "archived before deletion by security hardening run" && git push origin "$tag" || { echo "archive failed for $b — NOT deleting"; continue; }; fi
    git push origin --delete "$b" || echo "delete denied for $b (reported, not retried)"
    git branch -D "$b" 2>/dev/null || true
  fi
done
git fetch --prune origin && git branch -r
```

# -------------------------------------------------------------------------------------
# PHASE 8 — FINAL REPORT (print verbatim at the end)
# -------------------------------------------------------------------------------------
```
Repository / default branch / work branch:
Applicability: Tier A <Applicable|Not applicable|Decision required> · Tier B <…> · Tier C <…>
Findings: <n> (Critical x, High x, Medium x, Low x, Info x) — <review doc path>
Changes applied: <files + one line each>
Deferred / follow-ups: <item — reason>
Verification: tests <pass/fail vs baseline> · headers <verified list> · cookie attrs <verified|n/a> · CSRF probe <code|n/a> · audit <summary>
PR: <url> — <merged <sha> | open: <reason>>
Branches deleted: <list> · archived tags: <list> · skipped: <branch — reason>
Behaviour changes users will notice: <bullets | none>
```

## STOP CONDITIONS
- gh not authenticated / no push rights → PHASES 0–4 locally only; report the blocker.
- Working tree dirty at start → stop (never stash someone else's work).
- Tier A = Decision required → implement B + C; propose A in the review document.
- Baseline red before your changes → proceed, but do not auto-merge unless the PR's own CI is
  green and the failures are demonstrably pre-existing.
- Repository is a fork, or branch deletion denied → skip PHASE 7 and report.
- Any step would require printing, committing or rotating a secret → stop that step.

## CALIBRATION EXAMPLE (small FastAPI + vanilla-JS tool, no auth)
Tier A NOT APPLICABLE — no authentication; the only credential-like value is a 96-bit random
session ID held in a JS variable and sent as a custom X-Session header (never in web storage);
custom header + absent CORS already blocks CSRF. Recorded recommendation: when real auth
arrives use a __Host-session cookie + Origin check, not web storage.
Tier B APPLICABLE — no CSP/security headers; every innerHTML sink escapes user data (good) but
by per-call-site discipline; Swagger UI served from a CDN at /api/docs. Actions: header
middleware with ENFORCED CSP (no inline scripts), no-store on export/reconcile responses,
env-gate /api/docs, header tests.
Tier C APPLICABLE — unpinned >= ranges, no audit step, Actions pinned by tag. Actions:
hash-pinned requirements, pip-audit in CI, Dependabot, SHA pins, web-storage guard in CI.
