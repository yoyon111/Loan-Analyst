"""Transparent, illustrative rental-loan affordability exercise.

These thresholds are supplied as practice assumptions, not lender rules.
Rental income, credit, appraisal, documentation, and loan-program eligibility
are deliberately outside this calculation.
"""

from decimal import Decimal

from .finance import q


INPUT_KEYS = (
    "annual_income", "monthly_debt", "current_housing_payment",
    "liquid_assets", "reserves", "purchase_price", "requested_loan",
    "down_payment",
    "property_tax_annual", "insurance_annual", "hoa_monthly",
    "annual_rate", "term_months",
)


def input_values(application):
    return {key: str(Decimal(str(application.get(key, "0"))).normalize()) for key in INPUT_KEYS}


def payment_factor(annual_rate: Decimal, months: int):
    monthly_rate = annual_rate / Decimal("1200")
    if monthly_rate == 0:
        return Decimal(1) / months
    return monthly_rate / (1 - (1 + monthly_rate) ** -months)


def estimate_loan(application, assumptions):
    values = input_values(application)
    v = {key: Decimal(value) for key, value in values.items()}
    dti_cap = Decimal(str(assumptions["max_dti_percent"]))
    ltv_cap = Decimal(str(assumptions["max_ltv_percent"]))
    closing_percent = Decimal(str(assumptions["closing_cost_percent"]))
    missing = []
    if v["annual_income"] <= 0:
        missing.append("Annual income")
    if v["purchase_price"] <= 0:
        missing.append("Target purchase price")
    if v["annual_rate"] <= 0:
        missing.append("Hypothetical interest rate")
    if v["requested_loan"] <= 0:
        missing.append("Requested loan amount")

    gross_monthly = v["annual_income"] / 12
    existing_monthly = v["monthly_debt"] + v["current_housing_payment"]
    property_monthly = (v["property_tax_annual"] + v["insurance_annual"]) / 12 + v["hoa_monthly"]
    max_housing = max(Decimal(0), gross_monthly * dti_cap / 100 - existing_monthly)
    max_pi = max(Decimal(0), max_housing - property_monthly)
    factor = payment_factor(v["annual_rate"], int(v["term_months"]))
    debt_based_max = max_pi / factor
    price = v["purchase_price"]
    ltv_based_max = price * ltv_cap / 100
    estimated_max = min(price, debt_based_max, ltv_based_max) if price > 0 else debt_based_max
    closing_costs = price * closing_percent / 100
    requested_pi = v["requested_loan"] * factor
    requested_housing = requested_pi + property_monthly
    requested_dti = (existing_monthly + requested_housing) / gross_monthly * 100 if gross_monthly > 0 else None
    requested_ltv = v["requested_loan"] / price * 100 if price > 0 else None
    cash_needed = max(Decimal(0), price - v["requested_loan"]) + closing_costs + v["reserves"]
    cash_at_max = max(Decimal(0), price - estimated_max) + closing_costs + v["reserves"]
    reasons = []
    if not missing:
        if v["requested_loan"] > price:
            reasons.append("Requested loan exceeds the target purchase price.")
        if requested_dti > dti_cap:
            reasons.append("Monthly debts plus the proposed housing payment exceed the practice DTI limit.")
        if requested_ltv > ltv_cap:
            reasons.append("Requested loan exceeds the practice loan-to-value limit.")
        if cash_needed > v["liquid_assets"]:
            reasons.append("Available assets do not cover the down payment, estimated closing costs, and stated reserves.")
        if cash_at_max > v["liquid_assets"]:
            reasons.append("No loan at or below the modeled maximum covers the required cash for this price.")
    status = "needs_information" if missing else "outside_assumptions" if reasons else "within_assumptions"
    warnings = ["Expected rent is excluded; using it to qualify requires a separate documented review."]
    if price > 0 and v["down_payment"] > 0 and abs(v["down_payment"] - (price - v["requested_loan"])) > Decimal("0.01"):
        warnings.append("Entered down payment differs from target price minus requested loan; cash required uses price minus loan.")
    if v["current_housing_payment"] == 0:
        warnings.append("Current housing payment is zero; confirm this is accurate for the rental purchase scenario.")
    if v["property_tax_annual"] == 0 or v["insurance_annual"] == 0:
        warnings.append("Property tax or insurance is zero; add realistic estimates before relying on the exercise.")
    warnings.append("Credit, appraisal, program eligibility, fees, and document verification were not evaluated.")
    return {
        "status": status,
        "missing": missing,
        "reasons": reasons,
        "warnings": warnings,
        "gross_monthly_income": q(gross_monthly),
        "existing_monthly_debts_including_housing": q(existing_monthly),
        "property_costs_monthly": q(property_monthly),
        "maximum_housing_payment": q(max_housing),
        "debt_based_max_loan": q(debt_based_max),
        "ltv_based_max_loan": q(ltv_based_max),
        "illustrative_max_loan": q(estimated_max) if not missing and cash_at_max <= v["liquid_assets"] else None,
        "requested_principal_interest": q(requested_pi),
        "requested_total_housing_payment": q(requested_housing),
        "requested_dti_percent": q(requested_dti) if requested_dti is not None else None,
        "requested_ltv_percent": q(requested_ltv) if requested_ltv is not None else None,
        "estimated_closing_costs": q(closing_costs),
        "cash_required_for_requested_loan": q(cash_needed),
        "cash_available": q(v["liquid_assets"]),
        "reserves_held_back": q(v["reserves"]),
        "rent_counted": False,
    }
