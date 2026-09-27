import csv
import io
import re
from datetime import date
from decimal import Decimal, InvalidOperation
from .seed import HEADERS, record_key

CATEGORIES = {
    "customer_receipt",
    "loan_proceeds",
    "internal_transfer",
    "supplier_payment",
    "payroll",
    "operating_expense",
    "cash_tax",
    "maintenance_capex",
    "distribution",
    "debt_principal",
    "debt_interest",
}
TEXT_FIELDS = {
    "invoice_id",
    "customer",
    "bill_id",
    "supplier",
    "transaction_id",
    "category",
    "reference",
    "payment_id",
    "facility",
    "synthetic",
    "period",
    "as_of",
    "invoice_date",
    "due_date",
    "bill_date",
    "date",
    "last_payment_date",
}


def validate(kind, raw):
    errors = []
    rows = []
    seen = set()
    try:
        reader = csv.DictReader(io.StringIO(raw))
        if reader.fieldnames != HEADERS[kind]:
            return [], [
                {
                    "row": 1,
                    "field": "headers",
                    "message": "Use exactly these columns, in order: "
                    + ", ".join(HEADERS[kind]),
                }
            ]
        for line, row in enumerate(reader, 2):
            if line > 10002:
                errors.append(
                    {
                        "row": line,
                        "field": "file",
                        "message": "Maximum 10,000 records per upload.",
                    }
                )
                break

            def fail(field, message):
                errors.append({"row": line, "field": field, "message": message})

            if None in row or any(v is None for v in row.values()):
                fail(
                    "columns",
                    "This row has a different number of columns than the header.",
                )
                continue
            row = {k: v.strip() for k, v in row.items()}
            for field, value in row.items():
                if not value and field != "last_payment_date":
                    fail(field, "Required value is missing.")
                    continue
                if len(value) > 500:
                    fail(field, "Maximum 500 characters.")
                    continue
                if field not in TEXT_FIELDS:
                    try:
                        n = Decimal(value)
                        if (
                            not n.is_finite()
                            or abs(n) > Decimal("1000000000000")
                            or n.as_tuple().exponent < -2
                        ):
                            raise InvalidOperation
                        if (
                            n < 0
                            and not (kind == "bank" and field == "amount")
                            and field not in ("cash", "equity")
                        ):
                            fail(field, "Must be zero or positive.")
                        row[field] = format(n, ".2f")
                    except (InvalidOperation, ValueError):
                        fail(
                            field,
                            "Use a finite number with at most two decimals; no currency signs or commas.",
                        )
                elif field.endswith("_date") or field in ("date", "as_of"):
                    if value:
                        try:
                            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
                                raise ValueError
                            date.fromisoformat(value)
                        except ValueError:
                            fail(field, "Use a valid YYYY-MM-DD date.")
                elif field == "period":
                    try:
                        if not re.fullmatch(r"\d{4}-\d{2}", value):
                            raise ValueError
                        date.fromisoformat(value + "-01")
                    except ValueError:
                        fail(field, "Use a valid YYYY-MM reporting month.")
                elif field == "synthetic" and value not in ("true", "false"):
                    fail(field, "Use true or false to label the source.")
            if any(e["row"] == line for e in errors):
                continue
            if kind in ("receivables", "payables"):
                start = row.get("invoice_date", row.get("bill_date"))
                if start > row["as_of"]:
                    fail("as_of", "Snapshot date cannot precede the invoice or bill.")
                if row["due_date"] < start:
                    fail("due_date", "Due date cannot precede issue date.")
                if Decimal(row["paid_amount"]) > Decimal(row["amount"]):
                    fail("paid_amount", "Payment cannot exceed original amount.")
                if kind == "receivables":
                    if Decimal(row["paid_amount"]) > 0 and not row["last_payment_date"]:
                        fail(
                            "last_payment_date",
                            "Provide a payment date for paid invoices.",
                        )
                    if (
                        row["last_payment_date"]
                        and not start <= row["last_payment_date"] <= row["as_of"]
                    ):
                        fail(
                            "last_payment_date",
                            "Payment must fall between invoice date and snapshot date.",
                        )
            if kind == "bank":
                if row["category"] not in CATEGORIES:
                    fail(
                        "category",
                        "Choose a documented bank category; deposits are not automatically revenue.",
                    )
                elif (
                    row["category"] in ("customer_receipt", "loan_proceeds")
                    and Decimal(row["amount"]) <= 0
                ):
                    fail("amount", "Receipts and proceeds must be positive.")
                elif (
                    row["category"]
                    not in ("customer_receipt", "loan_proceeds", "internal_transfer")
                    and Decimal(row["amount"]) >= 0
                ):
                    fail("amount", "Cash outflows must be negative.")
            if kind == "monthly":
                d = lambda k: Decimal(row[k])
                if abs(
                    d("cash")
                    + d("receivables")
                    + d("inventory")
                    + d("fixed_assets")
                    - d("payables")
                    - d("current_debt")
                    - d("long_term_debt")
                    - d("equity")
                ) > Decimal("0.01"):
                    fail(
                        "equity",
                        "Balance sheet does not balance: assets must equal liabilities plus equity.",
                    )
            key = record_key(kind, row)
            if key in seen:
                fail("record", "Duplicate record key within this file: " + key)
            seen.add(key)
            rows.append(row)
    except (csv.Error, UnicodeError) as exc:
        errors.append({"row": 0, "field": "file", "message": str(exc)})
    if not rows and not errors:
        errors.append(
            {
                "row": 2,
                "field": "file",
                "message": "The file has headers but no records.",
            }
        )
    return rows, errors[:100]
