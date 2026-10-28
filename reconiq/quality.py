"""Public, truthful quality and incident-management information for ReconIQ.

This is a reviewable test catalogue, not a claim of production monitoring. The
verification snapshot is updated after the repository test suite is run.
"""

QUALITY = {
    "purpose": "Provide a transparent, reproducible record of ReconIQ's automated checks, test scenarios, known findings, and operational incidents.",
    "guide": [
        "Choose a section to review its purpose, scenario steps, referenced pytest scripts, and expected impact.",
        "The latest verification snapshot describes an actual local pytest run; it is not a live CI feed.",
        "Synthetic reconciliation exceptions are expected business findings planted in demo data, not software defects.",
        "An empty incident register means no incidents are recorded in this prototype; it does not prove production uptime.",
    ],
    "verification": {
        "status": "verified",
        "command": "python -m pytest tests -q",
        "result": "121 passed, 1 warning in 3.08s",
        "passed": 121,
        "failed": 0,
        "warnings": 1,
        "duration_seconds": 3.08,
        "recorded_at": "2026-10-28T10:35:18Z",
        "scope": "Local repository test suite; synthetic fixtures; not a CI or production-monitoring result.",
        "warning_detail": "Starlette deprecation warning: its TestClient currently uses httpx; upstream recommends httpx2.",
        "performance_note": "Suite wall-clock time is an environment-specific test-run measurement, not a production latency or throughput benchmark.",
    },
    "suites": [
        {
            "id": "normalization", "name": "Value normalization", "kind": "Unit", "file": "tests/test_normalize.py",
            "purpose": "Check conversion of raw spreadsheet values into stable policy, date, money, currency, and name values.",
            "scripts": ["test_parse_money", "test_parse_money_blank", "test_parse_percent_does_not_lose_precision", "test_parse_date_day_first", "test_key_variants_absorb_zero_padding_but_not_typos", "test_endorsement_parent_returns_canonical_parent", "test_insurer_similarity_ignores_generic_words", "test_name_similarity_tolerates_legal_suffixes", "test_money_close_uses_both_tolerances", "test_to_aed_uses_rate_table"],
            "steps": ["Feed valid, blank, malformed, and boundary values to the parsing helpers.", "Compare normalized results with UAE date and currency conventions.", "Check near-matches and key variants do not silently absorb real policy typos."],
            "expected": "Values normalize consistently; invalid or blank values stay safe; true policy-number typos remain distinct.",
            "impact": "Prevents bad input normalization from becoming a false match or incorrect financial comparison.",
        },
        {
            "id": "schema", "name": "Column schema and mapping", "kind": "Unit", "file": "tests/test_schema.py",
            "purpose": "Verify column discovery distinguishes amounts, rates, taxes, premiums, and policy identifiers.",
            "scripts": ["test_standard_statement_headers", "test_rate_column_is_not_taken_by_commission_amount", "test_bare_commission_header_is_an_amount", "test_commission_rate_wording_variants", "test_vat_and_stamp_duty_are_not_rates", "test_money_semantics_are_not_guessed_from_vague_headers", "test_clear_sum_insured_and_premium_headers_both_map", "test_header_row_discovery_skips_letterhead_and_title_rows", "test_mapping_ready_requires_policy_and_premium"],
            "steps": ["Provide common and ambiguous statement header labels.", "Check header discovery below title and letterhead rows.", "Confirm a mapping is ready only when required policy and premium fields exist."],
            "expected": "Amounts and percentages map to the correct canonical fields; ambiguous semantics are not guessed.",
            "impact": "Reduces silent reconciliation errors caused by selecting the wrong source column.",
        },
        {
            "id": "ingestion", "name": "File ingestion", "kind": "Unit / integration", "file": "tests/test_ingest.py",
            "purpose": "Exercise supported broker and insurer source formats and clear rejection paths.",
            "scripts": ["test_broker_csv_reads_all_lines", "test_xlsx_statement_skips_title_rows_and_total_row", "test_ruled_pdf_is_read_as_a_table", "test_pdf_without_grid_falls_back_to_text_columns", "test_scanned_pdf_gets_a_useful_error", "test_unsupported_file_type_is_rejected", "test_legacy_xls_has_a_clear_message"],
            "steps": ["Parse synthetic CSV, Excel, ruled-PDF, and text-aligned PDF fixtures.", "Check headers and row counts while excluding totals and title rows.", "Submit scanned, unsupported, and legacy workbook formats and inspect their errors."],
            "expected": "Supported demo formats produce usable rows and mappings; unsupported/scanned inputs fail with actionable messages.",
            "impact": "Protects against empty, misread, or misleading imports before finance users rely on results.",
        },
        {
            "id": "reconciliation", "name": "Reconciliation rules and regression", "kind": "Unit / regression", "file": "tests/test_engine.py",
            "purpose": "Check matching, exception classification, severity, exposure, insurer scope, and tolerance behavior.",
            "scripts": ["test_demo_dataset_surfaces_the_planted_exceptions", "test_no_false_missing_exceptions_from_insurer_scoping", "test_commission_shortfall_is_priced", "test_commission_gap_explained_by_premium_is_not_double_reported", "test_key_formatting_difference_matches_without_an_exception", "test_true_typo_becomes_a_probable_match_to_confirm", "test_cancelled_policy_still_invoiced_is_high_severity", "test_multi_currency_line_is_compared_in_aed", "test_insurer_without_a_statement_is_reported_as_unreconciled", "test_findings_are_sorted_high_first", "test_exposure_uses_commission_only", "test_raising_tolerance_removes_small_differences", "test_empty_statement_is_an_error_not_a_wall_of_false_exceptions"],
            "steps": ["Reconcile the deterministic synthetic broker register with three insurer statements.", "Assert planted exception categories and totals, plus key match/no-match edge cases.", "Change tolerance and insurer coverage inputs to detect noisy or missing findings."],
            "expected": "Demo regression expectations hold (18 seeded findings; 34 matched policies); only commission exposure is counted and findings are severity-sorted.",
            "impact": "Guards the core financial reconciliation logic and prevents known false positives from returning.",
        },
        {
            "id": "api", "name": "API, session, and export flows", "kind": "Integration / smoke", "file": "tests/test_api.py",
            "purpose": "Exercise the user-facing HTTP routes end-to-end using FastAPI's test client.",
            "scripts": ["test_index_and_static_assets", "test_quality_tab_is_in_app_shell", "test_quality_catalogue_is_public_and_describes_test_evidence", "test_quality_catalogue_is_read_only", "test_release_history_is_public_without_creating_sessions", "test_release_history_does_not_change_reconciliation_work", "test_application_version_is_consistent_in_api_metadata", "test_release_history_is_read_only", "test_demo_end_to_end", "test_exports_are_valid_files", "test_export_before_reconciling_is_rejected", "test_reconcile_without_files_is_rejected", "test_upload_broker_only_cannot_reconcile", "test_upload_rejects_unsupported_type", "test_bad_mapping_is_caught_instead_of_producing_silent_nonsense", "test_statement_with_no_policy_lines_is_rejected", "test_source_can_be_removed", "test_demo_file_download"],
            "steps": ["Request the app and static assets, then create a session and load synthetic demo files.", "Reconcile and validate returned KPIs, findings, data-quality details, and export contents.", "Try invalid upload, mapping, empty input, and precondition paths; check safe status codes."],
            "expected": "Healthy routes produce expected payloads and files; bad input is rejected clearly without fabricated results.",
            "impact": "Validates browser-to-service flows, export usability, and defensive API behavior.",
        },
        {
            "id": "release-history", "name": "Release history validation", "kind": "Unit / contract", "file": "tests/test_releases.py",
            "purpose": "Check public release metadata for ordering, completeness, and semantic-version correctness.",
            "scripts": ["test_changelog_is_valid_and_defines_the_application_version", "test_original_release_is_kept_in_the_history", "test_versions_use_a_simple_semantic_version", "test_duplicate_or_out_of_order_versions_are_rejected", "test_versions_are_compared_numerically_not_alphabetically", "test_dates_must_be_real_iso_calendar_dates", "test_dates_must_be_newest_first", "test_release_metadata_cannot_be_missing", "test_history_requires_release_objects", "test_release_changes_are_validated", "test_change_fields_cannot_be_blank"],
            "steps": ["Load the tracked release history and validate each release record.", "Exercise malformed, duplicate, out-of-order versions and dates.", "Confirm public route access is read-only and application versions agree."],
            "expected": "Well-formed newest-first history matches app metadata; incomplete or invalid entries are rejected.",
            "impact": "Keeps public change records dependable for reviewers and users.",
        },
        {
            "id": "security", "name": "Browser security controls", "kind": "Integration / regression guard", "file": "tests/test_security.py",
            "purpose": "Check the security headers and Content-Security-Policy on every route, the no-store rule for API data, the production flag that hides the API docs, and guard against credentials or unescaped values reaching browser JavaScript.",
            "scripts": ["test_security_headers_are_sent_on_every_kind_of_route", "test_content_security_policy_is_strict_first_party_only", "test_app_shell_has_no_inline_scripts_styles_or_handlers", "test_api_responses_are_never_cached_but_static_assets_may_be", "test_api_docs_are_available_locally_with_a_policy_limited_to_the_swagger_cdn", "test_production_flag_disables_api_docs_and_enables_https_only_headers", "test_browser_code_never_stores_credentials_in_web_storage_or_js_cookies", "test_escape_helper_neutralises_html_metacharacters", "test_user_controlled_values_are_escaped_before_reaching_innerhtml"],
            "steps": ["Request the app shell, API, static and unknown routes and compare every security header with the expected value.", "Load the demo, reconcile and export, confirming API responses are marked no-store while static assets are not.", "Start the app with RECONIQ_ENV=production in a subprocess and confirm the docs page is gone and HTTPS-only headers appear.", "Statically scan the browser code for credential-like storage use, JavaScript-set cookies, inline scripts or styles, and data-bearing fields interpolated without escapeHtml()."],
            "expected": "A strict first-party Content-Security-Policy and companion headers on all routes; uploaded data never cacheable; docs hidden in production; the session id stays in memory and all file-derived values are escaped.",
            "impact": "Blocks the common cross-site scripting exfiltration path (steal a token from browser storage, post it to another origin) and stops regressions from reintroducing it.",
        },
    ],
    "findings": [
        {
            "id": "seeded-demo-findings", "type": "Test fixture / expected business findings", "severity": "Informational", "status": "Expected",
            "summary": "The synthetic demo deliberately contains 18 reconciliation exceptions, including duplicate, missing, and mismatched policy lines.",
            "evidence": "test_demo_dataset_surfaces_the_planted_exceptions; documented demo expectation: AED 9,710 commission exposure.",
            "resolution": "No software fix is indicated: these are seeded inputs that exercise exception detection. The regression test pins the expected output.",
        },
        {
            "id": "test-client-deprecation", "type": "Test tooling warning", "severity": "Low", "status": "Open / monitor", 
            "summary": "The local test run emits one upstream Starlette deprecation warning because TestClient uses httpx.",
            "evidence": "pytest warning summary from the recorded run; application tests still pass.",
            "resolution": "No application defect identified. Monitor the upstream testing stack and update dependencies when compatible; do not suppress the warning.",
        },
        {
            "id": "software-defects", "type": "Software defects", "severity": "—", "status": "None found in recorded run",
            "summary": "No failing tests or confirmed product defects were identified by the recorded automated suite.",
            "evidence": "0 failed in the recorded local pytest run. This statement is limited to the checks listed here.",
            "resolution": "Not applicable. Manual testing, security review, and production monitoring are not represented by this result.",
        },
    ],
    "incidents": [],
    "incident_note": "No incidents have been logged in this prototype. There is no production incident feed, on-call process, SLA, or durable case-management backend.",
    "features": [
        {"id": "ai-guidance", "name": "AI guidance", "available": False, "default_enabled": False, "note": "AI is not connected in this prototype. Turning this preference on only displays the local scope notice; it does not send test or reconciliation data to an AI service."},
        {"id": "live-ci", "name": "Live CI status", "available": False, "default_enabled": False, "note": "Future option: connect a trusted CI provider before exposing live workflow results."},
        {"id": "incident-workflow", "name": "Incident assignment and SLA tracking", "available": False, "default_enabled": False, "note": "Future option: add an authenticated, durable incident-management service."},
    ],
}
