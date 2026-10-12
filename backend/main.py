import hashlib
import os
import secrets
import ipaddress
import calendar
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
    IndividualCase,
    IndividualPayment,
    records,
    event,
)
from .seed import seed, write_examples, HEADERS, record_key
from .intake import validate
from .finance import analysis, forecast, q

USERS = {
    "analyst": {"id": "analyst", "name": "Alex Morgan", "role": "analyst"},
    "reviewer": {"id": "reviewer", "name": "Jordan Lee", "role": "reviewer"},
    "yonathan": {"id": "yonathan", "name": "Yonathan", "role": "analyst"},
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
    allowed_origins = {
        "http://127.0.0.1:3000",
        "http://localhost:3000",
        "http://testserver",
    }
    lan_ip = os.getenv("LAN_IP", "").strip()
    try:
        parsed_ip = ipaddress.ip_address(lan_ip)
        if parsed_ip.version == 4 and parsed_ip.is_private:
            allowed_origins.add(f"http://{parsed_ip}:3000")
    except ValueError:
        pass
    if (
        request.method not in ("GET", "HEAD", "OPTIONS")
        and origin
        and origin not in allowed_origins
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
        raise HTTPException(400, "Choose a demo identity.")
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


# Individual rental-property cases are separate from the commercial analysis model.
# This local practice flow deliberately stores no SSNs, ID images, or credit reports.
INDIVIDUAL_CHECKLIST = (
    "identity", "application", "income", "employment", "assets",
    "funds_source", "reserves", "debts", "credit_permission", "purchase",
    "appraisal", "rent", "property_costs",
)


def individual_case(db, id):
    c = db.get(IndividualCase, id)
    if not c:
        raise HTTPException(404, "Individual case not found.")
    return c


def individual_payments(db, id):
    return db.query(IndividualPayment).filter_by(case_id=id).order_by(IndividualPayment.due_date).all()


def monthly_payment(balance: Decimal, annual_rate: Decimal, months: int):
    rate = annual_rate / Decimal("1200")
    if rate == 0:
        return Decimal(q(balance / months))
    return Decimal(q(balance * rate / (1 - (1 + rate) ** -months)))


def due_after_months(first_due: date, count: int):
    offset = first_due.year * 12 + first_due.month - 1 + count
    year, zero_based_month = divmod(offset, 12)
    month = zero_based_month + 1
    return date(year, month, min(first_due.day, calendar.monthrange(year, month)[1]))


def individual_detail(db, c):
    payments = individual_payments(db, c.id)
    app_data = c.application
    loan = Decimal(app_data["requested_loan"])
    balance = Decimal(payments[-1].balance) if payments else loan
    due = (
        due_after_months(date.fromisoformat(app_data["first_due_date"]), len(payments))
        if app_data["first_due_date"] and balance > 0 else None
    )
    escrow = (Decimal(app_data["property_tax_annual"]) + Decimal(app_data["insurance_annual"])) / 12
    scheduled_pi = monthly_payment(loan, Decimal(app_data["annual_rate"]), app_data["term_months"]) if loan > 0 else Decimal("0")
    next_interest = Decimal(q(balance * Decimal(app_data["annual_rate"]) / 1200))
    next_principal = (
        balance if len(payments) + 1 >= app_data["term_months"]
        else min(balance, max(Decimal("0"), scheduled_pi - next_interest))
    )
    full_payment_due = next_interest + next_principal + Decimal(q(escrow)) if balance > 0 else Decimal("0")
    return dict(
        id=c.id, owner_id=c.owner_id, application=app_data, checklist=c.checklist,
        status=c.status, review_comment=c.review_comment, version=c.version,
        servicing={
            "mode": "originated",
            "annual_rate": app_data["annual_rate"],
            "balance": q(balance), "scheduled_principal_interest": q(scheduled_pi),
            "monthly_escrow": q(escrow), "full_payment_due": q(full_payment_due),
            "next_due_date": due.isoformat() if due else None,
            "payments": [
                dict(id=p.id, due_date=p.due_date, effective_date=p.effective_date,
                     amount=p.amount, interest=p.interest, escrow=p.escrow,
                     principal=p.principal, balance=p.balance)
                for p in payments
            ],
        },
    )


class NewIndividualCase(BaseModel):
    applicant_name: str = Field(min_length=2, max_length=120)
    requested_loan: Decimal = Field(gt=0, le=100000000)


@app.get("/api/individual-cases")
def list_individual_cases(db=Depends(database), u=Depends(user)):
    return [dict(id=c.id, applicant_name=c.application["applicant_name"],
                 property_address=c.application["property_address"],
                 mode=c.application.get("mode", "application"), status=c.status)
            for c in db.query(IndividualCase).order_by(IndividualCase.id).all()]


@app.post("/api/individual-cases")
def create_individual_case(body: NewIndividualCase, db=Depends(database), u=Depends(user)):
    analyst(u)
    application = dict(
        applicant_name=body.applicant_name.strip(), co_applicant_name="",
        property_address="", purchase_price="0.00", requested_loan=q(body.requested_loan),
        down_payment="0.00", down_payment_source="", annual_income="0.00",
        employer="", employment_notes="", liquid_assets="0.00", reserves="0.00",
        monthly_debt="0.00", expected_monthly_rent="0.00",
        property_tax_annual="0.00", insurance_annual="0.00", hoa_monthly="0.00",
        annual_rate="0.00", term_months=360, first_due_date="",
        credit_authorized=False, notes="", rental_property=True,
    )
    c = IndividualCase(
        id=uid(), owner_id=u["id"], application=application,
        checklist=[dict(key=key, status="needed", note="") for key in INDIVIDUAL_CHECKLIST],
    )
    db.add(c)
    db.commit()
    return {"id": c.id}


@app.post("/api/individual-cases/practice")
def create_individual_practice(body: NewIndividualCase, db=Depends(database), u=Depends(user)):
    analyst(u)
    application = dict(
        mode="self_practice", applicant_name=body.applicant_name.strip(),
        co_applicant_name="", property_address="", purchase_price="0.00",
        requested_loan=q(body.requested_loan), down_payment="0.00",
        down_payment_source="", annual_income="0.00", employer="",
        employment_notes="", liquid_assets="0.00", reserves="0.00",
        monthly_debt="0.00", expected_monthly_rent="0.00",
        property_tax_annual="0.00", insurance_annual="0.00", hoa_monthly="0.00",
        annual_rate="0.00", term_months=360, first_due_date="",
        credit_authorized=False, notes="", rental_property=True,
    )
    c = IndividualCase(
        id=uid(), owner_id=u["id"], application=application,
        checklist=[dict(key=key, status="needed", note="") for key in INDIVIDUAL_CHECKLIST],
    )
    db.add(c)
    db.commit()
    return {"id": c.id}


@app.get("/api/individual-cases/{id}")
def get_individual_case(id: str, db=Depends(database), u=Depends(user)):
    return individual_detail(db, individual_case(db, id))


class IndividualChecklistItem(BaseModel):
    key: str
    status: str
    note: str = Field(default="", max_length=500)


class IndividualApplicationInput(BaseModel):
    version: int
    applicant_name: str = Field(min_length=2, max_length=120)
    co_applicant_name: str = Field(default="", max_length=120)
    property_address: str = Field(default="", max_length=250)
    purchase_price: Decimal = Field(ge=0, le=100000000)
    requested_loan: Decimal = Field(gt=0, le=100000000)
    down_payment: Decimal = Field(ge=0, le=100000000)
    down_payment_source: str = Field(default="", max_length=500)
    annual_income: Decimal = Field(ge=0, le=100000000)
    employer: str = Field(default="", max_length=200)
    employment_notes: str = Field(default="", max_length=1000)
    liquid_assets: Decimal = Field(ge=0, le=100000000)
    reserves: Decimal = Field(ge=0, le=100000000)
    monthly_debt: Decimal = Field(ge=0, le=100000000)
    expected_monthly_rent: Decimal = Field(ge=0, le=100000000)
    property_tax_annual: Decimal = Field(ge=0, le=100000000)
    insurance_annual: Decimal = Field(ge=0, le=100000000)
    hoa_monthly: Decimal = Field(ge=0, le=100000000)
    annual_rate: Decimal = Field(ge=0, le=30)
    term_months: int = Field(ge=12, le=480)
    first_due_date: str = ""
    credit_authorized: bool = False
    rental_property: bool = True
    notes: str = Field(default="", max_length=3000)
    checklist: list[IndividualChecklistItem]


@app.put("/api/individual-cases/{id}")
def save_individual_case(id: str, body: IndividualApplicationInput, db=Depends(database), u=Depends(user)):
    analyst(u)
    c = individual_case(db, id)
    if c.status not in ("draft", "changes_requested"):
        raise HTTPException(409, "This case is locked during review or servicing.")
    if body.version != c.version:
        raise HTTPException(409, "Case changed. Reload before saving.")
    if body.first_due_date:
        try:
            date.fromisoformat(body.first_due_date)
        except ValueError:
            raise HTTPException(422, "Enter a valid first payment due date.")
    if body.purchase_price and body.requested_loan > body.purchase_price:
        raise HTTPException(422, "Requested loan cannot exceed the purchase price in this practice flow.")
    if body.purchase_price and body.down_payment > body.purchase_price:
        raise HTTPException(422, "Down payment cannot exceed the purchase price.")
    keys = [item.key for item in body.checklist]
    if len(keys) != len(INDIVIDUAL_CHECKLIST) or set(keys) != set(INDIVIDUAL_CHECKLIST):
        raise HTTPException(422, "The document checklist must contain every item exactly once.")
    if any(item.status not in ("needed", "received", "verified", "not_required") for item in body.checklist):
        raise HTTPException(422, "Choose a valid checklist status.")
    if not body.rental_property:
        raise HTTPException(422, "This practice flow is for rental-property loans.")
    c.application = {**body.model_dump(mode="json", exclude={"version", "checklist"}),
                     **({"mode": "self_practice"} if c.application.get("mode") == "self_practice" else {})}
    c.checklist = [item.model_dump() for item in body.checklist]
    db.commit()
    return individual_detail(db, c)


class IndividualVersion(BaseModel):
    version: int


@app.post("/api/individual-cases/{id}/submit")
def submit_individual_case(id: str, body: IndividualVersion, db=Depends(database), u=Depends(user)):
    analyst(u)
    c = individual_case(db, id)
    if c.status not in ("draft", "changes_requested") or c.version != body.version:
        raise HTTPException(409, "Reload the editable case before submitting.")
    a = c.application
    if not a["property_address"].strip() or Decimal(a["purchase_price"]) <= 0:
        raise HTTPException(422, "Enter the property address and purchase price before review.")
    c.status = "in_review"
    db.commit()
    return individual_detail(db, c)


class IndividualReviewInput(BaseModel):
    version: int
    decision: str
    comment: str = Field(min_length=3, max_length=3000)


@app.post("/api/individual-cases/{id}/review")
def review_individual_case(id: str, body: IndividualReviewInput, db=Depends(database), u=Depends(user)):
    if u["role"] != "reviewer":
        raise HTTPException(403, "Only the reviewer can record a decision.")
    c = individual_case(db, id)
    if c.status != "in_review" or c.version != body.version:
        raise HTTPException(409, "Reload the submitted case before reviewing.")
    if body.decision not in ("approved", "changes_requested"):
        raise HTTPException(422, "Choose approve or request changes.")
    if body.decision == "approved":
        incomplete = [item["key"] for item in c.checklist if item["status"] not in ("verified", "not_required")]
        required_verified = {"identity", "application", "credit_permission"}
        if (incomplete or not c.application["credit_authorized"] or
                any(item["key"] in required_verified and item["status"] != "verified" for item in c.checklist) or
                not c.application["first_due_date"]):
            raise HTTPException(422, "Complete the checklist, verify identity, application and credit permission, and enter the first payment due date before simulated approval.")
    c.status = body.decision
    c.review_comment = body.comment
    db.commit()
    return individual_detail(db, c)


@app.post("/api/individual-cases/{id}/activate")
def activate_individual_case(id: str, body: IndividualVersion, db=Depends(database), u=Depends(user)):
    analyst(u)
    c = individual_case(db, id)
    if c.status != "approved" or c.version != body.version:
        raise HTTPException(409, "Only a current approved case can enter servicing.")
    a = c.application
    if not a["first_due_date"] or Decimal(a["annual_rate"]) < 0:
        raise HTTPException(422, "Set the first payment due date and loan terms before servicing.")
    c.status = "active"
    db.commit()
    return individual_detail(db, c)


@app.post("/api/individual-cases/{id}/practice-activate")
def activate_individual_practice(id: str, body: IndividualVersion, db=Depends(database), u=Depends(user)):
    analyst(u)
    c = individual_case(db, id)
    if c.application.get("mode") != "self_practice" or c.status != "draft" or c.version != body.version:
        raise HTTPException(409, "Reload the practice case before starting servicing.")
    a = c.application
    if not a["first_due_date"] or Decimal(a["requested_loan"]) <= 0:
        raise HTTPException(422, "Enter the loan amount and first payment due date before servicing.")
    c.status = "active"
    db.commit()
    return individual_detail(db, c)


class IndividualPaymentInput(BaseModel):
    version: int
    effective_date: date
    amount: Decimal = Field(gt=0, le=100000000)


@app.post("/api/individual-cases/{id}/payments")
def post_individual_payment(id: str, body: IndividualPaymentInput, db=Depends(database), u=Depends(user)):
    analyst(u)
    c = individual_case(db, id)
    if c.status != "active" or c.version != body.version:
        raise HTTPException(409, "Reload the active loan before posting a payment.")
    detail = individual_detail(db, c)
    s = detail["servicing"]
    balance = Decimal(s["balance"])
    if balance <= 0:
        raise HTTPException(409, "The loan is paid off.")
    if s["payments"] and body.effective_date < date.fromisoformat(s["payments"][-1]["effective_date"]):
        raise HTTPException(422, "Payment date cannot precede the previous posting.")
    a = c.application
    interest = Decimal(q(balance * Decimal(a["annual_rate"]) / 1200))
    escrow = Decimal(s["monthly_escrow"])
    minimum = Decimal(s["full_payment_due"])
    amount = Decimal(q(body.amount))
    if amount < minimum:
        raise HTTPException(422, f"This practice ledger accepts full payments only. Minimum: ${q(minimum)}.")
    principal = amount - interest - escrow
    if principal > balance:
        raise HTTPException(422, "Payment exceeds the remaining balance plus interest and escrow.")
    new_balance = balance - principal
    p = IndividualPayment(
        id=uid(), case_id=id, due_date=s["next_due_date"],
        effective_date=body.effective_date.isoformat(), amount=q(amount),
        interest=q(interest), escrow=q(escrow), principal=q(principal),
        balance=q(new_balance),
    )
    db.add(p)
    db.commit()
    return individual_detail(db, c)
