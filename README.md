# InvestOffice

A commercial lending workspace for a fictional community bank. Built with **Next.js + TypeScript, FastAPI + Python, and PostgreSQL**, with a no-Docker SQLite development option. All Harbor data is synthetic. No AI credentials, paid services, or cloud accounts are required.

The completed first milestone follows one case from CSV intake through analysis, stress testing, an editable memo, independent review, and subsequent-period monitoring. The application supports human judgment. It does not score applicants, estimate default probabilities, automatically approve credit, or disburse funds.

## Run locally

Requirements: Node.js 20.9+ (tested with 24), Python 3.12+, and optionally Docker for PostgreSQL. Run commands from this project directory.

### Fastest path on Windows

```powershell
powershell -ExecutionPolicy Bypass -File scripts/dev.ps1
```

This installs dependencies, starts FastAPI on `127.0.0.1:8000`, starts Next.js on `127.0.0.1:3000`, and persists the demo in `investoffice.db`. The execution-policy flag applies only to this invocation; it does not change the machine policy. Stop with Ctrl+C. The script stops its backend child process too.

For PostgreSQL instead:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/dev.ps1 -Postgres
```

The PostgreSQL container binds only to loopback and retains data in a named volume. Its credentials are intentionally public **local-demo defaults**, not production secrets. Stop it with `docker compose stop db`.

### Manual setup (all platforms)

```sh
python -m venv .venv
# Windows PowerShell: .venv/Scripts/Activate.ps1
# macOS / Linux: source .venv/bin/activate
python -m pip install -r backend/requirements.txt
npm ci
```

Choose your database. No `.env` is needed for the SQLite fallback. For PostgreSQL, copy `.env.example` to `.env`, keep its PostgreSQL URL, then run:

```sh
docker compose up -d --wait db
```

In separate terminals:

```sh
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
npm run dev
```

On macOS / Linux, `bash scripts/dev.sh` runs the SQLite option in one terminal. An existing `DATABASE_URL` environment variable takes precedence over `.env`. The convenience scripts default to SQLite unless PostgreSQL is explicitly selected.

Open [InvestOffice](http://127.0.0.1:3000). Interactive backend API documentation is at [localhost:8000/docs](http://127.0.0.1:8000/docs). The schema and Harbor fixtures are created once on first startup. Restarting preserves edits.

For a local production build, run `npm run build` and `npm start` while FastAPI is running. This is still a **local demo**, not a production banking deployment.

## Walk through the flagship demo

1. Choose **Alex Morgan**, the analyst. Harbor opens with monthly reports, bank transactions, payables, and debt already persisted. Receivables intentionally await intake.
2. Open **Financial intake**. Download the example CSV and upload it, or choose **Use Harbor sample** with Receivables selected. Review the first eight rows and validation results, then **Commit 224 records**. Both paths use the same multipart-upload API.
3. Open **Repayment analysis**. Verify $1.2 million annual revenue, $84,000 cash available for debt service, $35,550 existing debt service, and 2.36× coverage. The complete invoices identify Atlas as 40% of trailing sales.
4. Open **Cash flow scenarios** and run the default additional 30-day collection delay. Each run saves a new immutable version. Inspect baseline versus stress, the weekly cash waterfall, and the assumptions. The stress requires approximately $55,053 extra liquidity to preserve a $15,000 weekly cash buffer.
5. Open **Credit memo & review**. Generate the deterministic template, edit the recommendation, save, and submit. The most recently saved scenario is included. Submission locks the period and freezes the profile, source records, metrics, scenario, and memo.
6. Sign out with the icon beside the sidebar identity. Choose **Jordan Lee**, the reviewer. Read the frozen memo and analysis, enter a comment, and request changes, approve, or decline. Approval is visibly labeled as a simulation. Analyst attempts to review are rejected by the server.
7. Return as Alex. In **Ongoing monitoring**, load **Later receivables**, preview, and commit 240 records. Return to Monitoring, load **Later financial report**, preview, and commit its one row. These later reports can be imported while the historical case is locked.
8. Evaluate monitoring using the explicit demo clock **2026-02-16**. January DSO is 74.40 days, above the configured internal warning of 70. Assign the alert, record a follow-up note, and resolve it. The December submission stays unchanged.

To test missing-report alerts, evaluate before importing January's monthly report. Previously generated alerts remain as historical work items until someone resolves them; correcting the source data does not silently erase their history.

## What is implemented

| Component | Working behavior |
|---|---|
| Case file | Create empty cases; persist ownership, purpose, terms, amount, proposed-debt assumptions, and received/verified checklist status |
| Intake | Five CSV templates, examples, local file uploads, previews, row-level validation, duplicate prevention, correction revisions, downloadable original sources |
| Analysis | Trailing-year CADS and DSCR; current ratio and net working capital; reconciled invoice concentration; due-date aging; monthly DSO; explicit proposed-debt comparison |
| Scenarios | Reconciled opening records; 13 weekly cash periods; collection, sales, and cost stress; cash buffer; proposed draw, interest, and maturity; saved versions |
| Memo/review | Editable deterministic template; version conflicts; draft → submitted → changes requested / approved / declined; immutable submissions; separate server-enforced reviewer identity |
| Monitoring | Later-period imports; configurable reporting deadline; internal DSO warning; explicitly enabled illustrative DSCR covenant; precise unrounded comparisons; assignment, notes, resolution |

The optional DSCR covenant is **off by default**. Enabling it means the analyst explicitly configures an illustrative contractual condition. It is not a legal or universal banking requirement. Its calculation definition and trailing-year period are visible and fixed; unsupported alternative definitions are rejected.

## Why this architecture

Next.js handles presentation and proxies `/api` to FastAPI. FastAPI owns validation, financial arithmetic, permissions, workflow, and database writes. Keeping the business rules in one Python backend means a browser cannot change a ratio or approve its own case by altering frontend state.

SQLAlchemy uses the same schema with PostgreSQL and SQLite. Records are versioned rather than overwritten. Monetary values cross the API and are stored in JSON as decimal strings; Python `Decimal` handles calculations. JavaScript numbers are used only for chart coordinates and display formatting. See [architecture](docs/ARCHITECTURE.md), [financial definitions](docs/FINANCIAL_MODEL.md), and [CSV contracts](docs/CSV_GUIDE.md).

Supabase is not configured, so this implementation does not pretend to provide it. The local session adapter has two fixed identities and an opaque, expiring, HttpOnly session cookie. This tests role separation, **not identity assurance**. Setting `DEMO_MODE=false` fails closed until real authentication is implemented. No secrets belong in `NEXT_PUBLIC_*` variables.

## Verification

```sh
python -m pytest backend/tests -q
npm run typecheck
npm run build
```

The test suite covers ledger reconciliation, the complete API journey, immutable snapshots, missing data, malformed imports, duplicate files, corrections, authorization, workflow transitions, stale scenarios, proposed draws/maturity, monitoring, and a rounding-sensitive covenant breach. Each test uses an isolated in-memory database by default.

For the same suite against a **disposable PostgreSQL test database**, set `TEST_DATABASE_URL` to a PostgreSQL database whose name ends in `_test`. The fixture drops/recreates its tables before each test. Never point it at working data. CI provisions an isolated `investoffice_test` database and runs both adapters. PostgreSQL integration is configured in CI; this machine did not have Docker, so local verification used SQLite.

See [validation notes](docs/VALIDATION.md) for the browser acceptance walkthrough and checked financial results.

## Replay the demo without losing prior work

Stop both servers. With the default SQLite path, run:

```sh
python scripts/fresh_demo.py
```

This **archives** the database under `backups/`, preserving all prior work. Restart the backend to seed a fresh Harbor case. For PostgreSQL, use a new local database name instead. Never remove the named database volume as a routine reset.

## Deliberate boundaries

This milestone does not include arbitrary PDF extraction, AI memo drafting, production SSO/Supabase integration, real document binary storage, disbursement, live bank feeds, or validated credit scoring. Checklists record document status; structured CSV sources are retained in the database. The fixed demo identities must not be exposed on a public network. Before real deployment, add authenticated identity mapping, bank-level tenancy and authorization, migrations, backup/recovery, operational controls, retention policy, and independent model review.

AI assisted the implementation, not the lending decisions. The app itself makes no AI calls. Financial outputs have visible definitions and traceable inputs; reviewers retain responsibility for simulated decisions.
