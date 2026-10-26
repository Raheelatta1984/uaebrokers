# ReconIQ — insurance brokerage reconciliation prototype

A working V0 of the UAE insurance brokerage automation initiative described in the
initial project plan: **upload a broker policy register and insurer commission statements,
get a prioritised exception list with a recommended action and an exportable workbook.**

This is the prototype that goes into customer-discovery conversations. It is deliberately
narrow, runs locally, and uses synthetic data only — no real broker data, no cloud, no billing,
no multi-tenancy.

```
Broker policy file ─┐
                    ├─► match & validate ─► exception dashboard ─► export / action list
Insurer statements ─┘      (CSV/XLSX/PDF)
```

## Quick start

```bash
./run.sh                 # creates .venv, installs requirements, serves on port 8000
# then open http://localhost:8000
```

Manual equivalent:

```bash
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt
./.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
```

No API keys, no paid services, no external network calls at runtime. Everything is held in
memory and discarded when the process stops.

## What the prototype does

1. **Load files** — a broker policy register (CSV/Excel) and any number of insurer statements
   (CSV, Excel, or PDF, including PDFs with no table grid and a letterhead above the table).
2. **Confirm columns** — the canonical schema is detected automatically and shown with a
   confidence level; anything wrong can be re-mapped by hand, with a raw preview beside it.
3. **Set tolerances** — premium, commission and date tolerances are business policy, so they
   are explicit sliders rather than hidden constants.
4. **Reconcile** — policy-level matching, then field comparison, then exception classification
   and severity.
5. **Act** — KPIs, exception list with filters and search, per-exception side-by-side detail and
   recommended action, plus a three-sheet Excel export (Exceptions / Summary / Matched pairs)
   and a CSV export.

Sixteen exception types are recognised, including the ones brokers actually argue about:
commission shortfalls, premium differences, policies missing from a statement (unbilled
commission), statement lines missing from the book (unrecognised cash), duplicate lines,
cancelled-but-invoiced policies, endorsements not posted, currency mismatches, and probable
matches where the policy number was typed differently.

## What's New and app versions

The **What's New** tab is public and always available — no files or reconciliation
required. Open it from the navigation or go directly to `http://localhost:8000/#whats-new`.
It shows the current version, release dates and a newest-first history of added features,
improvements and fixes. Switching tabs keeps your files, mappings, tolerances, results
and exception filters intact.

Release notes live in [`reconiq/releases.json`](reconiq/releases.json), tracked in Git.
The newest release defines the app version everywhere, including the navigation badge,
`GET /api/releases`, `GET /api/health` and API documentation. To publish a future update,
prepend one entry, use a `MAJOR.MINOR.PATCH` version and include it in the feature PR.
See [the release guide](docs/releases.md) for the format and checks. Restart or redeploy
the app after merging to serve the new notes.

## Quality & incidents review

The **Quality & incidents** tab is a public, read-only review page at `/#quality` (also
available from `GET /api/quality`). It does not require a reconciliation session, create
one, or expose uploaded files. Reviewers can inspect high-level steps, source pytest names,
expected outcomes, and impacts for normalization, schema mapping, ingestion, reconciliation
regression, API integration, and release-history validation.

The page also records the latest repository test-suite snapshot, lists known findings, and
separates the demo's deliberately planted business exceptions from software defects and
operational incidents. Section visibility preferences are stored in the reviewer's browser.
AI guidance is off by default; enabling the preference only displays a local notice because
no AI provider is integrated and no data is sent to one. Live CI status and incident assignment
are shown as unavailable future options, not as implemented capabilities.

The snapshot is a manually maintained record of an actual local `pytest` run, not a live CI
feed or production performance/SLA claim. For the exact current evidence, see the tab and
`reconiq/quality.py`. Test scripts remain in `tests/`; CI runs `python -m pytest tests -q`.

## The demo dataset

`demo_data/` contains the synthetic dataset, and the app loads it with one click:

| File | Format | What it demonstrates |
|------|--------|----------------------|
| `broker_register_sep2026.csv` | CSV | 40 policy lines across 4 insurers |
| `GIG_statement_sep2026.xlsx` | Excel | Title rows, a rate column stored as a fraction, a total row to be ignored |
| `Orient_statement_sep2026.pdf` | PDF (ruled table) | Standard scanned/exported statement with a grid |
| `Sukoon_statement_sep2026.pdf` | PDF (no grid) | Columns are just aligned text — rebuilt from word positions |

With the default tolerances a run produces:

**87.2% match rate · 18 exceptions (6 high / 7 medium / 5 low) · AED 9,710 commission exposure**

| # | Severity | Exception | Policy | Book vs statement | Variance (AED) |
|---|----------|-----------|--------|-------------------|----------------|
| 1 | high | Duplicate on statement | `GIG/2026/000113` | — → 2 rows | 1,125.00 |
| 2 | high | Not in broker book | `GIG/2026/000199` | Not in book → AED 2,800.00 | 2,800.00 |
| 3 | high | Not in broker book | `OIC/MOT/2026/4599` | Not in book → AED 1,375.00 | 1,375.00 |
| 4 | high | Not on insurer statement | `GIG/2026/000112` | AED 800.00 → Not on statement | -800.00 |
| 5 | high | Not on insurer statement | `SKN/PRP/2026/7788` | AED 720.00 → Not on statement | -720.00 |
| 6 | high | Cancelled but invoiced | `GIG/2026/000111` | Cancelled → Active | 2,250.00 |
| 7 | medium | Commission mismatch | `GIG/2026/000110` | AED 1,200.00 → AED 960.00 | -240.00 |
| 8 | medium | Commission mismatch | `OIC/MOT/2026/4511` | AED 750.00 → AED 600.00 | -150.00 |
| 9 | medium | Currency mismatch | `GIG/2026/000107` | AED → USD | — |
| 10 | medium | Duplicate in broker book | `OIC/MOT/2026/4510` | 2 rows → — | — |
| 11 | medium | Probable match - confirm | `OIC/MOT/2026/4508` | `.../4508` → `.../4580` | — |
| 12 | medium | Premium mismatch | `GIG/2026/000109` | AED 12,500.00 → AED 11,900.00 | -600.00 |
| 13 | medium | Sum insured mismatch | `GIG/2026/000114` | 1,000,000 → 750,000 | -250,000.00 |
| 14 | low | Period mismatch | `OIC/MOT/2026/4509` | 01/03/2026 → 15/03/2026 | — |
| 15 | low | Endorsement not in book | `GIG/2026/000312/E1` | — → AED 250.00 | 250.00 |
| 16 | low | Insurer not covered | 2 policies | Takaful Emarat: no statement uploaded | — |
| 17 | low | Insured name mismatch | `GIG/2026/000115` | Emirates Logistics LLC → …& Transport LLC | — |
| 18 | low | Premium mismatch | `SKN/PRP/2026/7787` | AED 11,035.00 → AED 11,070.00 | 35.00 |

That table is the "expected result" checklist for a live demo — and the basis of
`tests/test_engine.py::test_demo_dataset_surfaces_the_planted_exceptions`, so the demo cannot
silently drift from what the presenter promises.

A step-by-step talk track is in [`docs/demo-script.md`](docs/demo-script.md).

## How the matching works

**Matching is staged, and each stage is only trusted as far as it deserves:**

1. **Exact policy key** — alphanumerics only, upper-cased (`GIG/2026/000451` = `GIG-2026-451`).
2. **Key variants** — removes zero-padding and redundant separators, but *only* accepts the
   pair when the insured name or the premium also agrees, so a variant can never invent a match.
3. **Probable match** — blocked on premium/name/insurer, scored on name similarity, premium
   closeness and date proximity. Always surfaced as *"confirm this pair"*, never applied silently.
4. **Nothing else** — an unmatched book line is reported as missing from the statement, and an
   unmatched statement line as missing from the book. No guessing.

**Insurer scoping matters.** A broker book covers many insurers; a statement covers one. If a
statement has no readable insurer, it is inferred from the policies that do match, so a
statement for Orient cannot generate hundreds of false "missing" exceptions for GIG policies.
If the insurer still cannot be determined, policies are not silently dropped — the reconciliation
reports which insurers had no statement at all.

**Rules that avoid noise, not just rules that find problems:**

- A commission gap fully explained by a premium difference (statement commission = statement
  premium × booked rate) is not reported twice.
- `AED 35` is left to the tolerance slider, not escalated as a finance issue.
- Commission rate differences below 0.25 points do not raise a separate exception when the
  amount already does.
- Key-format differences that are pure formatting are matched quietly and counted as
  `key normalised`, not reported as exceptions.

**Severity** is derived from money at stake: commission shortfalls above AED 500 are high;
premium differences above AED 1,000 or 5% are high; duplicates on a statement, unrecognised
statement lines and cancelled-but-invoiced commission are always high. Severity is a starting
priority, and the thresholds are in one place in `reconiq/engine.py`.

## Reading real files

- **CSV/TSV** — delimiter sniffed; blank rows and total rows dropped.
- **Excel** — most-populated sheet, header row found beneath letterhead/title rows, formulas read
  as cached values, `Grand Total` style rows excluded.
- **PDF with a table grid** — extraction via `pdfplumber` table strategies.
- **PDF without a table grid** — columns rebuilt by clustering cell positions from word
  geometry. Reported as *medium confidence* with an explicit warning, because this is the
  method most likely to be subtly wrong.
- **Scanned PDF** — refused with a clear message asking for OCR or the CSV/Excel statement,
  rather than producing an empty reconciliation.
- **Dates** are read day-first (`DD/MM/YYYY`), the UAE convention. **Commission rates** below 1
  are treated as fractions (`0.125` → 12.5%). **Currencies** other than AED are converted at an
  indicative rate table (1 USD = 3.6725 AED) and the mismatch is flagged, since the rate used
  is an assumption that should be visible.

Limits: 20 MB / 20,000 rows per file, 8 files per upload, in-memory only.

## Repository layout

```
reconiq/
  normalize.py   value parsing: money, percentages, dates, keys, names, currencies
  schema.py      canonical fields + column auto-detection
  ingest.py      CSV / Excel / PDF ingestion and header discovery
  engine.py      matching, comparison rules, severity, KPIs  (pure, no I/O)
  demo.py        synthetic UAE demo dataset + the three statement formats
  releases.json  public release history (newest entry defines the app version)
  releases.py    changelog loading and validation
app/
  main.py        FastAPI app: sessions, upload, reconcile, exports
  static/        index.html, styles.css, app.js  (no build step)
demo_data/       the generated demo files, ready to drag into the app
tests/           parsing, mapping, ingestion, engine rules, API and release-history tests
docs/            demo script and release-publishing guide
.github/         continuous integration for pull requests and main
```

The engine has no framework, database or file-system dependency — that is intentional, because
the plan calls for the matching core to be reusable outside insurance.

## Tests

```bash
./.venv/bin/python -m pytest tests -q
```

They cover the parsing traps that break real reconciliations (percentage precision, day-first
dates, zero-padded keys, dotted legal suffixes), column detection traps (`Commission %` vs
`Commission Amount`, VAT not being a rate), ingestion of all three statement formats, every
exception category in the demo dataset, tolerance sensitivity, and the API including export
files and the failure paths (bad mapping, empty statement, unsupported file). Release-history
tests also validate semantic versions, date ordering, required notes, public read-only access
and version consistency. GitHub Actions runs the full suite on pull requests and `main`.

## Deliberately not built (V0 scope)

Multi-tenancy, billing, real user management and permissions, insurer APIs, a mobile app, AI
agents, a case-management workflow with assignment/SLA tracking, and any cloud infrastructure.
Those wait for a paid pilot, exactly as the project plan sets out.

## What the next conversation should decide

1. **Is reconciliation the wedge, or is it renewals/document automation?** The prototype is the
   artefact that starts that conversation; it is not the conclusion.
2. **Does the broker's BMS already do this?** The honest answer may be "partly" — in which case
   the value is multi-insurer, multi-format reconciliation and exception *tracking*, not
   reconciliation itself.
3. **Who owns the budget** — finance, operations, IT or the MD — and therefore what the first
   paid engagement looks like.
4. **What data can be used in a pilot**, and what data-residency expectation applies before any
   real commission data leaves the broker's premises.
5. **Would a PDF-only statement realistically be accepted as input in the pilot**, or does the
   broker's own insurer correspondence need to be normalised first?

## Data handling

The demo uses synthetic data generated by `reconiq/demo.py`, with plausible UAE insured names
and realistic insurer statement layouts. Nothing is sent to a third party, nothing is written to
disk by the app, and sessions are discarded when the process stops. Real data in a pilot would
need a separate conversation about residency, retention and anonymisation.
