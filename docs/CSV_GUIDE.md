# CSV intake contracts

Download templates/examples from Financial intake or use the files under `examples/`. All five use UTF-8, a comma delimiter, the exact header order shown below, and a header row. Excel UTF-8 BOM files are accepted. Maximum file size is 2 MB / 10,000 rows. Quoted commas in text are supported.

Money uses plain decimal text such as `1250.00`, without `$`, commas, or more than two decimal places. Missing numeric values are errors, not zeros. Dates use `YYYY-MM-DD`; monthly periods use `YYYY-MM`. Every row carries `synthetic=true` or `false`. All supplied examples use `true`.

## Receivables

```csv
invoice_id,customer,invoice_date,due_date,amount,paid_amount,last_payment_date,as_of,synthetic
```

One complete invoice-history snapshot per file, including already-paid invoices. `amount` is the original sale, `paid_amount` is cumulative settled principal through `as_of`, and `last_payment_date` is the latest settlement date. Leave that date empty only for unpaid invoices. Due date cannot precede issue; payment date must fall between issue and snapshot. The same invoice can reappear in a later snapshot without being a duplicate.

Logical record key: **invoice_id + as_of**. This protects historical snapshots while later balances evolve. Include enough history to reconcile trailing-year invoice sales for customer concentration. A partial file may validate row formats but will not support complete financial calculations until it reconciles.

## Payables

```csv
bill_id,supplier,bill_date,due_date,amount,paid_amount,as_of,synthetic
```

One complete bill snapshot per file. Payment is cumulative through the snapshot. Logical key: **bill_id + as_of**. Amounts must be nonnegative; cumulative payments cannot exceed the bill. The forecast only pays the unpaid portion of opening bills.

## Monthly financials

```csv
period,revenue,cogs,payroll,operating_expenses,depreciation,interest_expense,cash_taxes,maintenance_capex,distributions,cash,receivables,inventory,payables,current_debt,fixed_assets,long_term_debt,equity,synthetic
```

One row per month; logical key: **period**. Income/cash-flow fields are monthly activity, not year-to-date totals. Balance-sheet fields are month-end balances. `current_debt` is principal due within the next twelve months; `long_term_debt` is the remainder. Expenses are positive values. Cash and equity may be negative. Assets must equal liabilities plus equity within one cent.

`operating_expenses` excludes payroll, COGS, depreciation, and interest to avoid double-counting. `cash_taxes`, maintenance capex, and owner distributions are cash outflows used in CADS. Do not enter total capex as maintenance capex without documenting that assumption.

## Bank transactions

```csv
transaction_id,date,category,amount,reference,synthetic
```

Logical key: **transaction_id**. Inflows are positive and outflows negative. Allowed categories:

| Category | Meaning / sign |
|---|---|
| customer_receipt | Cash settling customer invoices; positive |
| loan_proceeds | Financing inflow; positive; never revenue |
| internal_transfer | Signed transfer between included accounts; record both sides when both accounts are within scope |
| supplier_payment | Negative payment of trade bills |
| payroll | Negative cash payroll |
| operating_expense | Negative other operating cash cost |
| cash_tax | Negative tax payment |
| maintenance_capex | Negative maintenance investment |
| distribution | Negative owner distribution |
| debt_principal | Negative debt amortization |
| debt_interest | Negative interest payment |

`reference` links a receipt to its invoice or a payment to a bill/debt installment when applicable. The monthly financial report remains the accrual revenue source; bank deposits are not automatically classified as revenue.

## Debt schedules

```csv
payment_id,facility,due_date,principal,interest,maturity_amount,synthetic
```

Logical key: **payment_id**. All three amounts are nonnegative expected cash outflows. `principal` is ordinary amortization; `maturity_amount` is additional principal due at maturity, excluding any principal already in the ordinary field. Explicitly report a zero installment for a month with no scheduled payments if it is within the required analysis period. Do not omit a month and expect the engine to assume no debt service.

## Preview, commit, and correct

Uploading stores a preview batch and its source text; it does **not** change financial records. Errors name the row, field, and action needed. A valid preview can be committed once. The commit is atomic: either all financial records persist or none do.

Exact duplicate files are detected by a normalized line-ending SHA-256 digest. Renamed/reordered files are also checked by record keys. To change an existing key, provide a correction reason and upload corrected rows. The new revision supersedes the record for future calculations while the old row and source batch remain in the audit history. A file containing only unchanged records is rejected even if a correction reason is supplied.

Corrections update included keys; they do not delete records omitted from a replacement file. Correct a mistaken amount/payment explicitly. Do not attempt to remove an invoice by leaving it out of a new same-date snapshot. Validation rejects malformed, incomplete rows; cross-schedule discrepancies are surfaced in analysis and block unsupported forecasts.

Submitted periods are locked. Later snapshots/reports remain importable, but prior-period corrections require the reviewer to request changes. The submitted record snapshot never changes, even after later imports or corrections.

The current intake does not parse PDFs or validate every possible accounting policy. It validates structural consistency and the relationships used by this demo. Source verification remains an analyst task.
