import io

import pytest

from reconiq.ingest import IngestError, prepare


def test_broker_csv_reads_all_lines(demo_prepared):
    prepared = demo_prepared["broker_register_sep2026.csv"]
    assert prepared["meta"]["kind"] == "csv"
    assert prepared["meta"]["row_count"] == 40
    assert prepared["mapping"]["policy_no"]["header"] == "Policy No"


def test_xlsx_statement_skips_title_rows_and_total_row(demo_prepared):
    prepared = demo_prepared["GIG_statement_sep2026.xlsx"]
    assert prepared["meta"]["kind"] == "xlsx"
    assert prepared["meta"]["row_count"] == 20  # 19 policy lines + 1 duplicate line
    assert prepared["header"][0] == "Policy No"
    assert prepared["context"]["period"] == "September 2026"
    assert prepared["context"]["statement_no"] == "GIG-ST-2026-0918"
    assert not any("Grand Total" in " ".join(row) for row in prepared["rows"])


def test_ruled_pdf_is_read_as_a_table(demo_prepared):
    prepared = demo_prepared["Orient_statement_sep2026.pdf"]
    assert prepared["meta"]["kind"] == "pdf"
    assert prepared["meta"]["confidence"] == "high"
    assert prepared["meta"]["row_count"] == 12
    assert prepared["context"]["insurer_guess"] == "Orient Insurance PJSC"


def test_pdf_without_grid_falls_back_to_text_columns(demo_prepared):
    prepared = demo_prepared["Sukoon_statement_sep2026.pdf"]
    assert prepared["meta"]["method"] == "pdf text columns"
    assert prepared["meta"]["confidence"] == "medium"
    assert prepared["meta"]["warnings"], "the fallback must warn the user"
    assert prepared["rows"][0][0] == "SKN/PRP/2026/7781"
    assert prepared["mapping"]["premium"]["header"] == "Premium"


def test_scanned_pdf_gets_a_useful_error():
    from reportlab.pdfgen import canvas

    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer)
    pdf.setFont("Helvetica", 10)
    pdf.drawString(72, 720, "This page has a little text but no policy table at all.")
    pdf.save()
    with pytest.raises(IngestError) as excinfo:
        prepare("scan.pdf", buffer.getvalue(), "statement")
    assert "policy table" in str(excinfo.value).lower() or "scan" in str(excinfo.value).lower()


def test_unsupported_file_type_is_rejected():
    with pytest.raises(IngestError):
        prepare("statement.xyz", b"hello", "statement")


def test_legacy_xls_has_a_clear_message():
    with pytest.raises(IngestError) as excinfo:
        prepare("old.xls", b"\xd0\xcf\x11\xe0", "statement")
    assert ".xlsx" in str(excinfo.value)
