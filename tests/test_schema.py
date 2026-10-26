from reconiq.schema import detect_columns, header_row_index, mapping_ready


def mapping_of(header, rows=None):
    return {k: v["column"] for k, v in detect_columns(header, rows or []).items()}


def test_standard_statement_headers():
    header = ["Policy No", "Insured Name", "Inception", "Expiry", "Sum Insured",
              "Gross Premium", "Comm %", "Commission Amount", "Status"]
    mapping = mapping_of(header)
    assert mapping["policy_no"] == 0
    assert mapping["insured_name"] == 1
    assert mapping["inception_date"] == 2
    assert mapping["expiry_date"] == 3
    assert mapping["sum_insured"] == 4
    assert mapping["premium"] == 5
    assert mapping["commission_pct"] == 6
    assert mapping["commission_amount"] == 7
    assert mapping["status"] == 8


def test_rate_column_is_not_taken_by_commission_amount():
    """'Commission %' must map to the rate, never to the amount, whatever the order."""
    header = ["Policy No", "Gross Premium", "Commission %", "Commission Amount"]
    mapping = mapping_of(header)
    assert mapping["commission_pct"] == 2
    assert mapping["commission_amount"] == 3


def test_bare_commission_header_is_an_amount():
    header = ["Policy No", "Premium", "Commission"]
    mapping = mapping_of(header)
    assert mapping["commission_amount"] == 2
    assert mapping["commission_pct"] is None


def test_commission_rate_wording_variants():
    for header_text in ("Comm. Rate", "Brokerage %", "Rate %", "Commission Rate"):
        mapping = mapping_of(["Policy No", "Premium", header_text])
        assert mapping["commission_pct"] == 2, header_text


def test_vat_and_stamp_duty_are_not_rates():
    mapping = mapping_of(["Policy No", "Premium", "VAT %"])
    assert mapping["commission_pct"] is None


def test_money_semantics_are_not_guessed_from_vague_headers():
    """'Amount' could be premium or sum insured - we leave it to the user."""
    rows = [["GIG/2026/1", "24,000,000"], ["GIG/2026/2", "18,500,000"]]
    mapping = mapping_of(["Policy No", "Amount"], rows)
    assert mapping["premium"] is None
    assert mapping["sum_insured"] is None


def test_clear_sum_insured_and_premium_headers_both_map():
    mapping = mapping_of(["Policy No", "Sum Insured", "Gross Premium"])
    assert mapping["sum_insured"] == 1
    assert mapping["premium"] == 2


def test_header_row_discovery_skips_letterhead_and_title_rows():
    rows = [
        ["GIG Gulf"],
        ["Broker Commission Statement"],
        ["Statement No: GIG-ST-2026-0918   Period: September 2026"],
        [],
        ["Policy No", "Insured Name", "Gross Premium", "Commission Amount"],
        ["GIG/2026/1", "Al Habtoor Engineering LLC", "42,500.00", "5,312.50"],
    ]
    assert header_row_index(rows) == 4


def test_mapping_ready_requires_policy_and_premium():
    mapping = detect_columns(["Insured", "Commission Amount"])
    ready, missing = mapping_ready(mapping)
    assert not ready
    assert "Policy Number" in missing and "Gross Premium" in missing
