"""Pure decimal calculations over persisted source records. Monetary output is a string."""

from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
import calendar
from .db import records

D = Decimal


def q(n):
    return str(n.quantize(D("0.01"), rounding=ROUND_HALF_UP))


def total(rows, key):
    return sum((D(r[key]) for r in rows), D("0"))


def previous_month(period, count=1):
    year, month = map(int, period.split("-"))
    n = year * 12 + month - 1 - count
    return f"{n//12:04}-{n%12+1:02}"


def end_of(period):
    y, m = map(int, period.split("-"))
    return date(y, m, calendar.monthrange(y, m)[1])


def latest_snapshot(rows, as_of):
    dates = [r["as_of"] for r in rows if r["as_of"] <= as_of]
    latest = max(dates) if dates else None
    return [r for r in rows if r["as_of"] == latest], latest


def analysis(db, case, period=None):
    financials = records(db, case.id, "monthly")
    period = period or max((r["period"] for r in financials), default="2025-12")
    by_period = {r["period"]: r for r in financials}
    periods = sorted(previous_month(period, n) for n in range(12))
    missing = [p for p in periods if p not in by_period]
    year = [by_period[p] for p in periods if p in by_period]
    current = by_period.get(period)
    prior = by_period.get(previous_month(period, 12))
    if not prior and case.profile.get("opening", {}).get("as_of", "")[
        :7
    ] == previous_month(period, 12):
        prior = case.profile["opening"]
    end = end_of(period)
    start = date.fromisoformat(periods[0] + "-01")
    ar, ar_date = latest_snapshot(records(db, case.id, "receivables"), end.isoformat())
    ar_current = ar_date == end.isoformat()
    open_ar = [r for r in ar if D(r["amount"]) > D(r["paid_amount"])]
    outstanding = sum((D(r["amount"]) - D(r["paid_amount"]) for r in open_ar), D(0))
    aging = {
        name: D(0)
        for name in ["Current", "1–30 days", "31–60 days", "61–90 days", "90+ days"]
    }
    for r in open_ar:
        days = (date.fromisoformat(ar_date) - date.fromisoformat(r["due_date"])).days
        bucket = (
            "Current"
            if days <= 0
            else (
                "1–30 days"
                if days <= 30
                else (
                    "31–60 days"
                    if days <= 60
                    else "61–90 days" if days <= 90 else "90+ days"
                )
            )
        )
        aging[bucket] += D(r["amount"]) - D(r["paid_amount"])
    customers = {}
    for r in ar:
        if start.isoformat() <= r["invoice_date"] <= end.isoformat():
            customers[r["customer"]] = customers.get(r["customer"], D(0)) + D(
                r["amount"]
            )
    sales_from_invoices = sum(customers.values(), D(0))
    revenue = total(year, "revenue") if not missing else None
    invoice_complete = (
        ar_current and revenue is not None and sales_from_invoices == revenue
    )
    concentration = (
        [
            {"name": k, "sales": q(v), "share": q(v / sales_from_invoices * 100)}
            for k, v in sorted(
                customers.items(), key=lambda item: item[1], reverse=True
            )
        ]
        if invoice_complete and sales_from_invoices
        else []
    )
    debt = [
        r
        for r in records(db, case.id, "debt")
        if start.isoformat() <= r["due_date"] <= end.isoformat()
    ]
    bank = [
        r
        for r in records(db, case.id, "bank")
        if start.isoformat() <= r["date"] <= end.isoformat()
    ]
    debt_months = {r["due_date"][:7] for r in debt}
    ebitda = cads = dscr = service = wc_change = None
    reasons = []
    if missing:
        reasons.append("Missing monthly reports: " + ", ".join(missing))
    if not prior:
        reasons.append(
            "Missing opening working-capital balances for this trailing 12-month period."
        )
    if set(periods) - debt_months:
        reasons.append(
            "Debt schedule does not cover every month in the analysis period."
        )
    if revenue is not None:
        ebitda = (
            revenue
            - total(year, "cogs")
            - total(year, "payroll")
            - total(year, "operating_expenses")
        )
        if prior and current:
            wc_change = (
                D(current["receivables"])
                + D(current["inventory"])
                - D(current["payables"])
                - (
                    D(prior["receivables"])
                    + D(prior["inventory"])
                    - D(prior["payables"])
                )
            )
            cads = (
                ebitda
                - total(year, "cash_taxes")
                - total(year, "maintenance_capex")
                - total(year, "distributions")
                - wc_change
            )
        if not set(periods) - debt_months:
            service = (
                total(debt, "principal")
                + total(debt, "interest")
                + total(debt, "maturity_amount")
            )
            if service > 0 and cads is not None:
                dscr = cads / service
    dso = None
    if (
        ar_current
        and current
        and outstanding == D(current["receivables"])
        and D(current["revenue"]) > 0
    ):
        dso = outstanding / D(current["revenue"]) * D(end.day)
    current_assets = (
        D(current["cash"]) + D(current["receivables"]) + D(current["inventory"])
        if current
        else None
    )
    current_liabilities = (
        D(current["payables"]) + D(current["current_debt"]) if current else None
    )
    proposed = case.profile.get("proposed_terms")
    proposed_result = {
        "status": "insufficient_data",
        "reason": "Set an assumed draw, annual rate, and principal due during the analysis period. A requested limit alone is not debt service.",
    }
    if proposed and cads is not None and service is not None:
        interest = D(proposed["draw"]) * D(proposed["annual_rate"]) / 100
        principal = D(proposed["principal_due"])
        proposed_result = {
            "status": "illustrative",
            "interest": q(interest),
            "principal": q(principal),
            "dscr": (
                q(cads / (service + interest + principal))
                if service + interest + principal > 0
                else None
            ),
            "terms": proposed,
        }
    reconciliation = []
    if current and ar_current and outstanding != D(current["receivables"]):
        reconciliation.append(
            "Receivables detail differs from the monthly balance sheet. Resolve before relying on liquidity results."
        )
    if not ar_current:
        reconciliation.append(
            "Import a receivables snapshot dated "
            + end.isoformat()
            + " for current aging, DSO, and concentration."
        )
    if ar_current and not invoice_complete:
        reconciliation.append(
            "Invoice sales do not reconcile to the full trailing-year revenue; sales concentration is insufficient data."
        )
    return dict(
        raw_values={
            "dscr": str(dscr) if dscr is not None else None,
            "dso": str(dso) if dso is not None else None,
        },
        period=period,
        period_start=start.isoformat(),
        period_end=end.isoformat(),
        missing=missing,
        reasons=reasons,
        revenue=q(revenue) if revenue is not None else None,
        ebitda=q(ebitda) if ebitda is not None else None,
        cads=q(cads) if cads is not None else None,
        dscr=q(dscr) if dscr is not None else None,
        debt_service=q(service) if service is not None else None,
        cash=current["cash"] if current else None,
        current_ratio=(
            q(current_assets / current_liabilities)
            if current_liabilities and current_assets is not None
            else None
        ),
        working_capital=(
            q(current_assets - current_liabilities)
            if current_assets is not None
            else None
        ),
        dso=q(dso) if dso is not None else None,
        receivables=q(outstanding) if ar_current else None,
        ar_as_of=ar_date,
        aging=(
            [{"name": k, "amount": q(v)} for k, v in aging.items()]
            if ar_current
            else []
        ),
        concentration=concentration,
        proposed=proposed_result,
        reconciliation=reconciliation,
        sources=dict(
            ebitda=q(ebitda) if ebitda is not None else None,
            cash_taxes=q(total(year, "cash_taxes")) if not missing else None,
            maintenance_capex=(
                q(total(year, "maintenance_capex")) if not missing else None
            ),
            distributions=q(total(year, "distributions")) if not missing else None,
            working_capital_change=q(wc_change) if wc_change is not None else None,
            principal=q(total(debt, "principal")) if service is not None else None,
            interest=q(total(debt, "interest")) if service is not None else None,
        ),
        history=[
            {k: r[k] for k in ("period", "revenue", "cash", "receivables", "payables")}
            for r in sorted(financials, key=lambda r: r["period"])
        ],
        bank_classification=[
            {
                "category": c,
                "amount": q(
                    sum((D(r["amount"]) for r in bank if r["category"] == c), D(0))
                ),
            }
            for c in sorted(set(r["category"] for r in bank))
        ],
    )


def forecast(db, case, assumptions):
    period = assumptions["period"]
    as_of = end_of(period)
    financials = {r["period"]: r for r in records(db, case.id, "monthly")}
    current = financials.get(period)
    ar, ar_date = latest_snapshot(
        records(db, case.id, "receivables"), as_of.isoformat()
    )
    ap, ap_date = latest_snapshot(records(db, case.id, "payables"), as_of.isoformat())
    if not current or ar_date != as_of.isoformat() or ap_date != as_of.isoformat():
        return {
            "status": "insufficient_data",
            "reason": "A monthly report and both receivables and payables snapshots must share the forecast opening date.",
        }
    if sum((D(r["amount"]) - D(r["paid_amount"]) for r in ar), D(0)) != D(
        current["receivables"]
    ) or sum((D(r["amount"]) - D(r["paid_amount"]) for r in ap), D(0)) != D(
        current["payables"]
    ):
        return {
            "status": "insufficient_data",
            "reason": "Reconcile receivables and payables detail to the opening balance sheet first.",
        }
    scheduled = records(db, case.id, "debt")
    finish = as_of + timedelta(days=91)
    covered = {r["due_date"][:7] for r in scheduled}
    expected = {(as_of + timedelta(days=i)).strftime("%Y-%m") for i in range(1, 92)}
    if expected - covered:
        return {
            "status": "insufficient_data",
            "reason": "Debt schedule must explicitly cover each forecast month, including any zero-payment month.",
        }

    def run(delay, sales_change, cost_change, draw):
        cash = D(current["cash"])
        weeks = []
        daily_sales = D(current["revenue"]) / D(as_of.day) * (1 + D(sales_change) / 100)
        daily_cogs = (
            D(current["cogs"])
            / D(as_of.day)
            * (1 + D(sales_change) / 100)
            * (1 + D(cost_change) / 100)
        )
        # A future sale can only create a receipt after the opening date + collection terms.
        collection_days = int(case.profile["reported_collection_days"]) + delay
        supplier_days = int(case.profile["supplier_terms_days"])
        for week in range(13):
            start = as_of + timedelta(days=week * 7 + 1)
            end = start + timedelta(days=6)
            collections = D(0)
            bills = D(0)
            for invoice in ar:
                receipt = max(
                    date.fromisoformat(invoice["due_date"]), as_of + timedelta(days=1)
                ) + timedelta(days=delay)
                if start <= receipt <= end:
                    collections += D(invoice["amount"]) - D(invoice["paid_amount"])
            for bill in ap:
                payment = max(
                    date.fromisoformat(bill["due_date"]), as_of + timedelta(days=1)
                )
                if start <= payment <= end:
                    bills += D(bill["amount"]) - D(bill["paid_amount"])
            for day_offset in range(7):
                day = start + timedelta(days=day_offset)
                if day - timedelta(days=collection_days) > as_of:
                    collections += daily_sales
                if day - timedelta(days=supplier_days) > as_of:
                    bills += daily_cogs
            # Cash costs use a 365/12 average month, with weekly accrual assumed paid weekly.
            payroll = D(current["payroll"]) * 12 / 365 * 7
            operating = (
                D(current["operating_expenses"])
                * 12
                / 365
                * 7
                * (1 + D(cost_change) / 100)
            )
            other = (
                (
                    D(current["cash_taxes"])
                    + D(current["maintenance_capex"])
                    + D(current["distributions"])
                )
                * 12
                / 365
                * 7
            )
            due = [
                r
                for r in scheduled
                if start.isoformat() <= r["due_date"] <= end.isoformat()
            ]
            principal = total(due, "principal")
            interest = total(due, "interest")
            maturity = total(due, "maturity_amount")
            financing = D(draw) if week == 0 else D(0)
            proposed_interest = D(draw) * D(assumptions["annual_rate"]) / 100 / 365 * 7
            proposed_maturity = (
                D(draw) if assumptions.get("maturity_week") == week + 1 else D(0)
            )
            # Interest stops after the illustrative draw matures.
            if (
                assumptions.get("maturity_week")
                and week + 1 > assumptions["maturity_week"]
            ):
                proposed_interest = D(0)
            opening = cash
            cash += (
                collections
                + financing
                - bills
                - payroll
                - operating
                - other
                - principal
                - interest
                - maturity
                - proposed_interest
                - proposed_maturity
            )
            weeks.append(
                dict(
                    week=week + 1,
                    start=start.isoformat(),
                    end=end.isoformat(),
                    opening=q(opening),
                    collections=q(collections),
                    supplier_payments=q(bills),
                    payroll=q(payroll),
                    operating=q(operating),
                    tax_capex_distributions=q(other),
                    principal=q(principal),
                    interest=q(interest + proposed_interest),
                    maturity=q(maturity + proposed_maturity),
                    financing_inflow=q(financing),
                    cash=q(cash),
                )
            )
        low = min([D(current["cash"])] + [D(w["cash"]) for w in weeks])
        buffer = D(assumptions["cash_buffer"])
        return dict(
            weeks=weeks,
            lowest_cash=q(low),
            funding_needed=q(max(D(0), buffer - low)),
            ending_cash=weeks[-1]["cash"],
        )

    baseline = run(0, "0", "0", "0")
    stress = run(
        assumptions["delay_days"],
        assumptions["sales_change"],
        assumptions["cost_change"],
        assumptions["draw"],
    )
    return dict(
        status="complete",
        as_of=as_of.isoformat(),
        opening_cash=current["cash"],
        baseline=baseline,
        stress=stress,
        assumptions=assumptions,
        notes=[
            "Only invoices outstanding on the opening date are collected as existing receivables. Future sales begin the following day and collect after the assumed lag.",
            "Future sales and purchases use the last reported month divided by its calendar days. Payroll and other cash costs use monthly amount × 12 / 365 × 7.",
            "Existing unpaid bills are paid at due date; overdue bills are paid in week one. Future purchases pay after supplier terms.",
            "Funding need is the additional cash required to maintain the buffer at weekly endpoints, including opening cash. Intraday shortfalls are not modeled.",
            "A proposed draw is a financing inflow. Interest uses simple ACT/365; principal is due at the selected maturity week, or outside the horizon.",
        ],
    )
