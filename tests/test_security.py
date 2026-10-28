"""Browser-facing security controls.

Covers the headers and Content-Security-Policy sent on every route, the no-store rule for
API responses that carry uploaded broker data, the production flag that hides the
interactive API docs, and two regression guards for the class of bug where a credential
or unescaped value reaches JavaScript: nothing credential-like may be written to browser
storage, and user-controlled values must pass through escapeHtml() before innerHTML.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import CONTENT_SECURITY_POLICY, DOCS_CONTENT_SECURITY_POLICY, IS_PRODUCTION, app

ROOT = Path(__file__).resolve().parents[1]
STATIC_DIR = ROOT / "app" / "static"
APP_JS = (STATIC_DIR / "app.js").read_text(encoding="utf-8")

EXPECTED_HEADERS = {
    "Content-Security-Policy": CONTENT_SECURITY_POLICY,
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "X-Frame-Options": "DENY",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=()",
}


@pytest.fixture()
def client():
    with TestClient(app) as test_client:
        yield test_client


def _directives(policy: str) -> dict[str, str]:
    parts = (item.strip().split(None, 1) for item in policy.split(";") if item.strip())
    return {name: (values[0] if values else "") for name, *values in parts}


# ----------------------------------------------------------------- headers / CSP
@pytest.mark.parametrize("path", ["/", "/api/health", "/static/app.js", "/openapi.json", "/no-such-page"])
def test_security_headers_are_sent_on_every_kind_of_route(client, path):
    response = client.get(path)
    for name, value in EXPECTED_HEADERS.items():
        assert response.headers.get(name) == value, f"{name} missing or wrong on {path}"


def test_content_security_policy_is_strict_first_party_only():
    directives = _directives(CONTENT_SECURITY_POLICY)
    assert directives["default-src"] == "'self'"
    assert directives["script-src"] == "'self'"
    assert directives["style-src"] == "'self'"
    assert directives["connect-src"] == "'self'"
    assert directives["object-src"] == "'none'"
    assert directives["base-uri"] == "'none'"
    assert directives["frame-ancestors"] == "'none'"
    assert directives["form-action"] == "'self'"
    assert "'unsafe-inline'" not in directives["script-src"]
    assert "'unsafe-eval'" not in CONTENT_SECURITY_POLICY


def test_app_shell_has_no_inline_scripts_styles_or_handlers():
    """The strict policy only works because the UI never relies on inline code."""
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    assert re.search(r"<script(?![^>]*\bsrc=)[^>]*>", html) is None, "inline <script> block found"
    assert "<style" not in html
    assert re.search(r"\son[a-z]+\s*=", html, re.I) is None, "inline event handler found"
    assert re.search(r'style="', html) is None, "inline style attribute in index.html"
    assert re.search(r'style="', APP_JS) is None, "inline style attribute in a rendered template"
    assert not re.search(r"https?://", (STATIC_DIR / "styles.css").read_text(encoding="utf-8"))


# ----------------------------------------------------------------- caching
def test_api_responses_are_never_cached_but_static_assets_may_be(client):
    for path in ("/api/health", "/api/releases", "/api/quality", "/api/demo"):
        assert client.get(path).headers.get("Cache-Control") == "no-store", path
    session = {"X-Session": client.post("/api/session").json()["session_id"]}
    client.post("/api/demo/load", headers=session)
    reconcile = client.post("/api/reconcile", headers=session, json={})
    assert reconcile.status_code == 200
    assert reconcile.headers.get("Cache-Control") == "no-store"
    export = client.get("/api/export/csv", headers=session)
    assert export.status_code == 200
    assert export.headers.get("Cache-Control") == "no-store"
    assert client.get("/").headers.get("Cache-Control") != "no-store"
    assert client.get("/static/styles.css").headers.get("Cache-Control") != "no-store"


# ----------------------------------------------------------------- API docs gating
def test_api_docs_are_available_locally_with_a_policy_limited_to_the_swagger_cdn(client):
    assert not IS_PRODUCTION
    response = client.get("/api/docs")
    assert response.status_code == 200
    assert response.headers["Content-Security-Policy"] == DOCS_CONTENT_SECURITY_POLICY
    directives = _directives(DOCS_CONTENT_SECURITY_POLICY)
    assert "https://cdn.jsdelivr.net" in directives["script-src"]
    assert directives["frame-ancestors"] == "'none'"
    assert directives["object-src"] == "'none'"
    assert "Strict-Transport-Security" not in response.headers
    for name in ("X-Content-Type-Options", "Referrer-Policy", "X-Frame-Options"):
        assert response.headers.get(name) == EXPECTED_HEADERS[name]


def test_production_flag_disables_api_docs_and_enables_https_only_headers():
    """RECONIQ_ENV is read at import time, so the production app is built in a subprocess."""
    probe = """
import json
from fastapi.testclient import TestClient
from app.main import IS_PRODUCTION, app
assert IS_PRODUCTION
client = TestClient(app)
page = client.get("/")
print(json.dumps({
    "docs": client.get("/api/docs").status_code,
    "openapi": client.get("/openapi.json").status_code,
    "health": client.get("/api/health").status_code,
    "hsts": page.headers.get("Strict-Transport-Security"),
    "csp": page.headers.get("Content-Security-Policy"),
}))
"""
    env = {**os.environ, "RECONIQ_ENV": "production", "PYTHONPATH": str(ROOT)}
    result = subprocess.run(
        [sys.executable, "-c", probe], cwd=ROOT, env=env, capture_output=True, text=True, timeout=180,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    assert payload["docs"] == 404
    assert payload["openapi"] == 200
    assert payload["health"] == 200
    assert payload["hsts"] == "max-age=31536000; includeSubDomains"
    assert "upgrade-insecure-requests" in payload["csp"]
    assert "'unsafe-inline'" not in _directives(payload["csp"])["script-src"]


# ----------------------------------------------------------------- regression guards
CREDENTIAL_IN_WEB_STORAGE = re.compile(
    r"(localStorage|sessionStorage)\.(setItem|getItem|removeItem)\s*\([^,)]{0,40}"
    r"(token|jwt|auth|session|secret|api[_-]?key|credential|refresh|id_token|access)",
    re.IGNORECASE,
)


def test_browser_code_never_stores_credentials_in_web_storage_or_js_cookies():
    """A credential in localStorage/sessionStorage is readable by any injected script.

    The reconciliation session id must stay in memory (state.sessionId) and travel in the
    X-Session header; only non-sensitive UI preferences may use browser storage.
    """
    for path in sorted(STATIC_DIR.glob("*.js")) + sorted(STATIC_DIR.glob("*.html")):
        source = path.read_text(encoding="utf-8")
        assert CREDENTIAL_IN_WEB_STORAGE.search(source) is None, f"credential-like web storage use in {path.name}"
        assert re.search(r"document\.cookie\s*=", source) is None, f"JavaScript-set cookie in {path.name}"
        assert re.search(r"(localStorage|sessionStorage)\[", source) is None, f"bracket storage access in {path.name}"
    storage_keys = set(re.findall(r"localStorage\.(?:setItem|getItem)\(\s*([A-Za-z_][\w.]*)", APP_JS))
    assert storage_keys == {"QUALITY_PREFS_KEY"}
    assert "sessionStorage" not in APP_JS
    assert "sessionId: null" in APP_JS and 'headers["X-Session"] = state.sessionId' in APP_JS


def test_escape_helper_neutralises_html_metacharacters():
    match = re.search(r"function escapeHtml\(value\) \{(.*?)\n\}", APP_JS, re.S)
    assert match, "escapeHtml() helper is missing"
    body = match.group(1)
    assert "/[&<>\"']/g" in body
    for entity in ("&amp;", "&lt;", "&gt;", "&quot;", "&#39;"):
        assert entity in body
    node = shutil.which("node")
    if node is None:  # pragma: no cover - the static assertions above still apply
        return
    script = (
        "function escapeHtml(value) {" + body + "\n}\n"
        "const out = escapeHtml('<img src=x onerror=alert(1)>\"\\'&');\n"
        "if (out !== '&lt;img src=x onerror=alert(1)&gt;&quot;&#39;&amp;') { throw new Error(out); }\n"
        "if (escapeHtml(null) !== '' || escapeHtml(undefined) !== '' || escapeHtml(12.5) !== '12.5') { throw new Error('nullish'); }\n"
        "console.log('escape-ok');"
    )
    result = subprocess.run([node, "-e", script], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    assert "escape-ok" in result.stdout


USER_CONTROLLED = re.compile(
    r"\.(filename|label|header|insured|insurer|insured_name|insurer_name|policy_no|detail|action|reason|"
    r"message|method|broker_value|insurer_value|source_label|category_label|values|notes|assumptions|skipped)\b"
    r"|\b(h|w|note)\b|row\[i\]"
)


def test_user_controlled_values_are_escaped_before_reaching_innerhtml():
    """Values that originate in uploaded files or findings must be wrapped in escapeHtml().

    The UI renders with template literals assigned to innerHTML, so escaping is a per-call-
    site discipline. This guard fails as soon as one of the data-bearing properties is
    interpolated raw. toast() is exempt because it writes through textContent.
    """
    lines = APP_JS.splitlines()
    offenders = []
    for match in re.finditer(r"\$\{([^{}]*)\}", APP_JS):
        expression = match.group(1).strip()
        line_no = APP_JS.count("\n", 0, match.start()) + 1
        if "escapeHtml(" in expression or "toast(" in lines[line_no - 1]:
            continue
        if USER_CONTROLLED.search(expression):
            offenders.append(f"app.js:{line_no}: ${{{expression}}}")
    assert not offenders, "unescaped user-controlled interpolation(s):\n" + "\n".join(offenders)
