"""Deterministic synthetic ledger. All amounts are decimal strings, never binary floats."""

import calendar
import csv
import io
import hashlib
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from .db import Case, ImportBatch, Record

CENT = Decimal("0.01")


def money(x):
    return str(Decimal(x).quantize(CENT))


def month_end(year, month):
    return date(year, month, calendar.monthrange(year, month)[1])


CUSTOMERS = [
    ("Atlas Business Group", "0.40"),
    ("Northstar Studio", "0.25"),
    ("Elm Medical Partners", "0.20"),
    ("Cedar Workspace", "0.15"),
]
HEADERS = {
    "receivables": [
        "invoice_id",
        "customer",
        "invoice_date",
        "due_date",
        "amount",
        "paid_amount",
        "last_payment_date",
        "as_of",
        "synthetic",
    ],
    "payables": [
        "bill_id",
        "supplier",
        "bill_date",
        "due_date",
        "amount",
        "paid_amount",
        "as_of",
        "synthetic",
    ],
    "monthly": [
        "period",
        "revenue",
        "cogs",
        "payroll",
        "operating_expenses",
        "depreciation",
        "interest_expense",
        "cash_taxes",
        "maintenance_capex",
        "distributions",
        "cash",
        "receivables",
        "inventory",
        "payables",
        "current_debt",
        "fixed_assets",
        "long_term_debt",
        "equity",
        "synthetic",
    ],
    "bank": ["transaction_id", "date", "category", "amount", "reference", "synthetic"],
    "debt": [
        "payment_id",
        "facility",
        "due_date",
        "principal",
        "interest",
        "maturity_amount",
        "synthetic",
    ],
}
KEYS = {
    "receivables": "invoice_id",
    "payables": "bill_id",
    "monthly": "period",
    "bank": "transaction_id",
    "debt": "payment_id",
}


def record_key(kind, row):
    return row[KEYS[kind]] + (
        "@" + row["as_of"] if kind in ("receivables", "payables") else ""
    )


def csv_text(kind, rows):
    out = io.StringIO(newline="")
    w = csv.DictWriter(out, fieldnames=HEADERS[kind])
    w.writeheader()
    w.writerows(rows)
    return out.getvalue()


def generate():
    invoices, bills, bank, debt, monthly = [], [], [], [], []
    # Opening AR/AP invoices were earned/incurred before the analysis year.
    for year, months in [(2024, [11, 12]), (2025, range(1, 13)), (2026, [1])]:
        for month in months:
            for week, day in enumerate([7, 14, 21, 28]):
                issued = date(year, month, day)
                for i, (customer, share) in enumerate(CUSTOMERS):
                    amount = Decimal("25000") * Decimal(share)
                    inv_id = f"HOS-{year}{month:02}-{week+1}{i+1}"
                    paid_on = issued + timedelta(days=60)
                    invoices.append(
                        dict(
                            invoice_id=inv_id,
                            customer=customer,
                            invoice_date=issued.isoformat(),
                            due_date=paid_on.isoformat(),
                            amount=money(amount),
                            paid_on=paid_on,
                        )
                    )
                if (year, month) >= (2024, 12):
                    bills.append(
                        dict(
                            bill_id=f"BILL-{year}{month:02}-{week+1}",
                            supplier="Pacific Paper & Office",
                            bill_date=issued.isoformat(),
                            due_date=(issued + timedelta(days=30)).isoformat(),
                            amount="16250.00",
                        )
                    )

    def tx(tid, day, category, amount, ref):
        bank.append(
            dict(
                transaction_id=tid,
                date=day.isoformat(),
                category=category,
                amount=money(amount),
                reference=ref,
                synthetic="true",
            )
        )

    for inv in invoices:
        if date(2025, 1, 1) <= inv["paid_on"] <= date(2025, 12, 31):
            tx(
                "RCPT-" + inv["invoice_id"],
                inv["paid_on"],
                "customer_receipt",
                inv["amount"],
                inv["invoice_id"],
            )
    for bill in bills:
        due = date.fromisoformat(bill["due_date"])
        if date(2025, 1, 1) <= due <= date(2025, 12, 31):
            tx(
                "PAY-" + bill["bill_id"],
                due,
                "supplier_payment",
                -Decimal(bill["amount"]),
                bill["bill_id"],
            )
    for year, months in [(2025, range(1, 13)), (2026, range(1, 13))]:
        for month in months:
            balance = Decimal("60000") - Decimal("2500") * (
                (year - 2025) * 12 + month - 1
            )
            interest = max(Decimal("0"), balance * Decimal("0.01"))
            debt.append(
                dict(
                    payment_id=f"DEBT-{year}{month:02}",
                    facility="Equipment term loan",
                    due_date=date(year, month, 28).isoformat(),
                    principal="2500.00",
                    interest=money(interest),
                    maturity_amount="0.00",
                    synthetic="true",
                )
            )
            if year == 2025:
                day = date(year, month, 28)
                for cat, amount in [
                    ("payroll", 18000),
                    ("operating_expense", 6000),
                    ("cash_tax", 2000),
                    ("maintenance_capex", 1000),
                    ("distribution", 1000),
                    ("debt_principal", 2500),
                    ("debt_interest", interest),
                ]:
                    tx(
                        f"{cat}-{year}{month:02}",
                        day,
                        cat,
                        -Decimal(amount),
                        (
                            "DEBT-" + str(year) + f"{month:02}"
                            if cat.startswith("debt")
                            else "Synthetic recurring operating cash flow"
                        ),
                    )
    # Transfers are explicitly represented as a net-zero pair, never sales.
    tx("TRANSFER-IN", date(2025, 6, 15), "internal_transfer", 5000, "transfer-pair-1")
    tx("TRANSFER-OUT", date(2025, 6, 15), "internal_transfer", -5000, "transfer-pair-1")
    opening_cash = Decimal("22000")
    opening_ar = Decimal("200000")
    opening_ap = Decimal("65000")
    # Balance sheet opening assets 407,000 = liabilities 125,000 + equity 282,000.
    equity = Decimal("282000")
    for month in range(1, 13):
        end = month_end(2025, month)
        ar = sum(
            Decimal(i["amount"])
            for i in invoices
            if date.fromisoformat(i["invoice_date"]) <= end < i["paid_on"]
        )
        ap = sum(
            Decimal(b["amount"])
            for b in bills
            if date.fromisoformat(b["bill_date"])
            <= end
            < date.fromisoformat(b["due_date"])
        )
        cash = opening_cash + sum(
            Decimal(t["amount"]) for t in bank if date.fromisoformat(t["date"]) <= end
        )
        interest = Decimal(debt[month - 1]["interest"])
        equity += (
            Decimal("11000")
            - Decimal("1000")
            - interest
            - Decimal("2000")
            - Decimal("1000")
        )
        remaining = Decimal("60000") - Decimal("2500") * month
        monthly.append(
            dict(
                period=f"2025-{month:02}",
                revenue="100000.00",
                cogs="65000.00",
                payroll="18000.00",
                operating_expenses="6000.00",
                depreciation="1000.00",
                interest_expense=money(interest),
                cash_taxes="2000.00",
                maintenance_capex="1000.00",
                distributions="1000.00",
                cash=money(cash),
                receivables=money(ar),
                inventory="65000.00",
                payables=money(ap),
                current_debt=money(min(remaining, Decimal("30000"))),
                fixed_assets="120000.00",
                long_term_debt=money(max(Decimal("0"), remaining - Decimal("30000"))),
                equity=money(equity),
                synthetic="true",
            )
        )

    def ar_snapshot(as_of, delayed=False):
        rows = []
        for i in invoices:
            if date.fromisoformat(i["invoice_date"]) > as_of:
                continue
            pay = i["paid_on"] + timedelta(
                days=(
                    45
                    if delayed
                    and i["customer"] == CUSTOMERS[0][0]
                    and i["paid_on"] >= date(2026, 1, 1)
                    else 0
                )
            )
            paid = pay <= as_of
            rows.append(
                {
                    k: i[k]
                    for k in [
                        "invoice_id",
                        "customer",
                        "invoice_date",
                        "due_date",
                        "amount",
                    ]
                }
                | dict(
                    paid_amount=i["amount"] if paid else "0.00",
                    last_payment_date=pay.isoformat() if paid else "",
                    as_of=as_of.isoformat(),
                    synthetic="true",
                )
            )
        return rows

    ar = ar_snapshot(date(2025, 12, 31))
    ap = [
        {
            **b,
            "paid_amount": (
                b["amount"]
                if date.fromisoformat(b["due_date"]) <= date(2025, 12, 31)
                else "0.00"
            ),
            "as_of": "2025-12-31",
            "synthetic": "true",
        }
        for b in bills
        if date.fromisoformat(b["bill_date"]) <= date(2025, 12, 31)
    ]
    return {
        "monthly": monthly,
        "bank": bank,
        "debt": debt,
        "receivables": ar,
        "payables": ap,
    }, ar_snapshot(date(2026, 1, 31), True)


def seed(db):
    if db.get(Case, "harbor"):
        return
    profile = dict(
        name="Harbor Office Supply",
        industry="Wholesale distribution",
        location="Portland, Oregon",
        owner="Morgan Ellis · 100% ownership",
        requested_amount="100000.00",
        purpose="Revolving line of credit to bridge customer collections and supplier payments.",
        reported_collection_days=60,
        supplier_terms_days=30,
        verified=False,
        documents=[
            {"name": "2025 financial statements", "received": True, "verified": False},
            {"name": "Accounts receivable aging", "received": False, "verified": False},
            {"name": "Business tax returns", "received": False, "verified": False},
            {"name": "Existing debt schedule", "received": True, "verified": False},
            {
                "name": "Ownership and guarantor information",
                "received": False,
                "verified": False,
            },
        ],
        opening={
            "as_of": "2024-12-31",
            "cash": "22000.00",
            "receivables": "200000.00",
            "payables": "65000.00",
            "inventory": "65000.00",
            "debt": "60000.00",
            "fixed_assets": "120000.00",
            "equity": "282000.00",
        },
        conditions=[
            {
                "id": "collections-warning",
                "category": "internal_warning",
                "metric": "dso",
                "operator": "max",
                "threshold": "70",
                "period": "monthly",
                "enabled": True,
            },
            {
                "id": "illustrative-dscr",
                "category": "contractual_covenant",
                "metric": "dscr",
                "operator": "min",
                "threshold": "1.25",
                "period": "trailing_12_months",
                "enabled": False,
            },
        ],
        reporting_deadline="2026-02-15",
        expected_report_period="2026-01",
        synthetic=True,
    )
    db.add(Case(id="harbor", owner_id="analyst", profile=profile))
    db.flush()
    datasets, later = generate()
    # AR is deliberately not pre-imported: the flagship journey begins with a real upload.
    for kind in ["monthly", "bank", "debt", "payables"]:
        rows = datasets[kind]
        raw = csv_text(kind, rows)
        bid = "seed-" + kind
        db.add(
            ImportBatch(
                id=bid,
                case_id="harbor",
                kind=kind,
                filename="synthetic-" + kind + ".csv",
                raw=raw,
                digest=hashlib.sha256(raw.replace("\r\n", "\n").encode()).hexdigest(),
                status="committed",
                rows=rows,
                errors=[],
                created_by="seed",
            )
        )
        db.flush()
        for row in rows:
            db.add(
                Record(
                    case_id="harbor",
                    kind=kind,
                    key=record_key(kind, row),
                    data=row,
                    import_id=bid,
                )
            )
    db.commit()


def write_examples():
    target = Path(__file__).resolve().parents[1] / "examples"
    target.mkdir(exist_ok=True)
    datasets, later = generate()
    for kind, rows in datasets.items():
        (target / f"harbor-{kind}.csv").write_text(
            csv_text(kind, rows), encoding="utf-8"
        )
        (target / f"template-{kind}.csv").write_text(
            csv_text(kind, []), encoding="utf-8"
        )
    (target / "harbor-receivables-2026-01.csv").write_text(
        csv_text("receivables", later), encoding="utf-8"
    )
    closing = datasets["monthly"][-1]
    jan = {
        **closing,
        "period": "2026-01",
        "interest_expense": "300.00",
        "cash": money(Decimal(closing["cash"]) - Decimal("35800")),
        "receivables": "240000.00",
        "current_debt": "27500.00",
        "equity": money(Decimal(closing["equity"]) + Decimal("6700")),
    }
    (target / "harbor-monthly-2026-01.csv").write_text(
        csv_text("monthly", [jan]), encoding="utf-8"
    )


if __name__ == "__main__":
    write_examples()
