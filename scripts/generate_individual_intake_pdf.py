"""Generate the fillable individual-loan practice worksheet used by the app."""

from pathlib import Path
from shutil import copyfile

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output" / "pdf" / "individual-rental-loan-intake.pdf"
PUBLIC = ROOT / "public" / "individual-rental-loan-intake.pdf"
WIDTH, HEIGHT = letter
NAVY = colors.HexColor("#12363c")
GREEN = colors.HexColor("#087364")
MUTED = colors.HexColor("#647b7e")
LINE = colors.HexColor("#d2dfdc")


def header(pdf, subtitle):
    pdf.setFillColor(NAVY)
    pdf.rect(0, HEIGHT - 91, WIDTH, 91, fill=1, stroke=0)
    pdf.setFillColor(colors.white)
    pdf.setFont("Helvetica-Bold", 20)
    pdf.drawString(44, HEIGHT - 42, "Borrower rental-property worksheet")
    pdf.setFont("Helvetica", 10)
    pdf.drawString(44, HEIGHT - 63, subtitle)
    pdf.setStrokeColor(LINE)
    pdf.line(44, 43, WIDTH - 44, 43)
    pdf.setFillColor(MUTED)
    pdf.setFont("Helvetica", 8)
    pdf.drawString(44, 29, "InvestOffice practice worksheet  |  Fictional information only")
    pdf.drawRightString(WIDTH - 44, 29, "Page 1 of 1")


def heading(pdf, title, y):
    pdf.setFillColor(GREEN)
    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawString(44, y, title)
    pdf.setStrokeColor(LINE)
    pdf.line(44, y - 7, WIDTH - 44, y - 7)
    return y - 26


def field(pdf, name, label, x, y, width, height=22, multiline=False):
    pdf.setFillColor(NAVY)
    pdf.setFont("Helvetica-Bold", 8.6)
    pdf.drawString(x, y, label)
    pdf.acroForm.textfield(
        name=name,
        tooltip=label,
        x=x,
        y=y - height - 5,
        width=width,
        height=height,
        borderStyle="solid",
        borderWidth=0.7,
        borderColor=LINE,
        fillColor=colors.white,
        textColor=NAVY,
        forceBorder=True,
        fontName="Helvetica",
        fontSize=9,
        fieldFlags="multiline" if multiline else "",
    )


def pair(pdf, first, second, y):
    field(pdf, *first, 44, y, 250)
    field(pdf, *second, 318, y, 250)
    return y - 52


def wrap(pdf, text, x, y, max_width, font="Helvetica", size=8, step=11):
    pdf.setFont(font, size)
    words = text.split()
    line = ""
    for word in words:
        candidate = f"{line} {word}".strip()
        if stringWidth(candidate, font, size) <= max_width:
            line = candidate
        else:
            pdf.drawString(x, y, line)
            y -= step
            line = word
    if line:
        pdf.drawString(x, y, line)
        y -= step
    return y


def build():
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    pdf = canvas.Canvas(str(OUTPUT), pagesize=letter, pageCompression=1)
    pdf.setTitle("Borrower rental-property intake - fillable practice worksheet")
    pdf.setAuthor("InvestOffice")

    header(pdf, "Borrower completes this page. Leave unknown amounts blank.")
    y = heading(pdf, "1  Applicant and rental property", 674)
    y = pair(pdf, ("applicant_name", "Applicant name"), ("co_applicant_name", "Co-applicant name, if any"), y)
    field(pdf, "property_address", "Property address", 44, y, 524)
    y -= 52
    y = pair(pdf, ("purchase_price", "Purchase price ($)"), ("requested_loan", "Requested loan ($)"), y)
    y = pair(pdf, ("down_payment", "Down payment ($)"), ("expected_monthly_rent", "Expected monthly rent ($)"), y)
    field(pdf, "down_payment_source", "Source of down payment and closing funds", 44, y, 524, height=36, multiline=True)
    y -= 68

    y = heading(pdf, "2  Income, employment, assets, and debts", y)
    y = pair(pdf, ("annual_income", "Annual income ($)"), ("employer", "Employer / business"), y)
    y = pair(pdf, ("liquid_assets", "Bank and investment assets ($)"), ("reserves", "Savings after purchase ($)"), y)
    field(pdf, "monthly_debt", "Existing monthly debt payments ($)", 44, y, 250)
    y -= 52
    y = heading(pdf, "3  Property costs, if known", y)
    field(pdf, "property_tax_annual", "Annual property tax ($)", 44, y, 160)
    field(pdf, "insurance_annual", "Annual property insurance ($)", 226, y, 160)
    field(pdf, "hoa_monthly", "Monthly HOA dues ($)", 408, y, 160)
    y -= 53
    pdf.setFillColor(MUTED)
    y = wrap(pdf, "Do not enter a Social Security number here. The lender or practice operator completes the document checklist, verifies information, and enters loan terms separately.", 44, y, 524, size=8.5, step=12)
    wrap(pdf, "For this practice exercise, provide pay stubs, W-2s, statements, debt details, purchase agreement, and leases separately if requested. This worksheet is not a credit authorization.", 44, y - 4, 524, size=8.5, step=12)
    pdf.save()
    copyfile(OUTPUT, PUBLIC)
    print(OUTPUT)
    print(PUBLIC)


if __name__ == "__main__":
    build()
