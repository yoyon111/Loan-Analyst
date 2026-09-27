# Financial definitions and synthetic assumptions

## Harbor's cash-timing story

Harbor sells $100,000 each month and earns a positive operating profit. It grants customers 60 days to pay but pays suppliers after 30 days. Two months of sales can sit in receivables while only one month of purchases is financed by suppliers. That gap consumes cash even when the income statement looks healthy.

This is an illustrative wholesale distributor, not an actual borrower. Names, geography, ownership, invoices, payments, expenses, debt, and thresholds are synthetic. Supplier purchases equal cost of sales, keeping inventory at $65,000. Maintenance capex equals depreciation, keeping net fixed assets at $120,000. Taxes are a synthetic cash expense equal to the assumed tax expense, with no deferred taxes or other assets/liabilities modeled.

The [FDIC's commercial and industrial lending material](https://www.fdic.gov/credit/commercial-industrial-lending) provides general context for working-capital analysis. It does not prescribe this application's formulas or its sample thresholds.

## Source records and reconciliation

The deterministic generator creates four customer invoices on each of four issue dates per month. Atlas represents 40%, Northstar 25%, Elm 20%, and Cedar 15%. Each invoice's due date is exactly 60 calendar days after issue. Supplier bills are $16,250 per issue date, due after 30 days. The first receivables file includes November–December 2024 opening invoices plus the 2025 invoices: 224 records in all.

Opening at 2024-12-31:

| Balance | USD |
|---|---:|
| Cash | 22,000 |
| Receivables | 200,000 |
| Inventory | 65,000 |
| Net fixed assets | 120,000 |
| Payables | 65,000 |
| Term debt | 60,000 |
| Equity | 282,000 |

Assets of $407,000 equal liabilities of $125,000 plus equity of $282,000. Each monthly closing cash balance equals opening cash plus bank transactions through that date. Each monthly balance sheet balances. Invoice totals reconcile to reported annual sales and ending receivables. Synthetic internal transfers are a $5,000 in/out pair; they do not create revenue.

The equipment loan starts at $60,000, pays $2,500 principal monthly, and charges 1% of opening monthly principal in interest. The schedule contains separate principal, interest, and maturity fields. Scheduled 2025 debt service is $30,000 principal plus $5,550 interest. The schedule continues through December 2026; final ordinary principal amortization repays the balance, with no separate balloon.

## Historical cash available for debt service (CADS)

The demo defines:

```text
EBITDA = revenue − COGS − payroll − other operating expenses
Operating working capital = receivables + inventory − payables
Δ operating working capital = closing − opening
CADS = EBITDA − cash taxes − maintenance capex − distributions − Δ operating working capital
Debt service = scheduled principal + interest + maturity principal
DSCR = CADS / debt service
```

Do not subtract depreciation from CADS: it is noncash. Do not subtract interest in CADS and again in the denominator. A positive working-capital increase consumes cash; a decrease releases cash. This is a simplified cash-availability proxy and not a universal definition of DSCR. It assumes the reported operating accounts and cash items capture the business's relevant cash demands.

For 2025: EBITDA $132,000; cash taxes $24,000; maintenance capex $12,000; distributions $12,000; change in operating working capital $0. CADS is $84,000. Dividing by $35,550 of debt service gives 2.362869…×, displayed as 2.36×.

All 12 consecutive monthly reports, a supported opening working-capital balance, and explicit debt-schedule coverage for the period are required. A new case can provide the opening point by importing a prior-year month-end financial report. Missing source data returns null with reasons; it is not treated as zero. A zero-debt-service denominator returns insufficient data rather than an infinite ratio.

## Liquidity, collections, and concentration

```text
Current assets = cash + receivables + inventory
Current liabilities = payables + current portion of debt
Current ratio = current assets / current liabilities
Net working capital = current assets − current liabilities
Monthly DSO approximation = ending unpaid invoice balance / monthly revenue × calendar days in month
Customer concentration = that customer's invoice sales / total trailing-year invoice sales
```

Current ratio is 335,450 / 95,000 = 3.53× at December 2025. Liquidity measures use the reported balance sheet, with discrepancies to invoice detail surfaced separately. DSO requires an exact month-end snapshot reconciled to the reported receivables balance. Concentration requires invoice sales to reconcile to the full trailing-year revenue; it is not computed from only a partial upload or unpaid invoices.

Aging uses **days past due**, not days since sale. Due today is current; buckets are current, 1–30, 31–60, 61–90, and over 90 days. Every invoice's remaining amount is original amount less cumulative paid amount. Payment amounts cannot exceed invoice amounts. A stale snapshot is not silently treated as a current one.

Sales are accrual revenue at invoice issue. Bank receipts settle invoices on payment dates. The importer never equates deposits with sales or requires a month's receipts to equal its sales. The regular 2025 demo happens to have stable monthly sales and receipts; January 2026 makes the distinction explicit.

## Proposed financing

A $100,000 limit is not automatically a $100,000 draw. Historical existing-debt coverage excludes the proposed facility. To compute a separate illustrative comparison, enter an assumed constant draw, annual interest rate, and principal due within the comparison year:

```text
Illustrative added annual interest = assumed draw × annual rate / 100
Combined DSCR = historical CADS / (existing debt service + added interest + proposed principal due)
```

The numerator remains the historical CADS; this is an illustrative comparison, not a future income prediction. The model does not assume renewal at maturity. Without those terms, proposed-debt coverage is insufficient data.

## Thirteen-week cash forecast

The forecast begins the day after a supported month-end report and runs exactly 91 days. Both receivable and payable snapshots must be dated at the same month-end and reconcile to the opening balances. Debt coverage is required across all forecast months.

1. Collect only **unpaid opening invoices** on their due dates plus the selected extra delay. Overdue opening invoices are assumed collected in week one before the extra delay.
2. Start modeled new sales only after the opening date. Their receipts occur only after the reported collection lag plus the extra delay. An opening invoice is never also included as a new forecast sale.
3. Pay unpaid opening bills at their due dates, or in week one if overdue. Future purchases use daily run-rate COGS and the supplier lag.
4. Future daily sales and COGS use the last reported month's amount divided by that month's calendar days. The sales stress scales both future sales and future purchases. The selected cost stress scales COGS and other operating expenses; payroll, tax, capex, and owner distributions stay unchanged.
5. Payroll and other recurring cash items are assumed paid weekly at monthly amount × 12 / 365 × 7. They are forecasts, not transaction-level payroll calendars.
6. Existing debt payments use the actual scheduled due dates. A proposed draw arrives in week one as a **financing inflow**. Proposed interest uses simple ACT/365 on the assumed draw; the selected maturity week repays principal in full, after which interest stops. With maturity outside the horizon, the outstanding balance remains an obligation beyond week 13.
7. Compare baseline and stress cash at each week-end. Include opening cash in the low-point calculation. Additional funding need = max(0, configured buffer − lowest cash). This measures **weekly endpoint** liquidity and may miss an intraday shortfall. It is not a recommended commitment size or automatic loan-sizing decision.

At the default 30-day delay, zero added draw, and $15,000 buffer, the stressed low point is approximately −$40,053; additional funding need is approximately $55,053. The no-delay baseline stays positive. Scenario versions store assumptions and results so a reviewer can reproduce the exact selected run.

## Later-period monitoring

The January sample delays Atlas receipts by an additional 45 days for payments originally due in 2026. January collections fall from $100,000 to $60,000 while invoice sales remain $100,000. Ending receivables rise to $240,000 and cash falls to $34,650. January DSO becomes 240,000 / 100,000 × 31 = **74.40 days**. The internal 70-day warning prompts an updated aging and collection plan.

The optional DSCR covenant uses the same CADS definition over the **trailing 12 months**, including working-capital change from the preceding year's month-end. It is disabled until explicitly configured. January's trailing CADS is $44,000 and debt service is $35,250: the exact ratio is 1.248226…×. Although display rounding shows 1.25×, it breaches a configured minimum of 1.25×. **Condition comparisons use the unrounded Decimal result.**

Reporting alerts use a user-visible evaluation date instead of silently depending on today's date. This makes the synthetic story repeatable. Reports are overdue only after their configured deadline. Unsupported condition calculations create a data-quality work item, not a fabricated breach. Resolved alerts do not automatically reopen on repeated evaluation of the same period; a new period gets a new alert. Old alerts remain reviewable after the source condition clears.

## Precision

Currency inputs allow no more than two decimals and reject nonfinite values. Stored source values are decimal strings. Calculations retain `Decimal` precision and round output cents and displayed ratios with **ROUND_HALF_UP**. Weekly internal arithmetic retains precision until output, so summing rounded displayed components can differ by a few cents from the rounded total. Dashboard and table monetary formatting uses whole dollars for readability; API/source outputs retain cents. JavaScript does not perform underwriting calculations.
