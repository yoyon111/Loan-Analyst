"""Deterministic comparisons for fictional fixed-rate rental mortgage offers."""

from decimal import Decimal

from .finance import q
from .individual_estimate import payment_factor, input_values


def evaluate_offer(application, terms, assumptions):
    price = Decimal(str(application.get("purchase_price", 0)))
    assets = Decimal(str(application.get("liquid_assets", 0)))
    income = Decimal(str(application.get("annual_income", 0))) / 12
    existing = Decimal(str(application.get("monthly_debt", 0))) + Decimal(str(application.get("current_housing_payment", 0)))
    property_cost = (Decimal(str(application.get("property_tax_annual", 0))) + Decimal(str(application.get("insurance_annual", 0)))) / 12 + Decimal(str(application.get("hoa_monthly", 0)))
    loan = Decimal(str(terms["loan_amount"]))
    rate = Decimal(str(terms["annual_rate"]))
    months = int(terms["term_months"])
    points_cost = loan * Decimal(str(terms["points_percent"])) / 100
    lender_cost = points_cost + Decimal(str(terms["lender_fees"])) - Decimal(str(terms["lender_credits"]))
    closing = lender_cost + Decimal(str(terms["other_closing_costs"]))
    cash_to_close = price - loan + closing
    reserves = assets - cash_to_close
    pi = loan * payment_factor(rate, months)
    housing = pi + property_cost + Decimal(str(terms["mortgage_insurance_monthly"]))
    dti = (existing + housing) / income * 100 if income > 0 else None
    ltv = loan / price * 100 if price > 0 else None
    balance = loan
    interest_five_years = Decimal(0)
    for _ in range(min(60, months)):
        interest = balance * rate / 1200
        interest_five_years += interest
        balance = max(Decimal(0), balance + interest - pi)
    reasons = []
    if price <= 0 or income <= 0:
        reasons.append("Enter a purchase price and annual income.")
    if loan > price and price > 0:
        reasons.append("Loan exceeds the purchase price.")
    if dti is not None and dti > Decimal(str(assumptions["max_dti_percent"])):
        reasons.append("Debt-to-income exceeds the practice limit.")
    if ltv is not None and ltv > Decimal(str(assumptions["max_ltv_percent"])):
        reasons.append("Loan-to-value exceeds the practice limit.")
    if reserves < Decimal(str(application.get("reserves", 0))):
        reasons.append("Cash after closing falls below the entered reserve amount.")
    if cash_to_close < 0:
        reasons.append("Cash to close is negative; review the offer inputs.")
    return {
        "status": "needs_information" if price <= 0 or income <= 0 else "outside_assumptions" if reasons else "within_assumptions",
        "reasons": reasons,
        "monthly_principal_interest": q(pi),
        "monthly_total_housing": q(housing),
        "monthly_property_costs": q(property_cost),
        "monthly_mortgage_insurance": q(Decimal(str(terms["mortgage_insurance_monthly"]))),
        "dti_percent": q(dti) if dti is not None else None,
        "ltv_percent": q(ltv) if ltv is not None else None,
        "points_cost": q(points_cost),
        "estimated_closing_costs": q(closing),
        "cash_to_close": q(cash_to_close),
        "cash_after_closing": q(reserves),
        "five_year_interest_and_lender_cost": q(interest_five_years + lender_cost),
        "balance_after_five_years": q(balance),
        "rent_counted_for_qualification": False,
        "practice_only": True,
    }


def offer_inputs(application):
    values = input_values({"current_housing_payment": "0", **application})
    # Each option supplies its own loan amount, rate, and term. Changing the
    # worksheet's proposed terms does not invalidate a saved option.
    return {key: value for key, value in values.items()
            if key not in ("requested_loan", "annual_rate", "term_months", "down_payment")}
