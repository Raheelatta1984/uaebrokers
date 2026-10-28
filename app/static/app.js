/* ReconIQ prototype - vanilla JS, no build step.
   Deliberately simple: one state object, render functions, and fetch calls. */

const state = {
  sessionId: null,
  sources: [],
  result: null,
  step: "files",
  filters: { severity: "all", category: "all", search: "" },
  showAllMatched: false,
  view: "workspace",
  releases: null,
  releasesLoading: false,
  quality: null,
  qualityLoading: false,
};

const QUALITY_PREFS_KEY = "reconiq-quality-section-preferences-v1";
const QUALITY_SECTIONS = [
  { id: "overview", label: "Overview & guide", defaultEnabled: true },
  { id: "verification", label: "Latest test result", defaultEnabled: true },
  { id: "scenarios", label: "Test scenarios & scripts", defaultEnabled: true },
  { id: "findings", label: "Defects & findings", defaultEnabled: true },
  { id: "incidents", label: "Incident register", defaultEnabled: true },
  { id: "ai-guidance", label: "AI guidance (opt-in)", defaultEnabled: false },
];

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

const AED = new Intl.NumberFormat("en-AE", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const INT = new Intl.NumberFormat("en-AE");

function money(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "—";
  return `AED ${AED.format(Number(value))}`;
}

function moneyShort(value) {
  const n = Number(value || 0);
  const abs = Math.abs(n);
  const sign = n < 0 ? "-" : "";
  if (abs >= 1000000) return `${sign}AED ${(abs / 1000000).toFixed(2)}m`;
  if (abs >= 10000) return `${sign}AED ${(abs / 1000).toFixed(1)}k`;
  return `${sign}AED ${AED.format(abs)}`;
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (c) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
  ));
}

/* ------------------------------------------------------------------ utils */
let toastTimer = null;
function toast(message, isError = false) {
  const el = $("#toast");
  el.textContent = message;
  el.classList.toggle("is-error", isError);
  el.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { el.hidden = true; }, 4200);
}

function showOverlay(title, step, progress) {
  $("#overlay-title").textContent = title;
  $("#overlay-step").textContent = step;
  $("#overlay-bar").style.width = `${progress}%`;
  $("#overlay").hidden = false;
}

function overlayStep(text, progress) {
  $("#overlay-step").textContent = text;
  $("#overlay-bar").style.width = `${progress}%`;
}

function hideOverlay() {
  $("#overlay").hidden = true;
}

async function api(path, options = {}) {
  const headers = Object.assign({}, options.headers || {});
  if (state.sessionId) headers["X-Session"] = state.sessionId;
  if (options.body && !(options.body instanceof FormData)) {
    headers["Content-Type"] = "application/json";
  }
  const response = await fetch(path, { ...options, headers });
  const isJson = (response.headers.get("content-type") || "").includes("application/json");
  const payload = isJson ? await response.json() : await response.text();
  if (!response.ok) {
    const detail = (payload && payload.detail) || payload || "Something went wrong.";
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return payload;
}

/* ------------------------------------------------------------- app sections */
function setView(view) {
  state.view = view;
  $("#view-workspace").hidden = view !== "workspace";
  $("#view-whats-new").hidden = view !== "whats-new";
  $("#view-quality").hidden = view !== "quality";
  $("#reconciliation-steps").hidden = view !== "workspace";
  $$(".app-tab").forEach((tab) => {
    const selected = tab.dataset.view === view;
    tab.classList.toggle("is-active", selected);
    tab.setAttribute("aria-selected", String(selected));
    tab.tabIndex = selected ? 0 : -1;
  });
  closeDrawer();
}

function navigateView(view) {
  const hash = view === "whats-new" ? "#whats-new" : view === "quality" ? "#quality" : "#reconciliation";
  setView(view);
  $(`#tab-${view}`).focus({ preventScroll: true });
  if (window.location.hash !== hash) window.location.hash = hash;
  window.scrollTo({ top: 0, behavior: "smooth" });
}

/* -------------------------------------------------------------- release notes */
const CHANGE_LABELS = { added: "Added", improved: "Improved", fixed: "Fixed" };
const RELEASE_DATE = new Intl.DateTimeFormat("en-GB", {
  day: "numeric", month: "long", year: "numeric", timeZone: "UTC",
});

function renderReleases() {
  const { current_version: version, releases } = state.releases;
  $("#app-version").textContent = `v${version}`;
  $("#app-version").hidden = false;
  $("#current-version").textContent = `v${version}`;
  $("#release-version-summary").hidden = false;
  $("#releases-message").textContent = releases.length ? "" : "No release notes have been published yet.";
  $("#releases-message").hidden = releases.length > 0;
  $("#release-list").innerHTML = releases.map((release) => {
    const current = release.version === version;
    const date = new Date(`${release.date}T00:00:00Z`);
    const dateLabel = Number.isNaN(date.getTime()) ? release.date : RELEASE_DATE.format(date);
    return `
      <article class="card release-card ${current ? "is-current" : ""}">
        <div class="release-meta">
          <span class="release-version">v${escapeHtml(release.version)}</span>
          ${current ? '<span class="release-latest">Latest release</span>' : ""}
          <time datetime="${escapeHtml(release.date)}">${escapeHtml(dateLabel)}</time>
        </div>
        <h2>${escapeHtml(release.title)}</h2>
        <p class="release-summary">${escapeHtml(release.summary)}</p>
        <ul class="release-changes">
          ${(release.changes || []).map((change) => {
            const type = Object.hasOwn(CHANGE_LABELS, change.type) ? change.type : "update";
            return `
              <li>
                <span class="change-badge change-${type}">${CHANGE_LABELS[type] || "Update"}</span>
                <div>
                  <h3>${escapeHtml(change.title)}</h3>
                  <p>${escapeHtml(change.description)}</p>
                </div>
              </li>`;
          }).join("")}
        </ul>
      </article>`;
  }).join("");
}

async function loadReleases() {
  if (state.releasesLoading) return;
  state.releasesLoading = true;
  $("#release-notes").setAttribute("aria-busy", "true");
  $("#releases-message").textContent = "Loading release notes…";
  $("#releases-message").hidden = false;
  $("#btn-retry-releases").hidden = true;
  try {
    const payload = await api("/api/releases");
    if (!payload || typeof payload.current_version !== "string" || !Array.isArray(payload.releases)) {
      throw new Error("Invalid release history.");
    }
    state.releases = payload;
    renderReleases();
  } catch (_) {
    $("#releases-message").textContent = "Release notes could not be loaded. Please try again.";
    $("#releases-message").hidden = false;
    $("#btn-retry-releases").hidden = false;
  } finally {
    state.releasesLoading = false;
    $("#release-notes").setAttribute("aria-busy", "false");
  }
}

/* --------------------------------------------------------- quality record */
function qualityPreferences() {
  const defaults = Object.fromEntries(QUALITY_SECTIONS.map((item) => [item.id, item.defaultEnabled]));
  try {
    const saved = JSON.parse(localStorage.getItem(QUALITY_PREFS_KEY) || "{}");
    return { ...defaults, ...Object.fromEntries(Object.keys(defaults).map((id) => [id, saved[id] === undefined ? defaults[id] : Boolean(saved[id])])) };
  } catch (_) {
    return defaults;
  }
}

function renderQuality() {
  const quality = state.quality;
  if (!quality) return;
  const prefs = qualityPreferences();
  const verification = quality.verification;
  const stamp = new Date(verification.recorded_at);
  const stampLabel = Number.isNaN(stamp.getTime()) ? verification.recorded_at : stamp.toLocaleString("en-AU", { timeZone: "UTC", dateStyle: "medium", timeStyle: "short" }) + " UTC";
  $("#quality-status").textContent = `${verification.status === "verified" ? "Verified" : "Unverified"} · ${verification.passed} passed · ${verification.failed} failed`;
  const toggles = [
    ...QUALITY_SECTIONS.map((item) => `
      <label class="quality-toggle">
        <span><strong>${escapeHtml(item.label)}</strong>${item.id === "ai-guidance" ? '<small>Off by default; no AI service is connected</small>' : ""}</span>
        <input type="checkbox" data-quality-pref="${item.id}" ${prefs[item.id] ? "checked" : ""} aria-label="Show ${escapeHtml(item.label)}" />
      </label>`),
    ...quality.features.filter((feature) => !QUALITY_SECTIONS.some((item) => item.id === feature.id)).map((feature) => `
      <label class="quality-toggle is-unavailable" title="${escapeHtml(feature.note)}">
        <span><strong>${escapeHtml(feature.name)}</strong><small>Future option · not connected</small></span>
        <input type="checkbox" disabled aria-label="${escapeHtml(feature.name)} unavailable" />
      </label>`),
  ].join("");
  $("#quality-toggles").innerHTML = toggles;
  $("#quality-toggles").querySelectorAll("[data-quality-pref]").forEach((input) => {
    input.addEventListener("change", () => {
      const updated = qualityPreferences();
      updated[input.dataset.qualityPref] = input.checked;
      try { localStorage.setItem(QUALITY_PREFS_KEY, JSON.stringify(updated)); } catch (_) { /* browser storage is optional */ }
      renderQuality();
    });
  });

  const suites = quality.suites.map((suite) => `
    <details class="quality-suite">
      <summary><span class="quality-suite-name">${escapeHtml(suite.name)}</span><span class="quality-kind">${escapeHtml(suite.kind)}</span><span class="quality-file">${escapeHtml(suite.file)}</span></summary>
      <div class="quality-suite-body">
        <p>${escapeHtml(suite.purpose)}</p>
        <h4>High-level test steps</h4>
        <ol>${suite.steps.map((step) => `<li>${escapeHtml(step)}</li>`).join("")}</ol>
        <h4>Referenced test scripts</h4>
        <div class="script-list">${suite.scripts.map((script) => `<code>${escapeHtml(script)}</code>`).join("")}</div>
        <p class="quality-expect"><strong>Expected result:</strong> ${escapeHtml(suite.expected)}</p>
        <p class="quality-expect"><strong>Impact:</strong> ${escapeHtml(suite.impact)}</p>
      </div>
    </details>`).join("");
  const findings = quality.findings.map((finding) => `
    <article class="quality-finding">
      <div class="quality-finding-meta"><span class="quality-kind">${escapeHtml(finding.type)}</span><span class="quality-severity">${escapeHtml(finding.severity)}</span><span class="quality-state">${escapeHtml(finding.status)}</span></div>
      <h3>${escapeHtml(finding.summary)}</h3>
      <p><strong>Evidence:</strong> ${escapeHtml(finding.evidence)}</p>
      <p><strong>Disposition / fix:</strong> ${escapeHtml(finding.resolution)}</p>
    </article>`).join("");
  const incidents = quality.incidents.length ? quality.incidents.map((incident) => `
    <article class="quality-finding"><h3>${escapeHtml(incident.title || incident.id)}</h3><p>${escapeHtml(incident.summary || "")}</p></article>`).join("") : `
    <div class="quality-empty"><strong>No incidents recorded</strong><p>${escapeHtml(quality.incident_note)}</p></div>`;
  const aiFeature = quality.features.find((feature) => feature.id === "ai-guidance");
  const cards = [
    `<section class="card quality-card" data-quality-section="overview"><h2>Purpose &amp; reviewer guide</h2><p>${escapeHtml(quality.purpose)}</p><ol class="quality-guide">${quality.guide.map((line) => `<li>${escapeHtml(line)}</li>`).join("")}</ol><p class="quality-scope-note">This page reports repository evidence and an explicitly recorded local run. It does not claim that test scenarios outside this codebase were executed.</p></section>`,
    `<section class="card quality-card" data-quality-section="verification"><h2>Latest recorded automated run</h2><div class="quality-metrics"><div><span>Result</span><strong>${escapeHtml(verification.result)}</strong></div><div><span>Command</span><code>${escapeHtml(verification.command)}</code></div><div><span>Recorded (UTC)</span><strong>${escapeHtml(stampLabel)}</strong></div><div><span>Run scope</span><strong>${escapeHtml(verification.scope)}</strong></div></div><div class="quality-warning"><strong>Warning (${verification.warnings}):</strong> ${escapeHtml(verification.warning_detail)}</div><p class="muted">${escapeHtml(verification.performance_note)}</p></section>`,
    `<section class="card quality-card" data-quality-section="scenarios"><h2>Test scenarios, scripts &amp; expected impact</h2><p class="muted">Expand a suite to review its high-level steps and source test names. Parametrized test functions produce multiple individual cases.</p><div class="quality-suite-list">${suites}</div></section>`,
    `<section class="card quality-card" data-quality-section="findings"><h2>Defects &amp; findings</h2><p class="muted">Seeded business exceptions and test-tool warnings are kept separate from confirmed product defects.</p><div class="quality-findings">${findings}</div></section>`,
    `<section class="card quality-card" data-quality-section="incidents"><h2>Incident register</h2><p class="muted">Operational incidents are distinct from reconciliation exceptions and automated test failures.</p>${incidents}</section>`,
    `<section class="card quality-card" data-quality-section="ai-guidance" ${prefs["ai-guidance"] ? "" : "hidden"}><h2>AI guidance · ${prefs["ai-guidance"] ? "preference on" : "off"}</h2><div class="quality-ai-note"><strong>${aiFeature.available ? "AI assistance available" : "AI service not connected"}</strong><p>${escapeHtml(aiFeature.note)}</p><p>No AI-generated test conclusions or incident classifications are shown here.</p></div></section>`,
  ].join("");
  $("#quality-content").innerHTML = cards;
  $$("[data-quality-section]").forEach((section) => {
    if (section.dataset.qualitySection !== "ai-guidance") section.hidden = !prefs[section.dataset.qualitySection];
  });
}

async function loadQuality() {
  if (state.qualityLoading) return;
  state.qualityLoading = true;
  try {
    const payload = await api("/api/quality");
    if (!payload || !payload.verification || !Array.isArray(payload.suites)) throw new Error("Invalid quality record.");
    state.quality = payload;
    renderQuality();
  } catch (error) {
    $("#quality-status").textContent = "Quality record unavailable";
    $("#quality-content").innerHTML = `<p class="release-message">Could not load the test catalogue: ${escapeHtml(error.message)}</p>`;
  } finally {
    state.qualityLoading = false;
  }
}

/* ------------------------------------------------------------------ steps */
function setStep(step) {
  state.step = step;
  ["files", "mapping", "results", "exceptions"].forEach((name) => {
    $(`#step-${name}`).hidden = name !== step;
  });
  const order = ["files", "mapping", "results", "exceptions"];
  $$(".step").forEach((btn) => {
    const name = btn.dataset.step;
    btn.classList.toggle("is-active", name === step);
    btn.classList.toggle("is-done", order.indexOf(name) < order.indexOf(step));
    const ready = name === "files" || name === "mapping"
      ? state.sources.length > 0
      : state.result !== null;
    btn.disabled = !ready && name !== step;
  });
  window.scrollTo({ top: 0, behavior: "smooth" });
}

/* ------------------------------------------------------------- file lists */
function sourceById(id) {
  return state.sources.find((source) => source.id === id);
}

function renderFileLists() {
  ["broker", "statement"].forEach((side) => {
    const holder = $(`.file-list[data-side="${side}"]`);
    const files = state.sources.filter((source) => source.side === side);
    holder.innerHTML = files.map((source) => {
      const confidence = (source.meta.confidence || "medium").toLowerCase();
      const rows = source.meta.record_count ?? source.row_count;
      return `
        <div class="file-row">
          <div class="file-meta">
            <div class="file-name">${escapeHtml(source.filename)}</div>
            <div class="file-sub">${INT.format(rows)} policy lines · ${escapeHtml(source.meta.method || "parsed")}${
              source.skipped_count ? ` · ${source.skipped_count} row(s) ignored` : ""
            }</div>
          </div>
          <span class="conf conf-${confidence}">${escapeHtml(confidence)} confidence</span>
          <button class="icon-btn" data-remove="${source.id}" title="Remove file" type="button">✕</button>
        </div>`;
    }).join("");
  });

  const brokerCount = state.sources.filter((s) => s.side === "broker").length;
  const statementCount = state.sources.filter((s) => s.side === "statement").length;
  const summary = $("#files-summary");
  if (!state.sources.length) {
    summary.textContent = "No files loaded yet.";
  } else {
    const lines = state.sources.reduce((total, s) => total + (s.meta.record_count ?? s.row_count), 0);
    summary.textContent =
      `${brokerCount} policy register${brokerCount === 1 ? "" : "s"} · ` +
      `${statementCount} insurer statement${statementCount === 1 ? "" : "s"} · ` +
      `${INT.format(lines)} lines ready to reconcile.`;
  }
  const ready = brokerCount >= 1 && statementCount >= 1;
  $("#btn-to-mapping").disabled = !ready;
  if (!ready && state.sources.length) {
    summary.textContent += brokerCount < 1
      ? " Add the broker policy register to continue."
      : " Add at least one insurer statement to continue.";
  }
}

async function uploadFiles(files, side) {
  if (!files || !files.length) return;
  const form = new FormData();
  Array.from(files).forEach((file) => form.append("files", file));
  form.append("side", side);
  showOverlay("Reading files", `Parsing ${files.length} file(s)…`, 25);
  try {
    const payload = await api("/api/upload", { method: "POST", body: form });
    state.sessionId = payload.session_id || state.sessionId;
    state.result = null;
    payload.sources.forEach((source) => state.sources.push(source));
    renderFileLists();
    const failures = payload.errors || [];
    if (failures.length) {
      toast(failures.map((f) => `${f.filename}: ${f.error}`).join(" · "), true);
    } else {
      toast(`${payload.sources.length} file(s) loaded and mapped.`);
    }
  } catch (error) {
    toast(error.message, true);
  } finally {
    hideOverlay();
  }
}

/* ------------------------------------------------------------ demo loading */
async function loadDemoCatalogue() {
  try {
    const demo = await api("/api/demo");
    $("#demo-broker-name").textContent = demo.broker;
    $("#demo-files").innerHTML = demo.files.map((file) => `
      <li>
        <span class="file-kind">${escapeHtml(file.kind)}</span>
        <span class="fname">${escapeHtml(file.name)}</span>
        <a href="/api/demo/file/${encodeURIComponent(file.name)}" download>get file</a>
      </li>`).join("");
  } catch (error) {
    $("#demo-files").innerHTML = `<li class="loading-row">Could not load the demo list: ${escapeHtml(error.message)}</li>`;
  }
}

async function loadDemo() {
  showOverlay("Loading demo dataset", "Reading the broker register…", 15);
  try {
    const payload = await api("/api/demo/load", { method: "POST" });
    state.sessionId = payload.session_id || state.sessionId;
    state.sources = [];
    state.result = null;
    state.sources = payload.sources;
    renderFileLists();
    overlayStep("Parsing three insurer statements…", 100);
    toast("Demo dataset loaded: 1 register + 3 statements.");
    setStep("mapping");
    renderMapping();
  } catch (error) {
    toast(error.message, true);
  } finally {
    setTimeout(hideOverlay, 240);
  }
}

/* --------------------------------------------------------------- mapping */
function renderMapping() {
  const holder = $("#mapping-cards");
  if (!state.sources.length) {
    holder.innerHTML = `<div class="card"><p class="muted">No files loaded.</p></div>`;
    return;
  }
  holder.innerHTML = state.sources.map((source) => {
    const options = (field) => {
      const blank = `<option value=""${field.column === null ? " selected" : ""}>— not mapped —</option>`;
      return blank + source.columns.map((column) => {
        const selected = field.column === column.index ? " selected" : "";
        return `<option value="${column.index}"${selected}>${escapeHtml(column.label)}</option>`;
      }).join("");
    };
    const rows = source.mapping.map((field) => {
      const confidence = field.column === null ? "c-low" : field.confidence >= 90 ? "c-high" : field.confidence >= 60 ? "c-medium" : "c-low";
      const label = field.column === null ? "not set" : field.confidence >= 90 ? "auto" : "check";
      return `
        <div class="mapping-row ${field.required ? "is-required" : ""}">
          <label class="mapping-field" for="map-${source.id}-${field.key}">
            ${field.required ? '<span class="req" title="Required">*</span>' : ""}
            ${escapeHtml(field.label)}
          </label>
          <select id="map-${source.id}-${field.key}" data-source="${source.id}" data-field="${field.key}"
                  class="${field.column === null && field.required ? "is-empty" : ""}">
            ${options(field)}
          </select>
          <span class="mapping-conf ${confidence}">${label}</span>
        </div>`;
    }).join("");

    const previewHead = source.header.map((h, i) => `<th>${escapeHtml(h || `col ${i + 1}`)}</th>`).join("");
    const previewRows = source.preview.slice(0, 4).map((row) =>
      `<tr>${source.header.map((_, i) => `<td>${escapeHtml(row[i] ?? "")}</td>`).join("")}</tr>`
    ).join("");

    const warnings = (source.meta.warnings || []).map(
      (w) => `<div class="source-warn">${escapeHtml(w)}</div>`
    ).join("");

    return `
      <div class="mapping-card">
        <div class="mapping-head">
          <div class="mapping-title">
            <span class="role-badge">${source.side === "broker" ? "Broker book" : "Statement"}</span>
            <h3>${escapeHtml(source.filename)}</h3>
          </div>
          <div class="mapping-meta">
            <span>${INT.format(source.meta.record_count ?? source.row_count)} lines</span>
            <span>·</span>
            <span>${escapeHtml(source.meta.method || "")}</span>
            <span class="conf conf-${(source.meta.confidence || "medium").toLowerCase()}">${escapeHtml(source.meta.confidence || "")} confidence</span>
            <button class="icon-btn" data-remove="${source.id}" title="Remove file" type="button">✕</button>
          </div>
        </div>
        <div class="mapping-body">${rows}</div>
        ${warnings}
        <div class="preview-wrap">
          <h4>Raw preview</h4>
          <div class="preview-table"><table><thead><tr>${previewHead}</tr></thead><tbody>${previewRows}</tbody></table></div>
        </div>
      </div>`;
  }).join("");

  $$(".mapping-row select").forEach((select) => {
    select.addEventListener("change", (event) => {
      const source = sourceById(event.target.dataset.source);
      const field = source.mapping.find((f) => f.key === event.target.dataset.field);
      const value = event.target.value === "" ? null : Number(event.target.value);
      field.column = value;
      field.header = value === null ? null : source.columns[value].label;
      field.confidence = value === null ? 0 : 100;
      event.target.classList.toggle("is-empty", value === null && field.required);
      const label = event.target.parentElement.querySelector(".mapping-conf");
      label.textContent = value === null ? "not set" : "manual";
      label.className = `mapping-conf ${value === null ? "c-low" : "c-high"}`;
    });
  });
}

/* ------------------------------------------------------------ reconcile */
const OVERLAY_STEPS = [
  ["Reading policy lines", 18],
  ["Normalising policy numbers and dates", 34],
  ["Matching statements to the book", 58],
  ["Applying tolerances and rules", 76],
  ["Classifying and prioritising exceptions", 92],
];

async function runReconcile() {
  if (!state.sources.length) return;
  const mappings = state.sources.map((source) => ({
    id: source.id,
    mapping: Object.fromEntries(source.mapping.map((field) => [field.key, field.column])),
  }));
  const config = {
    premium_abs_tol: Number($("#tol-premium").value || 0),
    commission_abs_tol: Number($("#tol-commission").value || 0),
    date_tol_days: Number($("#tol-days").value || 0),
  };

  showOverlay("Reconciling", OVERLAY_STEPS[0][0], OVERLAY_STEPS[0][1]);
  let index = 1;
  const ticker = setInterval(() => {
    if (index < OVERLAY_STEPS.length) {
      overlayStep(OVERLAY_STEPS[index][0], OVERLAY_STEPS[index][1]);
      index += 1;
    }
  }, 320);

  try {
    const result = await api("/api/reconcile", {
      method: "POST",
      body: JSON.stringify({ mappings, config }),
    });
    clearInterval(ticker);
    overlayStep("Done", 100);
    state.result = result;
    state.filters = { severity: "all", category: "all", search: "" };
    renderResults();
    setStep("results");
    const k = result.kpis;
    toast(`Reconciled ${k.statement_records} statement lines in ${result.elapsed_seconds}s · ${k.exceptions} exceptions.`);
  } catch (error) {
    clearInterval(ticker);
    toast(error.message, true);
  } finally {
    setTimeout(hideOverlay, 220);
  }
}

/* --------------------------------------------------------------- results */
function kpiCard(label, value, sub, tone = "", accent = "") {
  return `
    <div class="kpi ${accent}">
      <div class="kpi-label">${escapeHtml(label)}</div>
      <div class="kpi-value ${tone}">${value}</div>
      <div class="kpi-sub">${sub}</div>
    </div>`;
}

function renderResults() {
  const result = state.result;
  if (!result) return;
  const k = result.kpis;
  const sev = k.by_severity || {};

  $("#results-lede").innerHTML =
    `${INT.format(k.broker_records)} broker policy lines against ${INT.format(k.statement_records)} ` +
    `statement lines from ${result.sources.length} insurer${result.sources.length === 1 ? "" : "s"}. ` +
    `Every difference is listed, priced and given a next action.`;

  $("#kpi-grid").innerHTML = [
    kpiCard(
      "Match rate",
      `${k.match_rate}<small>%</small>`,
      `${k.matched} of ${k.statement_records} statement lines matched · ${k.clean_matches} clean`,
      "tone-accent", "is-accent",
    ),
    kpiCard(
      "Exceptions",
      INT.format(k.exceptions),
      `${sev.high || 0} high · ${sev.medium || 0} medium · ${sev.low || 0} low`,
      k.exceptions ? "tone-high" : "tone-accent",
    ),
    kpiCard(
      "Commission variance",
      moneyShort(k.commission_variance_aed),
      "Net difference on matched policies",
      k.commission_variance_aed < 0 ? "tone-high" : "",
    ),
    kpiCard(
      "Exception exposure",
      moneyShort(k.exposure_aed),
      "Commission in dispute or unaccounted",
      "tone-medium",
    ),
    kpiCard(
      "Unbilled commission",
      moneyShort(k.unbilled_commission_aed),
      "Booked, but not on any statement",
      "tone-high",
    ),
    kpiCard(
      "Unrecognised commission",
      moneyShort(k.unrecognised_commission_aed),
      "On statements, but not in the book",
      "tone-medium",
    ),
    kpiCard(
      "Duplicate exposure",
      moneyShort(k.duplicate_exposure_aed),
      "Commission counted more than once",
    ),
    kpiCard(
      "Manual effort saved (est.)",
      `${k.manual_hours_estimate}<small>h</small>`,
      `At 45s per line across ${INT.format(k.broker_records + k.statement_records)} lines`,
    ),
  ].join("");

  renderCategoryBreakdown(result);
  renderMoneyBreakdown(result);
  renderSourceCards(result);
  renderMatchedTable(result);

  $("#assumptions").innerHTML = (result.assumptions || [])
    .map((note) => `<li>${escapeHtml(note)}</li>`).join("");

  const quality = result.data_quality || [];
  $("#data-quality").innerHTML = quality.length ? quality.map((item) => `
    <div class="dq-box">
      <h4>${escapeHtml(item.filename)} · ${item.skipped_count || 0} row(s) ignored</h4>
      <ul>
        ${(item.skipped || []).slice(0, 4).map((row) => `<li>Row ${row.row_no}: ${escapeHtml(row.reason)}${
          row.values && row.values.length ? ` &mdash; ${escapeHtml(row.values.join(" | ").slice(0, 90))}` : ""
        }</li>`).join("")}
        ${(item.notes || []).slice(0, 4).map((note) => `<li>${escapeHtml(note)}</li>`).join("")}
      </ul>
    </div>`).join("") : "";

  renderExceptions();
}

function renderCategoryBreakdown(result) {
  const categories = result.categories || {};
  const counts = Object.entries(result.kpis.by_category || {}).sort((a, b) => b[1] - a[1]);
  const max = Math.max(...counts.map(([, n]) => n), 1);
  const worst = {};
  (result.findings || []).forEach((finding) => {
    if (!worst[finding.category] || finding.severity === "high") {
      worst[finding.category] = finding.severity;
    }
  });

  $("#category-breakdown").innerHTML = counts.length ? counts.map(([key, count]) => {
    const meta = categories[key] || { label: key };
    const severity = worst[key] || "low";
    return `
      <button class="breakdown-row" data-category="${escapeHtml(key)}" type="button">
        <span class="breakdown-name">${escapeHtml(meta.label)}</span>
        <span class="breakdown-count">${count}</span>
        <span class="breakdown-bar"><span class="sev-${severity}" data-width="${Math.max(6, (count / max) * 100)}"></span></span>
      </button>`;
  }).join("") : `<p class="muted">No exceptions found. Either the book is clean or the mapping needs attention.</p>`;

  // Bar widths are set through the CSSOM rather than inline style attributes so the
  // Content-Security-Policy can keep style-src restricted to first-party stylesheets.
  $$("#category-breakdown .breakdown-bar [data-width]").forEach((bar) => {
    bar.style.width = `${Number(bar.dataset.width)}%`;
  });

  $$("#category-breakdown .breakdown-row").forEach((row) => {
    row.addEventListener("click", () => {
      state.filters = { severity: "all", category: row.dataset.category, search: "" };
      $("#exception-search").value = "";
      $("#category-filter").value = row.dataset.category;
      setStep("exceptions");
      renderExceptions();
    });
  });
}

function renderMoneyBreakdown(result) {
  const k = result.kpis;
  const rows = [
    ["Commission in broker book", k.broker_commission_aed, ""],
    ["Commission on statements", k.statement_commission_aed, ""],
    ["Net commission variance", k.commission_variance_aed, k.commission_variance_aed < 0 ? "neg" : "pos"],
    ["Unbilled (booked, not on statement)", k.unbilled_commission_aed, "neg"],
    ["Unrecognised (statement, not in book)", k.unrecognised_commission_aed, "neg"],
    ["Duplicate commission lines", k.duplicate_exposure_aed, "neg"],
    ["Commission on cancelled policies", k.cancelled_commission_aed, "neg"],
    ["Premium variance on matched policies", k.premium_variance_aed, "neg"],
  ];
  $("#money-breakdown").innerHTML = rows.map(([label, value, tone]) => `
    <div class="money-row">
      <span class="money-label">${escapeHtml(label)}</span>
      <span class="money-value ${tone}">${money(value)}</span>
    </div>`).join("") + `
    <div class="money-row money-total">
      <span class="money-label">Total exception exposure</span>
      <span class="money-value">${money(k.exposure_aed)}</span>
    </div>`;
}

function renderSourceCards(result) {
  $("#source-cards").innerHTML = (result.sources || []).map((source) => {
    const detail = (result.source_details || []).find((d) => d.id === source.source_id) || {};
    const warnings = (detail.warnings || []).map((w) => `<div class="source-warn">${escapeHtml(w)}</div>`).join("");
    return `
      <div class="source-card">
        <h4>${escapeHtml(source.label)}</h4>
        <dl>
          <dt>Insurer</dt><dd>${escapeHtml(source.insurer || "—")}</dd>
          <dt>Statement lines</dt><dd>${INT.format(source.statement_rows)}</dd>
          <dt>Book lines in scope</dt><dd>${INT.format(source.broker_rows_in_scope)}</dd>
          <dt>Matched</dt><dd>${source.matched} (${source.probable_matches} to confirm)</dd>
          <dt>Exceptions</dt><dd>${source.findings}</dd>
          <dt>Read as</dt><dd>${escapeHtml(detail.method || "—")}</dd>
        </dl>
        ${warnings}
      </div>`;
  }).join("");
}

function renderMatchedTable(result) {
  const pairs = result.matched_pairs || [];
  const shown = state.showAllMatched ? pairs : pairs.slice(0, 10);
  $("#matched-lede").textContent =
    `${pairs.length} policy pairs matched on policy key, key variant or a suggested similarity.`;
  $("#matched-table tbody").innerHTML = shown.map((pair) => `
    <tr>
      <td class="mono">${escapeHtml(pair.policy_no)}</td>
      <td>${escapeHtml(pair.insured)}</td>
      <td class="cell-sub">${escapeHtml(pair.insurer || "")}</td>
      <td class="num">${escapeHtml(pair.premium)}</td>
      <td class="num">${escapeHtml(pair.commission)}</td>
      <td><span class="conf ${pair.status === "confirmed" ? "conf-high" : pair.status === "key normalised" ? "conf-medium" : "conf-low"}">${escapeHtml(pair.status)}</span></td>
      <td class="num">${pair.finding_count}</td>
    </tr>`).join("");
  $("#btn-toggle-matched").hidden = pairs.length <= 10;
  $("#btn-toggle-matched").textContent = state.showAllMatched ? "Show less" : `Show all ${pairs.length}`;
}

/* -------------------------------------------------------------- exceptions */
function severityChip(severity) {
  return `<span class="sev-badge sev-${severity}"><span class="dot"></span>${severity}</span>`;
}

function filteredFindings() {
  if (!state.result) return [];
  const { severity, category, search } = state.filters;
  const needle = search.trim().toLowerCase();
  return state.result.findings.filter((finding) => {
    if (severity !== "all" && finding.severity !== severity) return false;
    if (category !== "all" && finding.category !== category) return false;
    if (!needle) return true;
    return [
      finding.policy_no, finding.insured, finding.insurer, finding.category_label,
      finding.broker_value, finding.insurer_value, finding.detail, finding.source_label,
    ].join(" ").toLowerCase().includes(needle);
  });
}

function renderExceptions() {
  if (!state.result) return;
  const counts = state.result.kpis.by_severity || {};
  const total = state.result.findings.length;
  $('[data-count="all"]').textContent = total;
  $('[data-count="high"]').textContent = counts.high || 0;
  $('[data-count="medium"]').textContent = counts.medium || 0;
  $('[data-count="low"]').textContent = counts.low || 0;

  const categories = state.result.categories || {};
  const select = $("#category-filter");
  const current = state.filters.category;
  select.innerHTML = `<option value="all">All exception types</option>` +
    Object.entries(state.result.kpis.by_category || {})
      .sort((a, b) => b[1] - a[1])
      .map(([key, count]) => `<option value="${escapeHtml(key)}">${escapeHtml(categories[key]?.label || key)} (${count})</option>`)
      .join("");
  select.value = current;

  $$("#severity-chips .chip").forEach((chip) => {
    chip.classList.toggle("is-active", chip.dataset.severity === state.filters.severity);
  });

  const findings = filteredFindings();
  $("#exceptions-lede").innerHTML =
    `${findings.length} of ${total} exceptions shown · sorted by severity, then exception type. ` +
    `Click any row for the side-by-side detail and the recommended action.`;

  $("#exception-table tbody").innerHTML = findings.map((finding) => {
    const variance = finding.variance_aed;
    const varianceCell = variance === null || variance === undefined
      ? `<span class="cell-sub">—</span>`
      : `<span class="${variance < 0 ? "variance-neg" : "variance-pos"}">${AED.format(variance)}</span>`;
    return `
      <tr data-finding="${escapeHtml(finding.id)}">
        <td>${severityChip(finding.severity)}</td>
        <td>
          <div class="cat-label">${escapeHtml(finding.category_label)}</div>
          <div class="cell-sub">${escapeHtml(finding.field)} · ${escapeHtml(finding.source_label || "")}</div>
        </td>
        <td class="mono">${escapeHtml(finding.policy_no)}</td>
        <td>
          <div>${escapeHtml(finding.insured || "—")}</div>
          <div class="cell-sub">${escapeHtml(finding.insurer || "")}</div>
        </td>
        <td>${escapeHtml(finding.broker_value || "—")}</td>
        <td>${escapeHtml(finding.insurer_value || "—")}</td>
        <td class="num">${varianceCell}</td>
      </tr>`;
  }).join("");

  $("#exception-empty").hidden = findings.length > 0;
  const COMMISSION_CATEGORIES = new Set([
    "commission_mismatch", "missing_in_insurer", "missing_in_broker",
    "duplicate_in_statement", "status_mismatch", "endorsement_not_in_book",
  ]);
  const commissionExposure = findings
    .filter((finding) => COMMISSION_CATEGORIES.has(finding.category))
    .reduce((total, finding) => total + Math.abs(finding.variance_aed || 0), 0);
  $("#exceptions-foot").textContent = findings.length
    ? `Commission exposure in this view: ${money(commissionExposure)} · premium and cover differences are listed but not priced here.`
    : "";

  $$("#exception-table tbody tr").forEach((row) => {
    row.addEventListener("click", () => openDrawer(row.dataset.finding));
  });
}

function openDrawer(findingId) {
  const finding = state.result.findings.find((item) => item.id === findingId);
  if (!finding) return;
  $("#drawer-kicker").innerHTML = severityChip(finding.severity);
  $("#drawer-title").textContent = finding.category_label;
  const broker = finding.broker_row || {};
  const insurer = finding.insurer_row || {};
  const both = finding.broker_row && finding.insurer_row;

  const contextRows = [
    ["Policy", finding.policy_no],
    ["Insured", finding.insured || "—"],
    ["Insurer", finding.insurer || "—"],
    ["Field compared", finding.field],
    ["Statement file", finding.source_label || "—"],
    ["Book row", broker.row_no ? `#${broker.row_no}` : "—"],
    ["Statement row", insurer.row_no ? `#${insurer.row_no}` : "—"],
    ["Confidence", finding.confidence ? `${finding.confidence}%` : "deterministic"],
  ];

  $("#drawer-body").innerHTML = `
    <div class="drawer-section">
      <div class="compare">
        <div class="compare-box ${both ? "" : "is-suspect"}">
          <div class="cb-label">Broker book</div>
          <div class="cb-value">${escapeHtml(finding.broker_value || "not found")}</div>
        </div>
        <div class="compare-box ${both ? "" : "is-suspect"}">
          <div class="cb-label">Insurer statement</div>
          <div class="cb-value">${escapeHtml(finding.insurer_value || "not found")}</div>
        </div>
      </div>
      ${finding.variance_aed !== null && finding.variance_aed !== undefined ? `
        <p class="muted variance-note">
          Variance in AED:
          <strong class="${finding.variance_aed < 0 ? "variance-neg" : "variance-pos"}">${AED.format(finding.variance_aed)}</strong>
        </p>` : ""}
    </div>

    <div class="drawer-section">
      <h4>What we found</h4>
      <p class="drawer-detail">${escapeHtml(finding.detail)}</p>
    </div>

    <div class="drawer-section">
      <h4>Recommended action</h4>
      <div class="action-box">${escapeHtml(finding.action)}</div>
    </div>

    <div class="drawer-section">
      <h4>Context</h4>
      <dl class="kv">
        ${contextRows.map(([key, value]) => `<dt>${escapeHtml(key)}</dt><dd>${escapeHtml(value)}</dd>`).join("")}
      </dl>
    </div>

    ${both ? `
    <div class="drawer-section">
      <h4>Full record comparison</h4>
      <div class="table-wrap table-wrap-unbounded">
        <table class="data-table">
          <thead><tr><th>Field</th><th>Broker book</th><th>Statement</th></tr></thead>
          <tbody>
            ${[
              ["Policy no", broker.policy_no, insurer.policy_no],
              ["Insured", broker.insured_name, insurer.insured_name],
              ["Class", broker.class_of_business, insurer.class_of_business],
              ["Inception", broker.inception_date, insurer.inception_date],
              ["Expiry", broker.expiry_date, insurer.expiry_date],
              ["Sum insured", broker.sum_insured, insurer.sum_insured],
              ["Premium", broker.premium, insurer.premium],
              ["Commission %", broker.commission_pct, insurer.commission_pct],
              ["Commission", broker.commission_amount, insurer.commission_amount],
              ["Status", broker.status, insurer.status],
            ].map(([label, a, b]) => `
              <tr>
                <td class="cell-sub">${escapeHtml(label)}</td>
                <td>${escapeHtml(a || "—")}</td>
                <td>${escapeHtml(b || "—")}</td>
              </tr>`).join("")}
          </tbody>
        </table>
      </div>
    </div>` : ""}
  `;
  $("#drawer").hidden = false;
  $("#scrim").hidden = false;
}

function closeDrawer() {
  $("#drawer").hidden = true;
  $("#scrim").hidden = true;
}

/* ---------------------------------------------------------------- exports */
async function download(format) {
  if (!state.result) {
    toast("Run a reconciliation before exporting.", true);
    return;
  }
  try {
    const response = await fetch(`/api/export/${format}`, {
      headers: { "X-Session": state.sessionId },
    });
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      throw new Error(payload.detail || "Export failed.");
    }
    const blob = await response.blob();
    const disposition = response.headers.get("content-disposition") || "";
    const match = disposition.match(/filename="?([^"]+)"?/);
    const filename = match ? match[1] : `reconiq-exceptions.${format}`;
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 4000);
    toast(`Exported ${filename}`);
  } catch (error) {
    toast(error.message, true);
  }
}

/* ------------------------------------------------------------------ wiring */
function wire() {
  $$("[data-view]").forEach((button) => {
    button.addEventListener("click", () => navigateView(button.dataset.view));
  });
  $(".app-tabs-inner").addEventListener("keydown", (event) => {
    const tabs = $$(".app-tab");
    const index = tabs.indexOf(event.target);
    if (index < 0) return;
    let next;
    if (event.key === "ArrowRight") next = (index + 1) % tabs.length;
    else if (event.key === "ArrowLeft") next = (index + tabs.length - 1) % tabs.length;
    else if (event.key === "Home") next = 0;
    else if (event.key === "End") next = tabs.length - 1;
    else return;
    event.preventDefault();
    tabs[next].focus();
    navigateView(tabs[next].dataset.view);
  });
  window.addEventListener("hashchange", () => {
    const hash = window.location.hash;
    setView(hash === "#whats-new" ? "whats-new" : hash === "#quality" ? "quality" : "workspace");
  });
  $("#btn-retry-releases").addEventListener("click", loadReleases);

  $$(".dropzone").forEach((zone) => {
    const input = $("input[type=file]", zone);
    ["dragenter", "dragover"].forEach((event) => {
      zone.addEventListener(event, (e) => { e.preventDefault(); zone.classList.add("is-over"); });
    });
    ["dragleave", "drop"].forEach((event) => {
      zone.addEventListener(event, (e) => { e.preventDefault(); zone.classList.remove("is-over"); });
    });
    zone.addEventListener("drop", (e) => {
      if (e.dataTransfer?.files?.length) uploadFiles(e.dataTransfer.files, zone.dataset.side);
    });
    input.addEventListener("change", () => {
      uploadFiles(input.files, zone.dataset.side);
      input.value = "";
    });
  });

  document.addEventListener("click", (event) => {
    const remove = event.target.closest("[data-remove]");
    if (remove) {
      event.preventDefault();
      const id = remove.dataset.remove;
      api(`/api/source/${id}`, { method: "DELETE" })
        .then(() => {
          state.sources = state.sources.filter((source) => source.id !== id);
          state.result = null;
          renderFileLists();
          if (state.step === "mapping") renderMapping();
          if (state.step === "results" || state.step === "exceptions") {
            setStep(state.sources.length ? "mapping" : "files");
            if (state.sources.length) renderMapping();
          }
          if (!state.sources.length) setStep("files");
        })
        .catch((error) => toast(error.message, true));
    }
    const goto = event.target.closest("[data-goto]");
    if (goto) {
      if (goto.dataset.goto === "mapping") renderMapping();
      setStep(goto.dataset.goto);
    }
  });

  $$(".step").forEach((btn) => {
    btn.addEventListener("click", () => {
      if (btn.disabled) return;
      if (btn.dataset.step === "mapping") renderMapping();
      setStep(btn.dataset.step);
    });
  });

  $("#btn-demo").addEventListener("click", loadDemo);
  $("#btn-to-mapping").addEventListener("click", () => { renderMapping(); setStep("mapping"); });
  $("#btn-reconcile").addEventListener("click", runReconcile);
  $("#btn-reset").addEventListener("click", async () => {
    try { await api("/api/reset", { method: "POST" }); } catch (_) { /* ignore */ }
    state.sources = [];
    state.result = null;
    renderFileLists();
    setStep("files");
    toast("Cleared. Load files or the demo dataset to start again.");
  });

  $("#btn-export-xlsx").addEventListener("click", () => download("xlsx"));
  $("#btn-export-xlsx-2").addEventListener("click", () => download("xlsx"));
  $("#btn-export-csv").addEventListener("click", () => download("csv"));

  $("#btn-toggle-matched").addEventListener("click", () => {
    state.showAllMatched = !state.showAllMatched;
    renderMatchedTable(state.result);
  });

  $("#exception-search").addEventListener("input", (event) => {
    state.filters.search = event.target.value;
    renderExceptions();
  });
  $("#category-filter").addEventListener("change", (event) => {
    state.filters.category = event.target.value;
    renderExceptions();
  });
  $$("#severity-chips .chip").forEach((chip) => {
    chip.addEventListener("click", () => {
      state.filters.severity = chip.dataset.severity;
      renderExceptions();
    });
  });

  $("#drawer-close").addEventListener("click", closeDrawer);
  $("#scrim").addEventListener("click", closeDrawer);
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeDrawer();
  });
}

async function init() {
  wire();
  const initialHash = window.location.hash;
  setView(initialHash === "#whats-new" ? "whats-new" : initialHash === "#quality" ? "quality" : "workspace");
  renderFileLists();
  // Public review pages do not require a reconciliation session.
  loadReleases();
  loadQuality();
  loadDemoCatalogue();
  try {
    const session = await api("/api/session", { method: "POST" });
    state.sessionId = session.session_id;
  } catch (error) {
    toast(`Could not start a session: ${error.message}`, true);
  }
}

init();
