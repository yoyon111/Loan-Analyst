import copy
import os
import io
import csv
from decimal import Decimal as D
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from backend import main
from backend.db import Base, Case, Record, ImportBatch, records
from backend.seed import generate, csv_text, HEADERS
from backend.intake import validate
from backend.finance import forecast, analysis


@pytest.fixture
def client(monkeypatch):
    test_url = os.getenv("TEST_DATABASE_URL")
    if test_url:
        # Opt-in destructive fixture, exclusively for an explicitly named test database.
        if not test_url.rsplit("/", 1)[-1].endswith("_test"):
            raise RuntimeError(
                "TEST_DATABASE_URL must end in _test; never point tests at working data."
            )
        engine = create_engine(test_url)
        Base.metadata.drop_all(engine)
    else:
        engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(main, "engine", engine)
    monkeypatch.setattr(main, "Session", sessions)
    with TestClient(main.app) as client:
        client.post("/api/auth/login", json={"identity": "analyst"})
        yield client, sessions
    engine.dispose()


def upload(client, kind, raw):
    response = client.post(
        "/api/cases/harbor/imports/preview",
        data={"kind": kind},
        files={"file": ("example.csv", raw, "text/csv")},
    )
    assert response.status_code == 200, response.text
    preview = response.json()
    assert not preview["errors"], preview["errors"]
    response = client.post("/api/cases/harbor/imports/" + preview["id"] + "/commit")
    assert response.status_code == 200, response.text
    return preview["id"]


def prepare(client):
    datasets, _ = generate()
    upload(client, "receivables", csv_text("receivables", datasets["receivables"]))
    scenario = client.post("/api/cases/harbor/scenarios", json={})
    assert scenario.status_code == 200, scenario.text
    case = client.get("/api/cases/harbor").json()
    template = client.get("/api/cases/harbor/memo/template").json()["memo"]
    assert (
        client.put(
            "/api/cases/harbor/memo",
            json={"memo": template, "version": case["version"]},
        ).status_code
        == 200
    )
    return scenario.json()


def test_synthetic_ledger_reconciles():
    data, _ = generate()
    assert sum(D(r["revenue"]) for r in data["monthly"]) == D("1200000")
    assert sum(
        D(r["amount"])
        for r in data["receivables"]
        if r["invoice_date"].startswith("2025")
    ) == D("1200000")
    assert sum(
        D(r["amount"])
        for r in data["receivables"]
        if r["invoice_date"].startswith("2025")
        and r["customer"] == "Atlas Business Group"
    ) == D("480000")
    for r in data["monthly"]:
        assert D(r["cash"]) + D(r["receivables"]) + D(r["inventory"]) + D(
            r["fixed_assets"]
        ) == D(r["payables"]) + D(r["current_debt"]) + D(r["long_term_debt"]) + D(
            r["equity"]
        )
        assert D(r["cash"]) == D("22000") + sum(
            D(t["amount"]) for t in data["bank"] if t["date"][:7] <= r["period"]
        )
    for kind, rows in data.items():
        assert not validate(kind, csv_text(kind, rows))[1]


def test_end_to_end_journey_and_frozen_submission(client):
    cl, dbs = client
    scenario = prepare(cl)
    a = cl.get("/api/cases/harbor/analysis").json()
    assert (a["revenue"], a["ebitda"], a["cads"], a["debt_service"], a["dscr"]) == (
        "1200000.00",
        "132000.00",
        "84000.00",
        "35550.00",
        "2.36",
    )
    assert a["cash"] == "70450.00" and a["concentration"][0]["share"] == "40.00"
    assert (
        scenario["result"]["stress"]["lowest_cash"]
        < scenario["result"]["baseline"]["lowest_cash"]
    )
    assert D(scenario["result"]["stress"]["funding_needed"]) > 0
    assert cl.post("/api/cases/harbor/submit").status_code == 200
    frozen = cl.get("/api/cases/harbor").json()["submissions"][0]
    assert (
        cl.post(
            "/api/cases/harbor/review",
            json={
                "decision": "approved",
                "comment": "Self approval must be forbidden.",
            },
        ).status_code
        == 403
    )
    cl.post("/api/auth/login", json={"identity": "reviewer"})
    assert (
        cl.post(
            "/api/cases/harbor/review",
            json={
                "decision": "approved",
                "comment": "Simulated approval subject to resolving documented questions.",
            },
        ).status_code
        == 200
    )
    assert (
        cl.post(
            "/api/cases/harbor/review",
            json={
                "decision": "declined",
                "comment": "Cannot change a completed decision.",
            },
        ).status_code
        == 409
    )
    cl.post("/api/auth/login", json={"identity": "analyst"})
    for kind in ["receivables", "monthly"]:
        raw = cl.get(f"/api/examples/harbor-{kind}-2026-01.csv").text
        upload(cl, kind, raw)
    result = cl.post(
        "/api/cases/harbor/monitoring/evaluate", json={"as_of": "2026-02-16"}
    )
    assert result.status_code == 200
    assert result.json()["evaluations"][0]["value"] == "74.40"
    alerts = cl.get("/api/cases/harbor/alerts").json()
    alert = next(a for a in alerts if a["rule_id"] == "collections-warning")
    assert alert["category"] == "internal_warning" and alert["status"] == "open"
    assert cl.get("/api/cases/harbor").json()["submissions"][0] == frozen
    assert (
        cl.put(
            "/api/cases/harbor/alerts/" + alert["id"],
            json={
                "status": "resolved",
                "assignee": "reviewer",
                "notes": "Asked for Atlas collection plan; follow up Friday.",
            },
        ).status_code
        == 200
    )
    cl.post("/api/cases/harbor/monitoring/evaluate", json={"as_of": "2026-02-16"})
    alerts = cl.get("/api/cases/harbor/alerts").json()
    assert len([a for a in alerts if a["rule_id"] == "collections-warning"]) == 1
    assert next(a for a in alerts if a["id"] == alert["id"])["status"] == "resolved"


def test_missing_data_is_not_zero(client):
    cl, dbs = client
    a = cl.get("/api/cases/harbor/analysis").json()
    assert a["receivables"] is None and not a["aging"] and a["dso"] is None
    assert a["proposed"]["status"] == "insufficient_data"
    assert cl.post("/api/cases/harbor/scenarios", json={}).status_code == 422
    with dbs() as db:
        db.query(Record).filter_by(kind="monthly", key="2025-06").delete()
        db.commit()
    a = cl.get("/api/cases/harbor/analysis").json()
    assert a["dscr"] is None and a["cads"] is None and a["revenue"] is None
    assert a["missing"] == ["2025-06"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("amount", "NaN"),
        ("amount", "100.001"),
        ("amount", "-1"),
        ("due_date", "2025-02-30"),
        ("paid_amount", "99999999"),
        ("customer", ""),
        ("as_of", "2020-01-01"),
    ],
)
def test_actionable_validation(field, value):
    data, _ = generate()
    row = copy.deepcopy(data["receivables"][0])
    row[field] = value
    rows, errors = validate("receivables", csv_text("receivables", [row]))
    assert errors and errors[0]["row"] == 2


def test_duplicate_import_and_immutable_corrections(client):
    cl, dbs = client
    data, _ = generate()
    raw = csv_text("receivables", data["receivables"])
    bid = upload(cl, "receivables", raw)
    assert (
        cl.post(
            "/api/cases/harbor/imports/preview",
            data={"kind": "receivables"},
            files={"file": ("renamed.csv", raw, "text/csv")},
        ).status_code
        == 409
    )
    changed = copy.deepcopy(data["receivables"])
    changed[-1]["customer"] = "Corrected synthetic customer"
    newer = cl.post(
        "/api/cases/harbor/imports/preview",
        data={
            "kind": "receivables",
            "correction_reason": "Correct synthetic customer name.",
        },
        files={
            "file": ("correction.csv", csv_text("receivables", changed), "text/csv")
        },
    ).json()
    assert not newer["errors"]
    assert (
        cl.post("/api/cases/harbor/imports/" + newer["id"] + "/commit").status_code
        == 200
    )
    assert cl.get(f"/api/cases/harbor/imports/{bid}/source").text == raw
    with dbs() as db:
        assert len(records(db, "harbor", "receivables")) == 224
        assert db.query(Record).filter_by(kind="receivables").count() == 448


def test_review_changes_resubmission_and_role_lock(client):
    cl, _ = client
    prepare(cl)
    cl.post("/api/cases/harbor/submit")
    assert cl.post("/api/cases/harbor/scenarios", json={}).status_code == 409
    cl.post("/api/auth/login", json={"identity": "reviewer"})
    assert cl.post("/api/cases/harbor/scenarios", json={}).status_code == 403
    assert (
        cl.post(
            "/api/cases/harbor/review",
            json={
                "decision": "changes_requested",
                "comment": "Please resolve the missing tax returns.",
            },
        ).status_code
        == 200
    )
    cl.post("/api/auth/login", json={"identity": "analyst"})
    assert cl.post("/api/cases/harbor/submit").status_code == 200
    assert len(cl.get("/api/cases/harbor").json()["submissions"]) == 2


def test_forecast_no_double_counting_draw_interest_and_maturity(client):
    cl, dbs = client
    prepare(cl)
    result = cl.post(
        "/api/cases/harbor/scenarios",
        json={
            "delay_days": 0,
            "draw": "100000",
            "annual_rate": "10",
            "maturity_week": 13,
        },
    ).json()["result"]
    assert result["stress"]["weeks"][0]["financing_inflow"] == "100000.00"
    assert result["stress"]["weeks"][-1]["maturity"] == "100000.00"
    # Financing cannot affect customer collections or recognized sales.
    assert [w["collections"] for w in result["baseline"]["weeks"]] == [
        w["collections"] for w in result["stress"]["weeks"]
    ]
    # 200k existing AR plus 31 days of future sales receipts after the 60-day lag.
    assert abs(
        sum(D(w["collections"]) for w in result["baseline"]["weeks"]) - D("300000")
    ) < D("0.05")
    assert D(result["stress"]["ending_cash"]) < D(result["baseline"]["ending_cash"])
    assert (
        cl.post("/api/cases/harbor/scenarios", json={"draw": "100001"}).status_code
        == 422
    )


def test_stale_scenario_cannot_be_submitted(client):
    cl, _ = client
    prepare(cl)
    c = cl.get("/api/cases/harbor").json()
    p = c["profile"]
    p["reported_collection_days"] = 75
    assert (
        cl.put(
            "/api/cases/harbor/profile", json={**p, "version": c["version"]}
        ).status_code
        == 200
    )
    assert cl.post("/api/cases/harbor/submit").status_code == 409


def test_overdue_reporting_and_no_implied_covenant(client):
    cl, _ = client
    cl.post("/api/cases/harbor/monitoring/evaluate", json={"as_of": "2026-02-16"})
    alerts = cl.get("/api/cases/harbor/alerts").json()
    assert any(a["rule_id"] == "missing-report" for a in alerts)
    assert not any(a["category"] == "contractual_covenant" for a in alerts)


def test_auth_csrf_and_version_conflict(client):
    cl, _ = client
    assert (
        cl.post(
            "/api/auth/login",
            json={"identity": "analyst"},
            headers={"Origin": "https://attacker.example"},
        ).status_code
        == 403
    )
    c = cl.get("/api/cases/harbor").json()
    assert (
        cl.put(
            "/api/cases/harbor/profile",
            json={**c["profile"], "version": c["version"] + 1},
        ).status_code
        == 409
    )
    cl.post("/api/auth/logout")
    assert cl.get("/api/cases/harbor").status_code == 401


def test_new_case_starts_empty(client):
    cl, _ = client
    r = cl.post("/api/cases", json={"name": "Example Wholesaler", "amount": "25000"})
    assert r.status_code == 200
    a = cl.get("/api/cases/" + r.json()["id"] + "/analysis").json()
    assert a["revenue"] is None and a["dscr"] is None and a["cash"] is None


def test_covenant_uses_unrounded_exact_result(client):
    cl, _ = client
    prepare(cl)
    for kind in ["receivables", "monthly"]:
        upload(cl, kind, cl.get(f"/api/examples/harbor-{kind}-2026-01.csv").text)
    c = cl.get("/api/cases/harbor").json()
    conditions = c["profile"]["conditions"]
    conditions[1]["enabled"] = True
    assert (
        cl.put(
            "/api/cases/harbor/monitoring",
            json={
                "conditions": conditions,
                "reporting_deadline": "2026-02-15",
                "expected_report_period": "2026-01",
            },
        ).status_code
        == 200
    )
    evaluations = cl.post(
        "/api/cases/harbor/monitoring/evaluate", json={"as_of": "2026-02-16"}
    ).json()["evaluations"]
    covenant = next(e for e in evaluations if e["metric"] == "dscr")
    assert covenant["value"] == "1.25" and covenant["status"] == "breach"
    assert any(
        a["category"] == "contractual_covenant"
        for a in cl.get("/api/cases/harbor/alerts").json()
    )


def test_mismatched_aging_does_not_generate_false_dso(client):
    cl, dbs = client
    prepare(cl)
    with dbs() as db:
        r = db.query(Record).filter_by(kind="monthly", key="2025-12").first()
        r.data = {**r.data, "receivables": "300000.00"}
        db.commit()
    a = cl.get("/api/cases/harbor/analysis").json()
    assert a["dso"] is None and a["reconciliation"]
    assert cl.post("/api/cases/harbor/scenarios", json={}).status_code == 422
