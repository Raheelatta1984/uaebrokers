from decimal import Decimal

import pytest

from reconiq import demo
from reconiq.engine import Config, build_records, reconcile


def categories(result):
    return result["kpis"]["by_category"]


def test_demo_dataset_surfaces_the_planted_exceptions(demo_result):
    found = categories(demo_result)
    expected = demo.expected_exceptions()
    for category, count in expected.items():
        assert found.get(category, 0) == count, (
            f"{category}: expected {count}, found {found.get(category, 0)}"
        )
    assert demo_result["kpis"]["exceptions"] == sum(expected.values())


def test_no_false_missing_exceptions_from_insurer_scoping(demo_result):
    """Every 'missing' finding must be one of the deliberately planted ones."""
    policies = {
        finding["policy_no"]
        for finding in demo_result["findings"]
        if finding["category"] in {"missing_in_insurer", "missing_in_broker"}
    }
    assert policies == {
        "GIG/2026/000112", "SKN/PRP/2026/7788",   # in book, not on statement
        "GIG/2026/000199", "OIC/MOT/2026/4599",   # on statement, not in book
    }


def test_commission_shortfall_is_priced(demo_result):
    finding = next(
        f for f in demo_result["findings"]
        if f["category"] == "commission_mismatch" and f["policy_no"] == "GIG/2026/000110"
    )
    assert finding["variance_aed"] == -240.0
    assert finding["severity"] == "medium"
    assert "shortfall" in finding["detail"].lower()


def test_commission_gap_explained_by_premium_is_not_double_reported(demo_result):
    """000109's commission differs only because the premium differs."""
    per_policy = [
        f["category"] for f in demo_result["findings"]
        if f["policy_no"] == "GIG/2026/000109"
    ]
    assert per_policy == ["premium_mismatch"]


def test_key_formatting_difference_matches_without_an_exception(demo_result):
    pairs = [p for p in demo_result["matched_pairs"] if p["policy_no"] == "GIG/2026/000451"]
    assert pairs and pairs[0]["status"] == "key normalised"
    assert not [
        f for f in demo_result["findings"] if f["policy_no"] == "GIG/2026/000451"
    ]


def test_true_typo_becomes_a_probable_match_to_confirm(demo_result):
    finding = next(
        f for f in demo_result["findings"] if f["category"] == "low_confidence_match"
    )
    assert finding["policy_no"] == "OIC/MOT/2026/4508"
    assert finding["insurer_value"] == "OIC/MOT/2026/4580"
    assert finding["confidence"] and finding["confidence"] >= 60


def test_cancelled_policy_still_invoiced_is_high_severity(demo_result):
    finding = next(f for f in demo_result["findings"] if f["category"] == "status_mismatch")
    assert finding["severity"] == "high"
    assert finding["variance_aed"] == 2250.0


def test_multi_currency_line_is_compared_in_aed(demo_result):
    finding = next(
        f for f in demo_result["findings"]
        if f["category"] == "currency_mismatch" and f["policy_no"] == "GIG/2026/000107"
    )
    assert finding["broker_value"] == "AED"
    assert finding["insurer_value"] == "USD"
    # 12,254.59 USD at 3.6725 is ~45,000 AED, so no premium exception on top
    assert not [
        f for f in demo_result["findings"]
        if f["policy_no"] == "GIG/2026/000107" and f["category"] == "premium_mismatch"
    ]


def test_insurer_without_a_statement_is_reported_as_unreconciled(demo_result):
    finding = next(
        f for f in demo_result["findings"] if f["category"] == "insurer_not_in_statements"
    )
    assert "Takaful Emarat" in finding["insurer"]


def test_findings_are_sorted_high_first(demo_result):
    order = {"high": 0, "medium": 1, "low": 2}
    severities = [order[f["severity"]] for f in demo_result["findings"]]
    assert severities == sorted(severities)


def test_exposure_uses_commission_only(demo_result):
    kpis = demo_result["kpis"]
    assert kpis["unbilled_commission_aed"] == 1520.0
    assert kpis["unrecognised_commission_aed"] == 4175.0
    assert kpis["exposure_aed"] == 9710.0


def test_raising_tolerance_removes_small_differences(demo_files, demo_prepared):
    broker_source = "broker_register_sep2026.csv"
    broker, _, _ = build_records(
        broker_source, "broker",
        demo_prepared[broker_source]["rows"], demo_prepared[broker_source]["mapping"],
    )
    statements = []
    for name in demo_prepared:
        if name == broker_source:
            continue
        records, _, _ = build_records(
            name, "statement", demo_prepared[name]["rows"], demo_prepared[name]["mapping"]
        )
        statements.append({"source_id": name, "label": name, "records": records})

    strict = reconcile(broker, statements, Config())
    loose = reconcile(broker, statements, Config(premium_abs_tol=Decimal("100")))
    assert categories(loose).get("premium_mismatch", 0) < categories(strict).get(
        "premium_mismatch", 0
    )


def test_empty_statement_is_an_error_not_a_wall_of_false_exceptions(demo_prepared):
    broker_source = "broker_register_sep2026.csv"
    broker, _, _ = build_records(
        broker_source, "broker",
        demo_prepared[broker_source]["rows"], demo_prepared[broker_source]["mapping"],
    )
    with pytest.raises(ValueError) as excinfo:
        reconcile(broker, [{"source_id": "empty", "label": "GIG", "records": []}])
    assert "no policy lines" in str(excinfo.value)
