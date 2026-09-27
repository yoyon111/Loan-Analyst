import hashlib
import os
import secrets
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone, date
from decimal import Decimal
from pathlib import Path
from uuid import uuid4
from fastapi import (
    FastAPI,
    Depends,
    HTTPException,
    UploadFile,
    File,
    Form,
    Request,
    Response,
)
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import StaleDataError
from .db import (
    Base,
    engine,
    Session,
    Case,
    ImportBatch,
    Record,
    Scenario,
    Submission,
    Review,
    Alert,
    Event,
    LoginSession,
    records,
    event,
)
from .seed import seed, write_examples, HEADERS, record_key
from .intake import validate
from .finance import analysis, forecast, q

USERS = {
    "analyst": {"id": "analyst", "name": "Alex Morgan", "role": "analyst"},
    "reviewer": {"id": "reviewer", "name": "Jordan Lee", "role": "reviewer"},
}


def uid():
    return str(uuid4())


@asynccontextmanager
async def lifespan(app):
    if os.getenv("DEMO_MODE", "true").lower() != "true":
        raise RuntimeError(
            "Production authentication is not configured. Demo identities are only supported in local DEMO_MODE=true."
        )
    Base.metadata.create_all(engine)
    with Session() as db:
        seed(db)
    write_examples()
    yield


app = FastAPI(title="InvestOffice", version="1.0.0", lifespan=lifespan)


@app.middleware("http")
async def local_security(request, call_next):
    # Browser writes require a same-site local origin. Cookies are HttpOnly and SameSite strict.
    origin = request.headers.get("origin")
    if (
        request.method not in ("GET", "HEAD", "OPTIONS")
        and origin
        and origin
        not in ("http://127.0.0.1:3000", "http://localhost:3000", "http://testserver")
    ):
        from fastapi.responses import JSONResponse

        return JSONResponse(
            {"detail": "This local demo does not accept cross-origin writes."},
            status_code=403,
        )
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Cache-Control"] = "no-store"
    return response


def database():
    with Session() as db:
        try:
            yield db
        except StaleDataError:
            db.rollback()
            raise HTTPException(
                409, "This case changed in another session. Reload and try again."
            )
        except IntegrityError:
            db.rollback()
            raise HTTPException(
                409, "This record was already saved. Reload to see the latest state."
            )


def user(request: Request, db=Depends(database)):
    token = request.cookies.get("investoffice_session", "")
    session = db.get(LoginSession, hashlib.sha256(token.encode()).hexdigest())
    if not session or session.expires_at < datetime.now(timezone.utc).isoformat():
        raise HTTPException(401, "Select a demo identity to continue.")
    return USERS[session.user_id]


def get_case(db, id):
    case = db.get(Case, id)
    if not case:
        raise HTTPException(404, "Case not found.")
    return case


def analyst(u):
    if u["role"] != "analyst":
        raise HTTPException(403, "Only analysts can change case analysis.")


def editable(case, u):
    analyst(u)
    if case.status not in ("draft", "changes_requested"):
        raise HTTPException(
            409,
            "The submitted case is locked. The reviewer must request changes before it can be edited.",
        )


class LoginInput(BaseModel):
    identity: str


@app.post("/api/auth/login")
def login(body: LoginInput, response: Response, request: Request, db=Depends(database)):
    if body.identity not in USERS:
        raise HTTPException(400, "Choose analyst or reviewer.")
    old = request.cookies.get("investoffice_session", "")
    if old:
        db.query(LoginSession).filter_by(
            token_hash=hashlib.sha256(old.encode()).hexdigest()
        ).delete()
    token = secrets.token_urlsafe(32)
    db.add(
        LoginSession(
            token_hash=hashlib.sha256(token.encode()).hexdigest(),
            user_id=body.identity,
            expires_at=(datetime.now(timezone.utc) + timedelta(hours=12)).isoformat(),
        )
    )
    db.commit()
    response.set_cookie(
        "investoffice_session",
        token,
        httponly=True,
        samesite="strict",
        max_age=43200,
        path="/",
    )
    return USERS[body.identity]


@app.get("/api/auth/me")
def me(u=Depends(user)):
    return u


@app.post("/api/auth/logout")
def logout(request: Request, response: Response, db=Depends(database)):
    db.query(LoginSession).filter_by(
        token_hash=hashlib.sha256(
            request.cookies.get("investoffice_session", "").encode()
        ).hexdigest()
    ).delete()
    db.commit()
    response.delete_cookie("investoffice_session", path="/")
    return {"ok": True}


@app.get("/api/health")
def health():
    return {"status": "ok", "mode": "local synthetic demo"}


@app.get("/api/cases")
def cases(db=Depends(database), u=Depends(user)):
    return [
        dict(id=c.id, profile=c.profile, status=c.status) for c in db.query(Case).all()
    ]


class NewCase(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    industry: str = Field(default="Small business", max_length=120)
    amount: Decimal = Field(gt=0, le=100000000)


@app.post("/api/cases")
def create_case(body: NewCase, db=Depends(database), u=Depends(user)):
    analyst(u)
    id = uid()
    profile = dict(
        name=body.name,
        industry=body.industry,
        requested_amount=q(body.amount),
        purpose="",
        location="",
        owner="",
        reported_collection_days=60,
        supplier_terms_days=30,
        verified=False,
        documents=[
            {"name": name, "received": False, "verified": False}
            for name in ["Financial statements", "Accounts receivable aging", "Business tax returns", "Existing debt schedule", "Ownership and guarantor information"]
        ],
        opening={},
        conditions=[],
        reporting_deadline="",
        expected_report_period="",
        synthetic=True,
    )
    db.add(Case(id=id, owner_id=u["id"], profile=profile))
    db.flush()
    event(db, id, u["id"], "Case created")
    db.commit()
    return {"id": id}


@app.get("/api/cases/{id}")
def case_detail(id: str, db=Depends(database), u=Depends(user)):
    c = get_case(db, id)
    submissions = (
        db.query(Submission)
        .filter_by(case_id=id)
        .order_by(Submission.created_at.desc())
        .all()
    )
    reviews = (
        db.query(Review)
        .filter(Review.submission_id.in_([s.id for s in submissions]))
        .order_by(Review.created_at.desc())
        .all()
        if submissions
        else []
    )
    return dict(
        id=id,
        profile=c.profile,
        status=c.status,
        memo=c.memo,
        version=c.version,
        owner_id=c.owner_id,
        submissions=[
            dict(
                id=s.id,
                memo=s.memo,
                snapshot=s.snapshot,
                author_id=s.author_id,
                created_at=s.created_at,
            )
            for s in submissions
        ],
        reviews=[
            dict(
                id=r.id,
                decision=r.decision,
                comment=r.comment,
                reviewer_id=r.reviewer_id,
                created_at=r.created_at,
            )
            for r in reviews
        ],
        events=[
            dict(
                id=e.id,
                actor=e.actor,
                action=e.action,
                detail=e.detail,
                created_at=e.created_at,
            )
            for e in db.query(Event)
            .filter_by(case_id=id)
            .order_by(Event.id.desc())
            .limit(30)
        ],
    )


class Document(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    received: bool
    verified: bool


class ProposedTerms(BaseModel):
    draw: Decimal = Field(ge=0, le=100000000)
    annual_rate: Decimal = Field(ge=0, le=100)
    principal_due: Decimal = Field(ge=0, le=100000000)


class ProfileInput(BaseModel):
    version: int
    name: str = Field(min_length=2, max_length=120)
    industry: str = Field(max_length=120)
    location: str = Field(max_length=120)
    owner: str = Field(max_length=200)
    purpose: str = Field(max_length=3000)
    requested_amount: Decimal = Field(gt=0, le=100000000)
    reported_collection_days: int = Field(ge=1, le=365)
    supplier_terms_days: int = Field(ge=1, le=365)
    verified: bool
    documents: list[Document] = Field(max_length=30)
    proposed_terms: ProposedTerms | None = None


@app.put("/api/cases/{id}/profile")
def save_profile(id: str, body: ProfileInput, db=Depends(database), u=Depends(user)):
    c = get_case(db, id)
    editable(c, u)
    if body.version != c.version:
        raise HTTPException(409, "Case changed. Reload before saving.")
    data = body.model_dump(mode="json", exclude={"version"})
    if any(d["verified"] and not d["received"] for d in data["documents"]):
        raise HTTPException(422, "A missing document cannot be verified.")
    if body.proposed_terms and body.proposed_terms.draw > body.requested_amount:
        raise HTTPException(422, "Assumed draw cannot exceed the requested limit.")
    c.profile = {**c.profile, **data}
    event(db, id, u["id"], "Borrower profile updated", {"verified": body.verified})
    db.commit()
    return {"ok": True}


@app.get("/api/examples/{filename}")
def example(filename: str):
    allowed = (
        {f"harbor-{k}.csv" for k in HEADERS}
        | {f"template-{k}.csv" for k in HEADERS}
        | {"harbor-receivables-2026-01.csv", "harbor-monthly-2026-01.csv"}
    )
    if filename not in allowed:
        raise HTTPException(404, "Example not found.")
    return PlainTextResponse(
        (Path(__file__).resolve().parents[1] / "examples" / filename).read_text(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/cases/{id}/imports")
def imports(id: str, db=Depends(database), u=Depends(user)):
    get_case(db, id)
    return [
        dict(
            id=b.id,
            kind=b.kind,
            filename=b.filename,
            status=b.status,
            count=len(b.rows),
            created_at=b.created_at,
            correction_reason=b.correction_reason,
        )
        for b in db.query(ImportBatch)
        .filter_by(case_id=id)
        .order_by(ImportBatch.created_at.desc())
    ]


@app.post("/api/cases/{id}/imports/preview")
async def preview(
    id: str,
    kind: str = Form(...),
    correction_reason: str = Form(""),
    file: UploadFile = File(...),
    db=Depends(database),
    u=Depends(user),
):
    c = get_case(db, id)
    analyst(u)
    if kind not in HEADERS:
        raise HTTPException(400, "Unknown CSV type.")
    if len(correction_reason) > 2000:
        raise HTTPException(422, "Correction reason is too long.")
    content = await file.read(2_000_001)
    if len(content) > 2_000_000:
        raise HTTPException(413, "Maximum file size is 2 MB.")
    try:
        raw = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(422, "Save the CSV as UTF-8.")
    rows, errors = validate(kind, raw)
    digest = hashlib.sha256(raw.replace("\r\n", "\n").encode()).hexdigest()
    old = db.query(ImportBatch).filter_by(case_id=id, kind=kind, digest=digest).first()
    if old:
        if old.status == "committed":
            raise HTTPException(
                409, "This exact file has already been imported. No records changed."
            )
        db.delete(old)
        db.flush()
    existing = {
        r.key: r.data
        for r in db.query(Record)
        .filter_by(case_id=id, kind=kind)
        .order_by(Record.revision)
        .all()
    }
    duplicates = [r for r in rows if record_key(kind, r) in existing]
    if duplicates and not correction_reason.strip():
        errors.append(
            {
                "row": 0,
                "field": "correction_reason",
                "message": f"{len(duplicates)} existing record keys. Provide a correction reason to preserve these as new revisions.",
            }
        )
    if (
        duplicates
        and correction_reason.strip()
        and all(existing[record_key(kind, r)] == r for r in duplicates)
        and len(duplicates) == len(rows)
    ):
        errors.append(
            {
                "row": 0,
                "field": "records",
                "message": "These records are unchanged. A renamed file is still a duplicate.",
            }
        )
    if kind in ("receivables", "payables") and len({r["as_of"] for r in rows}) > 1:
        errors.append(
            {
                "row": 0,
                "field": "as_of",
                "message": "Use a single snapshot date per file.",
            }
        )
    # Submitted analysis is frozen. Only reports for later periods can be imported while locked.
    if c.status not in ("draft", "changes_requested"):
        submissions = (
            db.query(Submission)
            .filter_by(case_id=id)
            .order_by(Submission.created_at.desc())
            .first()
        )
        cutoff = (
            submissions.snapshot["analysis"]["period_end"]
            if submissions
            else "9999-12-31"
        )
        row_date = lambda r: r.get(
            "as_of",
            (
                r.get("period", "") + "-01"
                if kind == "monthly"
                else r.get("date", r.get("due_date", ""))
            ),
        )
        if any(row_date(r) <= cutoff for r in rows):
            errors.append(
                {
                    "row": 0,
                    "field": "period",
                    "message": "Submitted periods are locked. Request changes or import only subsequent reporting periods.",
                }
            )
    bid = uid()
    b = ImportBatch(
        id=bid,
        case_id=id,
        kind=kind,
        filename=(file.filename or "upload.csv")[:200],
        raw=raw,
        digest=digest,
        rows=rows,
        errors=errors,
        status="invalid" if errors else "preview",
        correction_reason=correction_reason,
        created_by=u["id"],
    )
    db.add(b)
    db.commit()
    return dict(
        id=bid,
        count=len(rows),
        errors=errors,
        preview=rows[:8],
        columns=HEADERS[kind],
        corrections=len(duplicates),
        synthetic=all(r.get("synthetic") == "true" for r in rows),
    )


@app.post("/api/cases/{id}/imports/{bid}/commit")
def commit_import(id: str, bid: str, db=Depends(database), u=Depends(user)):
    c = get_case(db, id)
    analyst(u)
    b = db.get(ImportBatch, bid)
    if not b or b.case_id != id:
        raise HTTPException(404, "Import not found.")
    if b.status != "preview" or b.errors:
        raise HTTPException(409, "Only a valid, uncommitted preview can be committed.")
    # Recheck locks and duplicates at commit time; preview never authorizes stale changes.
    latest = (
        db.query(Submission)
        .filter_by(case_id=id)
        .order_by(Submission.created_at.desc())
        .first()
    )
    for row in b.rows:
        row_date = row.get(
            "as_of",
            (
                row.get("period", "") + "-01"
                if b.kind == "monthly"
                else row.get("date", row.get("due_date", ""))
            ),
        )
        if c.status not in ("draft", "changes_requested") and (
            not latest or row_date <= latest.snapshot["analysis"]["period_end"]
        ):
            raise HTTPException(
                409, "The period was locked after preview. Request changes first."
            )
        key = record_key(b.kind, row)
        prior = (
            db.query(Record)
            .filter_by(case_id=id, kind=b.kind, key=key)
            .order_by(Record.revision.desc())
            .first()
        )
        if prior and not b.correction_reason:
            raise HTTPException(
                409, "Records changed after preview. Preview this as a correction."
            )
        db.add(
            Record(
                case_id=id,
                kind=b.kind,
                key=key,
                data=row,
                import_id=bid,
                revision=prior.revision + 1 if prior else 1,
            )
        )
    b.status = "committed"
    c.version += 1
    if b.kind == "receivables":
        c.profile = {
            **c.profile,
            "documents": [
                (
                    {**d, "received": True, "verified": False}
                    if d["name"] == "Accounts receivable aging"
                    else d
                )
                for d in c.profile["documents"]
            ],
        }
    event(
        db,
        id,
        u["id"],
        "CSV import committed",
        {
            "import_id": bid,
            "kind": b.kind,
            "records": len(b.rows),
            "correction_reason": b.correction_reason,
        },
    )
    db.commit()
    return {"ok": True, "records": len(b.rows)}


@app.get("/api/cases/{id}/imports/{bid}/source")
def source(id: str, bid: str, db=Depends(database), u=Depends(user)):
    b = db.get(ImportBatch, bid)
    if not b or b.case_id != id:
        raise HTTPException(404, "Import not found.")
    return PlainTextResponse(
        b.raw,
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="source.csv"'},
    )


@app.get("/api/cases/{id}/analysis")
def metrics(id: str, period: str | None = None, db=Depends(database), u=Depends(user)):
    if period:
        try:
            date.fromisoformat(period + "-01")
        except ValueError:
            raise HTTPException(422, "Use YYYY-MM for the analysis period.")
    return analysis(db, get_case(db, id), period)


class ScenarioInput(BaseModel):
    name: str = Field(default="Delayed collections", min_length=1, max_length=120)
    period: str = "2025-12"
    delay_days: int = Field(default=30, ge=0, le=120)
    sales_change: Decimal = Field(default=Decimal("0"), ge=-100, le=100)
    cost_change: Decimal = Field(default=Decimal("0"), ge=-100, le=100)
    cash_buffer: Decimal = Field(default=Decimal("15000"), ge=0, le=10000000)
    draw: Decimal = Field(default=Decimal("0"), ge=0, le=100000000)
    annual_rate: Decimal = Field(default=Decimal("9"), ge=0, le=100)
    maturity_week: int | None = Field(default=None, ge=1, le=13)

    @field_validator("period")
    @classmethod
    def valid_period(cls, v):
        date.fromisoformat(v + "-01")
        return v


@app.post("/api/cases/{id}/scenarios")
def run_scenario(id: str, body: ScenarioInput, db=Depends(database), u=Depends(user)):
    c = get_case(db, id)
    editable(c, u)
    if body.draw > Decimal(c.profile["requested_amount"]):
        raise HTTPException(422, "Draw cannot exceed the requested credit limit.")
    inputs = body.model_dump(mode="json")
    result = forecast(db, c, inputs)
    if result["status"] != "complete":
        raise HTTPException(422, result["reason"])
    sid = uid()
    db.add(
        Scenario(id=sid, case_id=id, name=body.name, assumptions=inputs, result=result)
    )
    c.version += 1
    event(db, id, u["id"], "Scenario version saved", {"scenario_id": sid})
    db.commit()
    return {"id": sid, "name": body.name, "assumptions": inputs, "result": result}


@app.get("/api/cases/{id}/scenarios")
def scenarios(id: str, db=Depends(database), u=Depends(user)):
    get_case(db, id)
    return [
        dict(
            id=s.id,
            name=s.name,
            assumptions=s.assumptions,
            result=s.result,
            created_at=s.created_at,
        )
        for s in db.query(Scenario)
        .filter_by(case_id=id)
        .order_by(Scenario.created_at.desc())
    ]


def memo_template(c, a, s):
    latest = s.result if s else None
    top = a["concentration"][0] if a["concentration"] else None
    missing = (
        ", ".join(d["name"] for d in c.profile["documents"] if not d["received"])
        or "None identified in checklist"
    )
    return f"""CREDIT MEMO Â· {c.profile['name']}
Synthetic portfolio exercise Â· Human review required

FINANCING PURPOSE
Requested revolving limit: ${c.profile['requested_amount']}. {c.profile['purpose']}

PRIMARY REPAYMENT SOURCE
Collections of trade receivables. Reported customer collection cycle is {c.profile['reported_collection_days']} days, compared with supplier terms of {c.profile['supplier_terms_days']} days. Profit does not eliminate the cash timing gap. Confirm line utilization, cleanup expectations, and maturity repayment separately.

HISTORICAL FINANCIAL RESULTS Â· {a['period_start']} to {a['period_end']}
Sales: {a['revenue'] or 'insufficient data'}; EBITDA: {a['ebitda'] or 'insufficient data'}.
Cash available for debt service: {a['cads'] or 'insufficient data'}. Existing debt service: {a['debt_service'] or 'insufficient data'}; DSCR: {a['dscr'] or 'insufficient data'}.
Definition: EBITDA minus cash taxes, maintenance capital expenditure, distributions, and increase in operating working capital (receivables + inventory âˆ’ payables).
Including proposed financing: {a['proposed'].get('dscr','insufficient data')}. Proposed assumptions: {a['proposed'].get('terms','not supplied')}.

RISKS AND MITIGANTS TO INVESTIGATE
Largest customer: {top['name']+' ('+top['share']+'% of trailing sales)' if top else 'insufficient verified invoice coverage'}.
Assess customer payment history, disputed balances, dilution, inventory quality, and availability of additional liquidity. Reported data is not independently verified unless explicitly marked.

13-WEEK SCENARIO
{('Saved scenario: '+s.name+'. Collection delay: '+str(s.assumptions['delay_days'])+' days. Lowest stressed cash: $'+latest['stress']['lowest_cash']+'. Additional funding to maintain the chosen buffer: $'+latest['stress']['funding_needed']+'. Assumptions: '+str(s.assumptions)) if latest else 'No supported scenario saved.'}

UNRESOLVED QUESTIONS
Missing documents: {missing}.
Reconciliation: {'; '.join(a['reconciliation']) or 'No arithmetic differences identified; this is not independent verification.'}
Confirm proposed pricing, amount drawn, maturity, security, and reporting conditions. Explain any exceptions before review.

ANALYST RECOMMENDATION
[Enter your reasoned recommendation and conditions. No automated lending decision.]

REVIEW NOTICE
Approval is a simulated review decision only; it does not authorize or trigger a disbursement."""


@app.get("/api/cases/{id}/memo/template")
def template(id: str, db=Depends(database), u=Depends(user)):
    c = get_case(db, id)
    s = (
        db.query(Scenario)
        .filter_by(case_id=id)
        .order_by(Scenario.created_at.desc())
        .first()
    )
    a = analysis(db, c, s.assumptions["period"] if s else None)
    return {"memo": memo_template(c, a, s)}


class MemoInput(BaseModel):
    memo: str = Field(min_length=20, max_length=30000)
    version: int


@app.put("/api/cases/{id}/memo")
def save_memo(id: str, body: MemoInput, db=Depends(database), u=Depends(user)):
    c = get_case(db, id)
    editable(c, u)
    if c.version != body.version:
        raise HTTPException(409, "Case changed. Reload before saving the memo.")
    c.memo = body.memo
    event(db, id, u["id"], "Draft memo saved")
    db.commit()
    return {"ok": True}


@app.post("/api/cases/{id}/submit")
def submit(id: str, db=Depends(database), u=Depends(user)):
    c = get_case(db, id)
    editable(c, u)
    if len(c.memo) < 20:
        raise HTTPException(422, "Save a draft memo before submitting.")
    s = (
        db.query(Scenario)
        .filter_by(case_id=id)
        .order_by(Scenario.created_at.desc())
        .first()
    )
    if not s:
        raise HTTPException(
            422, "Save a supported cash-flow scenario before submitting."
        )
    a = analysis(db, c, s.assumptions["period"])
    if a["dscr"] is None or a["receivables"] is None:
        raise HTTPException(
            422,
            "Import enough monthly financials, debt, and receivables to support this submission.",
        )
    # Detect edits to source data or profile after the last scenario was saved.
    if forecast(db, c, s.assumptions) != s.result:
        raise HTTPException(
            409,
            "The source data changed after the scenario. Save a new scenario and update the memo before submitting.",
        )
    snap = {
        "analysis": a,
        "scenario": s.result,
        "profile": c.profile,
        "records": {k: records(db, id, k) for k in HEADERS},
        "import_ids": [
            b.id
            for b in db.query(ImportBatch).filter_by(case_id=id, status="committed")
        ],
        "scenario_id": s.id,
    }
    sid = uid()
    db.add(
        Submission(id=sid, case_id=id, author_id=u["id"], memo=c.memo, snapshot=snap)
    )
    c.status = "submitted"
    event(db, id, u["id"], "Memo submitted", {"submission_id": sid})
    db.commit()
    return {"ok": True, "submission_id": sid}


class ReviewInput(BaseModel):
    decision: str
    comment: str = Field(min_length=10, max_length=5000)


@app.post("/api/cases/{id}/review")
def review(id: str, body: ReviewInput, db=Depends(database), u=Depends(user)):
    c = get_case(db, id)
    if u["role"] != "reviewer" or c.owner_id == u["id"]:
        raise HTTPException(403, "An independent reviewer must make this decision.")
    if c.status != "submitted":
        raise HTTPException(409, "Only submitted cases can be reviewed.")
    if body.decision not in ("approved", "declined", "changes_requested"):
        raise HTTPException(422, "Choose approved, declined, or changes_requested.")
    s = (
        db.query(Submission)
        .filter_by(case_id=id)
        .order_by(Submission.created_at.desc())
        .first()
    )
    if s.author_id == u["id"]:
        raise HTTPException(403, "You cannot review your own submission.")
    db.add(
        Review(
            id=uid(),
            submission_id=s.id,
            reviewer_id=u["id"],
            decision=body.decision,
            comment=body.comment,
        )
    )
    c.status = body.decision
    event(
        db,
        id,
        u["id"],
        "Review: " + body.decision,
        {"comment": body.comment, "submission_id": s.id},
    )
    db.commit()
    return {"ok": True}


class ConditionInput(BaseModel):
    id: str = Field(min_length=1, max_length=80)
    category: str
    metric: str
    operator: str
    threshold: Decimal = Field(ge=0, le=10000)
    period: str
    enabled: bool


class MonitoringInput(BaseModel):
    conditions: list[ConditionInput] = Field(max_length=20)
    reporting_deadline: date
    expected_report_period: str


@app.put("/api/cases/{id}/monitoring")
def configure(id: str, body: MonitoringInput, db=Depends(database), u=Depends(user)):
    c = get_case(db, id)
    analyst(u)
    try:
        date.fromisoformat(body.expected_report_period + "-01")
    except ValueError:
        raise HTTPException(422, "Expected reporting period must use YYYY-MM.")
    if len({r.id for r in body.conditions}) != len(body.conditions):
        raise HTTPException(422, "Condition identifiers must be unique.")
    for r in body.conditions:
        if r.category not in ("internal_warning", "contractual_covenant") or (
            r.metric,
            r.period,
            r.operator,
        ) not in [("dso", "monthly", "max"), ("dscr", "trailing_12_months", "min")]:
            raise HTTPException(
                422,
                "Supported definitions: monthly ending AR / monthly sales Ã— days (maximum), or trailing 12-month CADS / scheduled debt service (minimum).",
            )
    c.profile = {**c.profile, **body.model_dump(mode="json")}
    event(
        db,
        id,
        u["id"],
        "Monitoring conditions configured",
        body.model_dump(mode="json"),
    )
    db.commit()
    return {"ok": True}


def evaluate_monitoring(db, c, as_of, u):
    reports = records(db, c.id, "monthly")
    period = max(
        (r["period"] for r in reports if r["period"] <= as_of[:7]), default=None
    )
    expected = c.profile.get("expected_report_period")
    deadline = c.profile.get("reporting_deadline")
    findings = []
    if (
        expected
        and deadline
        and as_of > deadline
        and expected not in {r["period"] for r in reports}
    ):
        findings.append(
            dict(
                rule_id="missing-report",
                period=expected,
                category="reporting",
                title="Monthly financial report overdue",
                detail=f"{expected} report was due {deadline}. Request the financial statements and reconcile them with the receivables schedule.",
            )
        )
    evaluations = []
    for rule in c.profile.get("conditions", []):
        if not rule["enabled"]:
            continue
        a = analysis(db, c, period) if period else None
        value = a[rule["metric"]] if a else None
        exact = a["raw_values"][rule["metric"]] if a else None
        evaluations.append(
            {
                **rule,
                "value": value,
                "evaluated_period": period,
                "status": (
                    "insufficient_data"
                    if value is None
                    else (
                        "breach"
                        if (
                            Decimal(exact) > Decimal(rule["threshold"])
                            if rule["operator"] == "max"
                            else Decimal(exact) < Decimal(rule["threshold"])
                        )
                        else "within_threshold"
                    )
                ),
            }
        )
        if value is None:
            findings.append(
                dict(
                    rule_id=rule["id"],
                    period=period or expected or as_of[:7],
                    category="data_quality",
                    title="Condition cannot be evaluated",
                    detail=f"{rule['metric'].upper()} for {rule['period']}: insufficient data. Import and reconcile the required reporting schedules; this is not a covenant breach.",
                )
            )
        elif evaluations[-1]["status"] == "breach":
            findings.append(
                dict(
                    rule_id=rule["id"],
                    period=period,
                    category=rule["category"],
                    title=(
                        "Collections are slowing"
                        if rule["metric"] == "dso"
                        else "Debt-service coverage below configured minimum"
                    ),
                    detail=f"{rule['metric'].upper()} = {value} (unrounded: {exact}); configured {rule['operator']} {rule['threshold']} for {rule['period']} ending {period}. "
                    + (
                        "Request updated aging and a collection plan for Atlas. Review disputed or overdue invoices."
                        if rule["metric"] == "dso"
                        else "Review the configured definition, obtain updated financials, and document the response."
                    ),
                )
            )
    for f in findings:
        prior = (
            db.query(Alert)
            .filter_by(case_id=c.id, rule_id=f["rule_id"], period=f["period"])
            .first()
        )
        if not prior:
            db.add(Alert(id=uid(), case_id=c.id, **f))
        elif prior.status == "open":
            prior.title = f["title"]
            prior.detail = f["detail"]
            prior.category = f["category"]
    event(db, c.id, u["id"], "Monitoring evaluated", {"as_of": as_of, "period": period})
    db.commit()
    return evaluations


class EvaluateInput(BaseModel):
    as_of: date = date(2026, 2, 16)


@app.post("/api/cases/{id}/monitoring/evaluate")
def evaluate(id: str, body: EvaluateInput, db=Depends(database), u=Depends(user)):
    c = get_case(db, id)
    analyst(u)
    return {"evaluations": evaluate_monitoring(db, c, body.as_of.isoformat(), u)}


@app.get("/api/cases/{id}/alerts")
def alerts(id: str, db=Depends(database), u=Depends(user)):
    get_case(db, id)
    return [
        dict(
            id=a.id,
            rule_id=a.rule_id,
            period=a.period,
            category=a.category,
            title=a.title,
            detail=a.detail,
            status=a.status,
            assignee=a.assignee,
            notes=a.notes,
        )
        for a in db.query(Alert).filter_by(case_id=id).order_by(Alert.period.desc())
    ]


class AlertInput(BaseModel):
    status: str
    assignee: str
    notes: str = Field(max_length=5000)


@app.put("/api/cases/{id}/alerts/{aid}")
def update_alert(
    id: str, aid: str, body: AlertInput, db=Depends(database), u=Depends(user)
):
    a = db.get(Alert, aid)
    if not a or a.case_id != id:
        raise HTTPException(404, "Alert not found.")
    if body.status not in ("open", "resolved") or body.assignee not in USERS:
        raise HTTPException(422, "Choose a valid status and demo assignee.")
    if body.status == "resolved" and len(body.notes.strip()) < 10:
        raise HTTPException(422, "Add a resolution note of at least 10 characters.")
    for k, v in body.model_dump().items():
        setattr(a, k, v)
    event(db, id, u["id"], "Alert updated", {"alert_id": aid, **body.model_dump()})
    db.commit()
    return {"ok": True}
