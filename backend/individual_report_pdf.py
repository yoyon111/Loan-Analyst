"""Render a saved individual practice case as a shareable PDF."""

from decimal import Decimal
from html import escape
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle


INK = colors.HexColor("#203238")
GREEN = colors.HexColor("#087364")
PALE = colors.HexColor("#eef5f1")
LINE = colors.HexColor("#d7e4df")


def safe(value):
    return escape(str(value if value not in (None, "") else "Not entered")).replace("\n", "<br/>")


def dollars(value):
    return f"${Decimal(str(value or 0)):,.2f}"


def render_individual_report(report):
    snapshot = report.snapshot
    application = snapshot["application"]
    servicing = snapshot["servicing"]
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=42, leftMargin=42,
                            topMargin=48, bottomMargin=48)
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="ReportTitle", parent=styles["Title"], fontName="Helvetica-Bold",
                              fontSize=19, leading=23, textColor=INK, spaceAfter=6))
    styles.add(ParagraphStyle(name="ReportSub", parent=styles["Normal"], fontSize=9,
                              leading=13, textColor=colors.HexColor("#58716e"), spaceAfter=12))
    styles.add(ParagraphStyle(name="ReportHeading", parent=styles["Heading2"], fontSize=12,
                              leading=16, textColor=GREEN, spaceBefore=14, spaceAfter=7,
                              keepWithNext=1))
    styles.add(ParagraphStyle(name="ReportCell", parent=styles["Normal"], fontSize=8,
                              leading=11, textColor=INK))
    styles.add(ParagraphStyle(name="ReportSmall", parent=styles["Normal"], fontSize=7,
                              leading=10, textColor=INK))
    cell = styles["ReportCell"]
    small = styles["ReportSmall"]
    story = [
        Paragraph(safe(report.title), styles["ReportTitle"]),
        Paragraph(f"Individual rental-property loan practice | Saved {safe(report.created_at[:16].replace('T', ' '))} UTC", styles["ReportSub"]),
        Paragraph("Practice simulation only. This report is a saved snapshot; it does not verify documents, check credit, approve a loan, or reflect real servicer accounting.", styles["ReportCell"]),
    ]

    def section(title, rows):
        story.append(Paragraph(title, styles["ReportHeading"]))
        data = [[Paragraph(safe(label), cell), Paragraph(safe(value), cell)] for label, value in rows]
        table = Table(data, colWidths=[165, 363], hAlign="LEFT")
        table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.white, PALE]),
            ("LINEBELOW", (0, -1), (-1, -1), 0.4, LINE),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        story.append(table)

    section("Case and terms", [
        ("Practice case", application["applicant_name"]),
        ("Status at save", snapshot["status"].replace("_", " ").title()),
        ("Loan amount", dollars(application["requested_loan"])),
        ("Purchase price", dollars(application["purchase_price"])),
        ("Annual interest rate", f"{application['annual_rate']}%"),
        ("Term", f"{application['term_months']} months"),
        ("First payment due", application["first_due_date"]),
        ("Property", application["property_address"]),
        ("Rental property", "Yes" if application["rental_property"] else "No"),
    ])
    section("Borrower worksheet", [
        ("Co-applicant", application["co_applicant_name"]),
        ("Down payment", dollars(application["down_payment"])),
        ("Down payment source", application["down_payment_source"]),
        ("Annual income", dollars(application["annual_income"])),
        ("Employer", application["employer"]),
        ("Employment details", application["employment_notes"]),
        ("Bank and investment assets", dollars(application["liquid_assets"])),
        ("Savings after purchase", dollars(application["reserves"])),
        ("Existing monthly debts", dollars(application["monthly_debt"])),
        ("Expected monthly rent", dollars(application["expected_monthly_rent"])),
        ("Annual property tax", dollars(application["property_tax_annual"])),
        ("Annual insurance", dollars(application["insurance_annual"])),
        ("Monthly HOA", dollars(application["hoa_monthly"])),
        ("Credit authorization recorded", "Yes" if application["credit_authorized"] else "No"),
        ("Case notes", application["notes"]),
    ])
    story.append(Paragraph("Document checklist", styles["ReportHeading"]))
    checklist = snapshot["checklist"]
    if checklist:
        rows = [[Paragraph("Item", small), Paragraph("Status", small), Paragraph("Note", small)]]
        rows.extend([Paragraph(safe(item["key"].replace("_", " ").title()), small),
                     Paragraph(safe(item["status"].replace("_", " ").title()), small),
                     Paragraph(safe(item["note"]), small)] for item in checklist)
        table = Table(rows, colWidths=[145, 105, 278], repeatRows=1, hAlign="LEFT")
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), PALE),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LINEBELOW", (0, 0), (-1, 0), 0.6, LINE),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PALE]),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        story.append(table)
    else:
        story.append(Paragraph("No checklist items recorded.", cell))

    section("Servicing at save", [
        ("Principal balance", dollars(servicing["balance"])),
        ("Scheduled principal + interest", dollars(servicing["scheduled_principal_interest"])),
        ("Monthly escrow", dollars(servicing["monthly_escrow"])),
        ("Next full payment", dollars(servicing["full_payment_due"])),
        ("Next due date", servicing["next_due_date"] or "Paid off"),
        ("Payments posted", str(len(servicing["payments"]))),
    ])
    story.append(Paragraph("Payment history", styles["ReportHeading"]))
    payments = servicing["payments"]
    if payments:
        header = ["Due", "Posted", "Paid", "Interest", "Escrow", "Principal", "Balance"]
        rows = [[Paragraph(x, small) for x in header]]
        for payment in payments:
            rows.append([Paragraph(safe(payment[key] if key in ("due_date", "effective_date") else dollars(payment[key])), small)
                         for key in ("due_date", "effective_date", "amount", "interest", "escrow", "principal", "balance")])
        table = Table(rows, colWidths=[66, 66, 79, 75, 75, 78, 89], repeatRows=1, hAlign="LEFT")
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), PALE),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PALE]),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 3),
            ("RIGHTPADDING", (0, 0), (-1, -1), 3),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        story.append(table)
    else:
        story.append(Paragraph("No payments posted at the time this report was saved.", cell))
    story.append(Spacer(1, 10))

    def footer(canvas, document):
        canvas.saveState()
        canvas.setStrokeColor(LINE)
        canvas.line(42, 35, letter[0] - 42, 35)
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#58716e"))
        canvas.drawString(42, 23, "InvestOffice | Individual loan practice")
        canvas.drawRightString(letter[0] - 42, 23, f"Page {document.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()
