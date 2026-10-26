"""Synthetic demo dataset.

Why synthetic: the plan is explicit that no real broker data is used before a
signed pilot, and commission data is commercially sensitive. This module builds
a believable UAE broker book plus three insurer statements in three different
formats, with a known set of exceptions planted so the demo can be narrated
("there are eleven problems in here - let's find them in ninety seconds").

Everything is deterministic: same files, same numbers, every time.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal

BROKER_NAME = "Gulf Crest Insurance Brokers LLC"
STATEMENT_PERIOD = "September 2026"

GIG = "GIG Gulf"
ORIENT = "Orient Insurance PJSC"
SUKOON = "Sukoon Insurance"
TAKAFUL = "Takaful Emarat"


@dataclass
class Policy:
    policy_no: str
    insured: str
    insurer: str
    cob: str
    inception: date
    expiry: date
    sum_insured: int
    premium: float
    rate: float
    currency: str = "AED"
    status: str = "Active"
    class_code: str = ""

    @property
    def commission(self) -> float:
        return round(self.premium * self.rate / 100, 2)


def _d(day: int, month: int) -> date:
    return date(2026, month, day)


def _policy(no, insured, insurer, cob, inc, exp, si, premium, rate, **kw) -> Policy:
    return Policy(no, insured, insurer, cob, inc, exp, si, premium, rate, **kw)


def broker_book() -> list[Policy]:
    """The broker's own policy register."""
    rows = [
        # --- GIG Gulf -------------------------------------------------------
        _policy("GIG/2026/000101", "Al Habtoor Engineering LLC", GIG, "Engineering", _d(1, 1), _d(31, 12), 5_000_000, 42_500, 12.5),
        _policy("GIG/2026/000102", "Meraas Facilities Management", GIG, "Property", _d(1, 1), _d(31, 12), 12_000_000, 36_000, 15),
        _policy("GIG/2026/000103", "Aswaaq Retail Group", GIG, "Property", _d(15, 1), _d(14, 1), 8_500_000, 28_750, 12.5),
        _policy("GIG/2026/000104", "Bin Ghanim Transport LLC", GIG, "Motor Fleet", _d(1, 2), _d(31, 1), 3_200_000, 61_400, 10),
        _policy("GIG/2026/000105", "Oasis Medical Centre", GIG, "Medical Malpractice", _d(1, 3), _d(28, 2), 2_000_000, 18_000, 15),
        _policy("GIG/2026/000106", "Sharjah Steel Industries", GIG, "Marine Cargo", _d(1, 4), _d(31, 3), 7_500_000, 24_900, 12.5),
        _policy("GIG/2026/000107", "Falcon Hospitality Group", GIG, "Property", _d(1, 5), _d(30, 4), 15_000_000, 45_000, 15),
        _policy("GIG/2026/000108", "Dune Security Services", GIG, "Liability", _d(1, 6), _d(31, 5), 1_000_000, 9_600, 15),
        # premium overstated in the broker book
        _policy("GIG/2026/000109", "Reem Island Contracting", GIG, "Engineering", _d(1, 1), _d(31, 12), 4_000_000, 12_500, 12.5),
        # commission short-paid by insurer
        _policy("GIG/2026/000110", "Arabian Cement Works", GIG, "Property", _d(1, 2), _d(31, 1), 6_000_000, 8_000, 15),
        # cancelled in the book, still invoiced by insurer
        _policy("GIG/2026/000111", "Marina Yacht Club", GIG, "Marine Hull", _d(1, 1), _d(31, 12), 2_500_000, 15_000, 15, status="Cancelled"),
        # not on the insurer statement at all
        _policy("GIG/2026/000112", "Nakheel Community Services", GIG, "Liability", _d(1, 7), _d(30, 6), 3_000_000, 6_400, 12.5),
        # duplicated on the insurer statement
        _policy("GIG/2026/000113", "Dubai Frame Attractions", GIG, "Property", _d(1, 3), _d(28, 2), 9_000_000, 9_000, 12.5),
        # key formatting differs between systems
        _policy("GIG/2026/000451", "Horizon Tech Park", GIG, "Engineering", _d(1, 8), _d(31, 7), 11_000_000, 33_000, 12.5),
        # parent policy that receives an endorsement on the statement
        _policy("GIG/2026/000312", "Ras Al Khaimah Quarry", GIG, "Engineering", _d(1, 5), _d(30, 4), 6_500_000, 20_000, 12.5),
        # sum insured understated on the statement
        _policy("GIG/2026/000114", "Jumeirah Retail Holdings", GIG, "Property", _d(1, 4), _d(31, 3), 1_000_000, 7_500, 15),
        # insured name differs on the statement
        _policy("GIG/2026/000115", "Emirates Logistics LLC", GIG, "Marine Cargo", _d(1, 6), _d(31, 5), 4_500_000, 14_400, 12.5),
        # priced in USD on both sides
        _policy("GIG/2026/000116", "Global Freight Partners FZE", GIG, "Marine Cargo", _d(1, 7), _d(30, 6), 3_600_000, 4_901.29, 15, currency="USD"),
        # --- Orient Insurance ----------------------------------------------
        _policy("OIC/MOT/2026/4501", "Al Ghurair Foods LLC", ORIENT, "Motor Fleet", _d(1, 1), _d(31, 12), 4_200_000, 54_000, 10),
        _policy("OIC/MOT/2026/4502", "Union Coop Hypermarkets", ORIENT, "Property", _d(1, 1), _d(31, 12), 20_000_000, 52_000, 12.5),
        _policy("OIC/MOT/2026/4503", "ENOC Retail Stations", ORIENT, "Liability", _d(1, 2), _d(31, 1), 5_000_000, 21_500, 15),
        _policy("OIC/MOT/2026/4504", "Dubai Investments Park", ORIENT, "Property", _d(1, 3), _d(28, 2), 18_000_000, 43_200, 12.5),
        _policy("OIC/MOT/2026/4505", "Al Rostamani Trading", ORIENT, "Motor Fleet", _d(1, 4), _d(31, 3), 2_800_000, 39_000, 10),
        _policy("OIC/MOT/2026/4506", "National Catering Company", ORIENT, "Medical", _d(1, 5), _d(30, 4), 1_500_000, 26_400, 12.5),
        _policy("OIC/MOT/2026/4507", "Rivoli Group Retail", ORIENT, "Property", _d(1, 6), _d(31, 5), 6_200_000, 17_800, 12.5),
        # inception date differs on the statement by two weeks
        _policy("OIC/MOT/2026/4509", "Emirates Steel Rolling", ORIENT, "Engineering", _d(1, 3), _d(28, 2), 9_500_000, 29_400, 12.5),
        # one digit typo on the statement - should surface as a probable match
        _policy("OIC/MOT/2026/4508", "Khadamat Facilities LLC", ORIENT, "Property", _d(1, 7), _d(30, 6), 5_400_000, 16_200, 12.5),
        # duplicated inside the broker's own book
        _policy("OIC/MOT/2026/4510", "Zenith Tourism LLC", ORIENT, "Liability", _d(1, 8), _d(31, 7), 2_200_000, 6_000, 12.5),
        _policy("OIC/MOT/2026/4510", "Zenith Tourism LLC", ORIENT, "Liability", _d(1, 8), _d(31, 7), 2_200_000, 6_000, 12.5),
        # commission rate booked at 12.5% but the insurer applied 10%
        _policy("OIC/MOT/2026/4511", "Barakat Vegetables LLC", ORIENT, "Motor Fleet", _d(1, 9), _d(31, 8), 1_800_000, 6_000, 12.5),
        # --- Sukoon Insurance ---------------------------------------------
        _policy("SKN/PRP/2026/7781", "Al Zahia Community Mall", SUKOON, "Property", _d(1, 1), _d(31, 12), 14_000_000, 38_500, 15),
        _policy("SKN/PRP/2026/7782", "Ajman Free Zone Authority", SUKOON, "Property", _d(1, 2), _d(31, 1), 22_000_000, 61_000, 12.5),
        _policy("SKN/PRP/2026/7783", "Gulf Pipes Manufacturing", SUKOON, "Engineering", _d(1, 3), _d(28, 2), 7_800_000, 23_400, 12.5),
        _policy("SKN/PRP/2026/7784", "Swiss International School", SUKOON, "Liability", _d(1, 4), _d(31, 3), 3_000_000, 13_200, 15),
        _policy("SKN/PRP/2026/7785", "Fujairah Port Services", SUKOON, "Marine Cargo", _d(1, 5), _d(30, 4), 9_000_000, 27_000, 12.5),
        _policy("SKN/PRP/2026/7786", "Al Ain Farms Dairy", SUKOON, "Property", _d(1, 6), _d(31, 5), 5_500_000, 16_500, 15),
        # small premium difference of AED 35 - below any sane tolerance? still flagged low
        _policy("SKN/PRP/2026/7787", "Bawadi Retail LLC", SUKOON, "Property", _d(1, 7), _d(30, 6), 4_100_000, 11_035, 12.5),
        # not on the statement - unbilled commission
        _policy("SKN/PRP/2026/7788", "Hatta Adventure Tourism", SUKOON, "Liability", _d(1, 8), _d(31, 7), 1_200_000, 4_800, 15),
        # --- insurer with no statement uploaded (coverage gap) --------------
        _policy("TE/2026/9001", "Mirdif Medical Supplies", TAKAFUL, "Medical", _d(1, 1), _d(31, 12), 2_400_000, 19_200, 12.5),
        _policy("TE/2026/9002", "Green Oasis Landscaping", TAKAFUL, "Liability", _d(1, 3), _d(28, 2), 900_000, 5_400, 12.5),
    ]
    return rows


def gig_statement(book: list[Policy]) -> list[Policy]:
    """Statement lines for GIG Gulf (delivered as Excel)."""
    gig = [p for p in book if p.insurer == GIG]
    rows: list[Policy] = []
    for p in gig:
        if p.policy_no == "GIG/2026/000112":  # missing from the statement
            continue
        if p.policy_no == "GIG/2026/000109":
            rows.append(replace(p, premium=11_900, rate=12.5))
            continue
        if p.policy_no == "GIG/2026/000110":
            # insurer applied 12% not the 15% in the book -> 960 vs 1,200
            rows.append(replace(p, rate=12))
            continue
        if p.policy_no == "GIG/2026/000111":
            rows.append(replace(p, status="Active"))
            continue
        if p.policy_no == "GIG/2026/000113":
            rows.append(p)
            rows.append(replace(p, status="Active"))  # duplicate line
            continue
        if p.policy_no == "GIG/2026/000451":
            rows.append(replace(p, policy_no="GIG-2026-451"))
            continue
        if p.policy_no == "GIG/2026/000312":
            rows.append(p)
            rows.append(
                replace(
                    p,
                    policy_no="GIG/2026/000312/E1",
                    premium=2_000,
                    rate=12.5,
                    sum_insured=0,
                    cob="Engineering - Endorsement",
                )
            )
            continue
        if p.policy_no == "GIG/2026/000114":
            rows.append(replace(p, sum_insured=750_000))
            continue
        if p.policy_no == "GIG/2026/000115":
            rows.append(replace(p, insured="Emirates Logistics & Transport LLC"))
            continue
        if p.policy_no == "GIG/2026/000116":
            rows.append(p)
            continue
        if p.policy_no == "GIG/2026/000107":
            # insurer billed in USD while the book records AED
            rows.append(replace(p, currency="USD", premium=12_254.59))
            continue
        rows.append(p)

    # Statement carries a policy the broker book does not have at all.
    rows.append(
        _policy("GIG/2026/000199", "Unregistered Client Trading LLC", GIG, "Property",
                _d(1, 9), _d(31, 8), 3_500_000, 22_400, 12.5)
    )
    return rows


def orient_statement(book: list[Policy]) -> list[Policy]:
    """Statement lines for Orient (delivered as a ruled PDF)."""
    orient = [p for p in book if p.insurer == ORIENT and p.policy_no != "OIC/MOT/2026/4510"]
    rows: list[Policy] = []
    for p in orient:
        if p.policy_no == "OIC/MOT/2026/4509":
            rows.append(replace(p, inception=_d(15, 3)))
            continue
        if p.policy_no == "OIC/MOT/2026/4508":
            rows.append(replace(p, policy_no="OIC/MOT/2026/4580"))
            continue
        if p.policy_no == "OIC/MOT/2026/4511":
            rows.append(replace(p, rate=10))
            continue
        rows.append(p)
    # duplicated in the broker book, single line on the statement
    rows.append(
        _policy("OIC/MOT/2026/4510", "Zenith Tourism LLC", ORIENT, "Liability",
                _d(1, 8), _d(31, 7), 2_200_000, 6_000, 12.5)
    )
    # statement carries a policy missing from the book
    rows.append(
        _policy("OIC/MOT/2026/4599", "Unlisted Marine Services LLC", ORIENT, "Marine Cargo",
                _d(1, 9), _d(31, 8), 2_600_000, 11_000, 12.5)
    )
    return rows


def sukoon_statement(book: list[Policy]) -> list[Policy]:
    """Statement lines for Sukoon (delivered as a PDF with no table grid)."""
    sukoon = [p for p in book if p.insurer == SUKOON]
    rows: list[Policy] = []
    for p in sukoon:
        if p.policy_no == "SKN/PRP/2026/7788":
            continue
        if p.policy_no == "SKN/PRP/2026/7787":
            rows.append(replace(p, premium=11_070))
            continue
        rows.append(p)
    return rows


# --------------------------------------------------------------------------- #
# File writers
# --------------------------------------------------------------------------- #
BROKER_HEADERS = [
    "Policy No", "Insured Name", "Insurer", "Class of Business", "Inception Date",
    "Expiry Date", "Sum Insured", "Gross Premium", "Commission %", "Commission Amount",
    "Currency", "Status",
]
STATEMENT_HEADERS = [
    "Policy No", "Insured Name", "Class of Business", "Inception", "Expiry",
    "Sum Insured", "Gross Premium", "Comm %", "Commission Amount", "Ccy", "Status",
    "Debit Note No",
]


def _broker_values(p: Policy) -> list[str]:
    return [
        p.policy_no, p.insured, p.insurer, p.cob, p.inception.strftime("%d/%m/%Y"),
        p.expiry.strftime("%d/%m/%Y"), f"{p.sum_insured:,}", f"{p.premium:,.2f}",
        f"{p.rate}%", f"{p.commission:,.2f}", p.currency, p.status,
    ]


def _statement_values(p: Policy, ref: str) -> list[str]:
    return [
        p.policy_no, p.insured, p.cob, p.inception.strftime("%d/%m/%Y"),
        p.expiry.strftime("%d/%m/%Y"), f"{p.sum_insured:,}", f"{p.premium:,.2f}",
        f"{p.rate}%", f"{p.commission:,.2f}", p.currency, p.status, ref,
    ]


def broker_csv(book: list[Policy]) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(BROKER_HEADERS)
    for p in book:
        writer.writerow(_broker_values(p))
    return buffer.getvalue().encode("utf-8")


def gig_xlsx(rows: list[Policy]) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill

    wb = Workbook()
    ws = wb.active
    ws.title = "Sept 2026"

    ws["A1"] = GIG
    ws["A1"].font = Font(bold=True, size=14)
    ws["A2"] = "Broker Commission Statement"
    ws["A2"].font = Font(bold=True, size=11)
    ws["A3"] = f"Statement No: GIG-ST-2026-0918     Period: {STATEMENT_PERIOD}"
    ws["A4"] = f"Broker: {BROKER_NAME}     Broker Code: BR-4471"
    ws["A5"] = "Currency: AED unless stated"

    head_fill = PatternFill("solid", fgColor="1F3A5F")
    for col, header in enumerate(STATEMENT_HEADERS, start=1):
        cell = ws.cell(row=7, column=col, value=header)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = head_fill
        cell.alignment = Alignment(horizontal="center", wrap_text=True)

    for offset, p in enumerate(rows):
        excel_row = 8 + offset
        values = [
            p.policy_no, p.insured, p.cob, p.inception, p.expiry, p.sum_insured,
            p.premium, p.rate / 100, p.commission, p.currency, p.status,
            f"DN-{9100 + offset}",
        ]
        for col, value in enumerate(values, start=1):
            cell = ws.cell(row=excel_row, column=col, value=value)
            if isinstance(value, date):
                cell.number_format = "DD/MM/YYYY"
            elif col == 7:
                cell.number_format = "#,##0.00"
            elif col == 9:
                cell.number_format = "#,##0.00"
            elif col == 8:
                cell.number_format = "0.00%"

    total_row = 8 + len(rows) + 1
    ws.cell(row=total_row, column=1, value="Grand Total").font = Font(bold=True)
    ws.cell(row=total_row, column=7, value=f"=SUM(G8:G{total_row - 2})").font = Font(bold=True)
    ws.cell(row=total_row, column=9, value=f"=SUM(I8:I{total_row - 2})").font = Font(bold=True)
    for col, width in zip(range(1, 13), (22, 34, 24, 14, 14, 16, 16, 10, 18, 8, 12, 14)):
        ws.column_dimensions[chr(64 + col)].width = width

    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def _pdf_header(canvas, doc, insurer: str, statement_no: str, subtitle: str) -> None:
    from reportlab.lib.units import mm

    canvas.saveState()
    canvas.setFont("Helvetica-Bold", 15)
    canvas.drawString(18 * mm, doc.pagesize[1] - 18 * mm, insurer)
    canvas.setFont("Helvetica", 10)
    canvas.drawString(18 * mm, doc.pagesize[1] - 24 * mm, subtitle)
    canvas.drawString(18 * mm, doc.pagesize[1] - 29 * mm, f"Statement No: {statement_no}")
    canvas.drawString(18 * mm, doc.pagesize[1] - 34 * mm, f"Broker: {BROKER_NAME}")
    canvas.drawRightString(doc.pagesize[0] - 18 * mm, doc.pagesize[1] - 24 * mm, f"Period: {STATEMENT_PERIOD}")
    canvas.drawRightString(doc.pagesize[0] - 18 * mm, doc.pagesize[1] - 29 * mm, "Page 1 of 1")
    canvas.setStrokeColorRGB(0.75, 0.75, 0.75)
    canvas.setLineWidth(0.6)
    canvas.line(18 * mm, doc.pagesize[1] - 37 * mm, doc.pagesize[0] - 18 * mm, doc.pagesize[1] - 37 * mm)
    canvas.restoreState()


def orient_pdf(rows: list[Policy]) -> bytes:
    """A ruled-table PDF, the common shape of a UAE insurer statement."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=landscape(A4),
        leftMargin=14 * mm, rightMargin=14 * mm, topMargin=46 * mm, bottomMargin=16 * mm,
        title="Orient Insurance - Broker Commission Statement",
    )
    styles = getSampleStyleSheet()
    body = styles["BodyText"].clone("body", fontSize=6.6, leading=7.8)

    headers = ["Policy No", "Insured Name", "Class", "Inception", "Expiry",
               "Sum Insured", "Gross Premium", "Comm %", "Commission", "Ccy", "Status",
               "Debit Note"]
    data: list[list] = [[Paragraph(h, body) for h in headers]]
    for index, p in enumerate(rows):
        data.append(
            [
                Paragraph(p.policy_no, body), Paragraph(p.insured, body), Paragraph(p.cob, body),
                Paragraph(p.inception.strftime("%d/%m/%Y"), body),
                Paragraph(p.expiry.strftime("%d/%m/%Y"), body),
                Paragraph(f"{p.sum_insured:,}", body), Paragraph(f"{p.premium:,.2f}", body),
                Paragraph(f"{p.rate}%", body), Paragraph(f"{p.commission:,.2f}", body),
                Paragraph(p.currency, body), Paragraph(p.status, body),
                Paragraph(f"DN-{9200 + index}", body),
            ]
        )
    total_premium = sum(p.premium for p in rows)
    total_commission = sum(p.commission for p in rows)
    data.append(
        [Paragraph("Total", body)] + [Paragraph("", body)] * 5
        + [Paragraph(f"{total_premium:,.2f}", body), Paragraph("", body),
           Paragraph(f"{total_commission:,.2f}", body), Paragraph("", body),
           Paragraph("", body), Paragraph("", body)]
    )

    table = Table(
        data,
        colWidths=[27 * mm, 50 * mm, 27 * mm, 18 * mm, 18 * mm, 23 * mm, 23 * mm, 12 * mm,
                   23 * mm, 11 * mm, 16 * mm, 20 * mm],
        repeatRows=1,
    )
    table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#9AA5B1")),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E8EDF3")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 6.6),
                ("ALIGN", (5, 1), (8, -1), "RIGHT"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#F4F6F8")),
                ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
                ("TOPPADDING", (0, 0), (-1, -1), 2.5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
            ]
        )
    )

    story = [
        Spacer(1, 24 * mm),
        table,
        Spacer(1, 6 * mm),
        Paragraph(
            "This statement is issued for reconciliation purposes. Queries must be raised "
            "within 30 days of the statement date.",
            styles["BodyText"].clone("foot", fontSize=6.5, textColor=colors.HexColor("#5A6570")),
        ),
    ]
    doc.build(
        story,
        onFirstPage=lambda c, d: _pdf_header(c, d, ORIENT, "OIC-ST-2026-0917", "Broker Commission Statement"),
        onLaterPages=lambda c, d: _pdf_header(c, d, ORIENT, "OIC-ST-2026-0917", "Broker Commission Statement"),
    )
    return buffer.getvalue()


def sukoon_pdf(rows: list[Policy]) -> bytes:
    """A PDF statement with no table grid - columns are just aligned text.

    Deliberately awkward: this is what a lot of real statements look like when
    they come out of older core systems.
    """
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas

    buffer = io.BytesIO()
    page_width, page_height = landscape(A4)
    pdf = canvas.Canvas(buffer, pagesize=landscape(A4))
    pdf.setTitle("Sukoon Insurance - Commission Statement")

    top = page_height - 20 * mm
    pdf.setFont("Helvetica-Bold", 14)
    pdf.drawString(18 * mm, top, SUKOON)
    pdf.setFont("Helvetica", 9)
    pdf.drawString(18 * mm, top - 12, "Broker Commission Statement - Commission Payable")
    pdf.drawString(18 * mm, top - 24, f"Statement No: SKN-ST-2026-0919    Period: {STATEMENT_PERIOD}")
    pdf.drawString(18 * mm, top - 36, f"Broker: {BROKER_NAME}    Broker Code: BR-4471")
    pdf.drawString(18 * mm, top - 48, "All amounts in AED unless otherwise stated")

    columns = [
        (18, "Policy No"),
        (108, "Insured"),
        (255, "Class"),
        (330, "From"),
        (382, "To"),
        (432, "Sum Insured"),
        (496, "Premium"),
        (550, "Comm %"),
        (588, "Commission"),
        (648, "Ccy"),
        (678, "Status"),
    ]
    header_y = top - 68
    pdf.setFont("Helvetica-Bold", 7)
    for x, label in columns:
        pdf.drawString(x, header_y, label)
    pdf.setLineWidth(0.5)
    pdf.line(18 * mm, header_y - 4, page_width - 18 * mm, header_y - 4)

    pdf.setFont("Helvetica", 7)
    y = header_y - 16
    for index, p in enumerate(rows):
        values = [
            p.policy_no, p.insured[:30], p.cob[:16], p.inception.strftime("%d/%m/%Y"),
            p.expiry.strftime("%d/%m/%Y"), f"{p.sum_insured:,}", f"{p.premium:,.2f}",
            f"{p.rate}%", f"{p.commission:,.2f}", p.currency, p.status,
        ]
        for (x, _), value in zip(columns, values):
            pdf.drawString(x, y, value)
        y -= 12.5
        if y < 40:
            pdf.showPage()
            pdf.setFont("Helvetica", 7)
            y = page_height - 30 * mm

    y -= 6
    pdf.setFont("Helvetica-Bold", 7)
    pdf.drawString(18, y, "Total")
    pdf.drawString(496, y, f"{sum(p.premium for p in rows):,.2f}")
    pdf.drawString(588, y, f"{sum(p.commission for p in rows):,.2f}")
    pdf.setFont("Helvetica", 6.5)
    pdf.drawString(18, y - 24, "Computer generated statement - no signature required.")
    pdf.save()
    return buffer.getvalue()


DEMO_FILES = (
    ("broker_register_sep2026.csv", "Broker policy register", "csv"),
    ("GIG_statement_sep2026.xlsx", "GIG Gulf - commission statement", "xlsx"),
    ("Orient_statement_sep2026.pdf", "Orient Insurance - commission statement", "pdf"),
    ("Sukoon_statement_sep2026.pdf", "Sukoon Insurance - commission statement (no table grid)", "pdf"),
)


def build_all() -> dict[str, bytes]:
    book = broker_book()
    return {
        "broker_register_sep2026.csv": broker_csv(book),
        "GIG_statement_sep2026.xlsx": gig_xlsx(gig_statement(book)),
        "Orient_statement_sep2026.pdf": orient_pdf(orient_statement(book)),
        "Sukoon_statement_sep2026.pdf": sukoon_pdf(sukoon_statement(book)),
    }


def expected_exceptions() -> dict[str, int]:
    """What the demo dataset should surface. Used by the test suite."""
    return {
        "premium_mismatch": 2,
        "commission_mismatch": 2,
        "sum_insured_mismatch": 1,
        "date_mismatch": 1,
        "name_mismatch": 1,
        "status_mismatch": 1,
        "currency_mismatch": 1,
        "missing_in_insurer": 2,
        "missing_in_broker": 2,
        "duplicate_in_statement": 1,
        "duplicate_in_broker": 1,
        "low_confidence_match": 1,
        "endorsement_not_in_book": 1,
        "insurer_not_in_statements": 1,
    }
