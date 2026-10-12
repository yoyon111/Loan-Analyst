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


def test_individual_rental_case_review_and_payment(client):
    cl, _ = client
    created = cl.post(
        "/api/individual-cases",
        json={"applicant_name": "Jamie Example", "requested_loan": "200000"},
    )
    assert created.status_code == 200, created.text
    path = "/api/individual-cases/" + created.json()["id"]
    case = cl.get(path).json()
    assert case["application"]["rental_property"] is True
    assert len(case["checklist"]) == 13
    assert "ssn" not in case["application"]

    application = {
        **case["application"],
        "property_address": "123 Fictional Lane",
        "purchase_price": "250000",
        "annual_rate": "6",
        "first_due_date": "2026-12-01",
        "credit_authorized": True,
    }
    saved = cl.put(path, json={**application, "checklist": case["checklist"], "version": case["version"]})
    assert saved.status_code == 200, saved.text
    case = saved.json()
    assert cl.post(path + "/submit", json={"version": case["version"]}).status_code == 200
    assert cl.post(path + "/review", json={"version": case["version"], "decision": "approved", "comment": "Looks complete"}).status_code == 403

    cl.post("/api/auth/logout")
    cl.post("/api/auth/login", json={"identity": "reviewer"})
    case = cl.get(path).json()
    incomplete = cl.post(path + "/review", json={"version": case["version"], "decision": "approved", "comment": "Looks complete"})
    assert incomplete.status_code == 422
    changed = cl.post(path + "/review", json={"version": case["version"], "decision": "changes_requested", "comment": "Verify the documents"})
    assert changed.status_code == 200

    cl.post("/api/auth/logout")
    cl.post("/api/auth/login", json={"identity": "analyst"})
    case = cl.get(path).json()
    checklist = [{**item, "status": "verified"} for item in case["checklist"]]
    saved = cl.put(path, json={**case["application"], "checklist": checklist, "version": case["version"]})
    assert saved.status_code == 200, saved.text
    case = saved.json()
    assert cl.post(path + "/submit", json={"version": case["version"]}).status_code == 200
    cl.post("/api/auth/logout")
    cl.post("/api/auth/login", json={"identity": "reviewer"})
    case = cl.get(path).json()
    approved = cl.post(path + "/review", json={"version": case["version"], "decision": "approved", "comment": "Verified in simulation"})
    assert approved.status_code == 200, approved.text

    cl.post("/api/auth/logout")
    cl.post("/api/auth/login", json={"identity": "analyst"})
    case = cl.get(path).json()
    activated = cl.post(path + "/activate", json={"version": case["version"]})
    assert activated.status_code == 200, activated.text
    case = activated.json()
    assert case["servicing"]["balance"] == "200000.00"
    assert case["servicing"]["next_due_date"] == "2026-12-01"
    too_small = cl.post(path + "/payments", json={"version": case["version"], "effective_date": "2026-12-01", "amount": "1"})
    assert too_small.status_code == 422
    posted = cl.post(path + "/payments", json={"version": case["version"], "effective_date": "2026-12-01", "amount": "1500"})
    assert posted.status_code == 200, posted.text
    payment = posted.json()["servicing"]["payments"][0]
    assert D(payment["interest"]) + D(payment["escrow"]) + D(payment["principal"]) == D("1500")
    assert D(payment["balance"]) < D("200000")
    assert posted.json()["servicing"]["next_due_date"] == "2027-01-01"


def test_yonathan_can_practice_worksheet_to_servicing_alone(client):
    cl, _ = client
    cl.post("/api/auth/logout")
    assert cl.post("/api/auth/login", json={"identity": "yonathan"}).json()["name"] == "Yonathan"
    created = cl.post("/api/individual-cases/practice", json={
        "applicant_name": "Rental loan practice", "requested_loan": "200000",
    })
    assert created.status_code == 200, created.text
    path = "/api/individual-cases/" + created.json()["id"]
    case = cl.get(path).json()
    assert case["application"]["mode"] == "self_practice"
    assert cl.post(path + "/practice-activate", json={"version": case["version"]}).status_code == 422
    saved = cl.put(path, json={
        **case["application"], "version": case["version"], "checklist": case["checklist"],
        "annual_rate": "6", "first_due_date": "2026-11-01",
    })
    assert saved.status_code == 200, saved.text
    case = saved.json()
    assert case["application"]["mode"] == "self_practice"
    active = cl.post(path + "/practice-activate", json={"version": case["version"]})
    assert active.status_code == 200, active.text
    assert active.json()["status"] == "active"
    assert active.json()["checklist"][0]["status"] == "needed"
    due = active.json()["servicing"]["full_payment_due"]
    posted = cl.post(path + "/payments", json={
        "version": active.json()["version"], "effective_date": "2026-11-01", "amount": due,
    })
    assert posted.status_code == 200, posted.text
    assert D(posted.json()["servicing"]["balance"]) < D("200000")


def test_saved_individual_reports_keep_prior_payment_history(client):
    cl, _ = client
    cl.post("/api/auth/logout")
    cl.post("/api/auth/login", json={"identity": "yonathan"})
    created = cl.post("/api/individual-cases/practice", json={
        "applicant_name": "Practice borrower", "requested_loan": "120000",
    }).json()
    path = "/api/individual-cases/" + created["id"]
    case = cl.get(path).json()
    saved = cl.put(path, json={
        **case["application"], "version": case["version"], "checklist": case["checklist"],
        "annual_rate": "6", "first_due_date": "2026-11-01",
        "notes": "Fictional walkthrough",
    }).json()
    active = cl.post(path + "/practice-activate", json={"version": saved["version"]}).json()
    first = cl.post(path + "/reports", json={"title": "Before first payment", "version": active["version"]})
    assert first.status_code == 200, first.text
    first_id = first.json()["id"]
    pdf = cl.get(path + "/reports/" + first_id + "/pdf")
    assert pdf.status_code == 200, pdf.text
    assert pdf.headers["content-type"] == "application/pdf"
    assert pdf.content.startswith(b"%PDF")
    assert len(pdf.content) > 1000
    assert "attachment" in pdf.headers["content-disposition"]
    assert "inline" in cl.get(path + "/reports/" + first_id + "/pdf?view=true").headers["content-disposition"]

    paid = cl.post(path + "/payments", json={
        "version": active["version"], "effective_date": "2026-11-01",
        "amount": active["servicing"]["full_payment_due"],
    }).json()
    second = cl.post(path + "/reports", json={"title": "After first payment", "version": paid["version"]})
    assert second.status_code == 200, second.text
    reports = cl.get(path + "/reports").json()
    assert len(reports) == 2
    assert sorted(row["payments_count"] for row in reports) == [0, 1]
    earlier = cl.get(path + "/reports/" + first_id).json()["snapshot"]
    later = cl.get(path + "/reports/" + second.json()["id"]).json()["snapshot"]
    assert earlier["application"]["notes"] == "Fictional walkthrough"
    assert earlier["servicing"]["payments"] == []
    assert len(later["servicing"]["payments"]) == 1
    assert earlier["servicing"]["balance"] == "120000.00"
    assert D(later["servicing"]["balance"]) < D("120000")
    assert cl.get(path + "/reports/missing").status_code == 404


def test_individual_practice_estimate_excludes_rent_and_tracks_stale_inputs(client):
    cl, _ = client
    cl.post("/api/auth/logout")
    cl.post("/api/auth/login", json={"identity": "yonathan"})
    created = cl.post("/api/individual-cases/practice", json={
        "applicant_name": "Rental scenario", "requested_loan": "200000",
    }).json()
    path = "/api/individual-cases/" + created["id"]
    case = cl.get(path).json()
    missing = cl.post(path + "/estimate", json={
        "version": case["version"], "max_dti_percent": "40",
        "max_ltv_percent": "80", "closing_cost_percent": "3",
    })
    assert missing.status_code == 200, missing.text
    assert missing.json()["result"]["status"] == "needs_information"
    assert "Annual income" in missing.json()["result"]["missing"]

    application = {
        **case["application"], "version": case["version"], "checklist": case["checklist"],
        "annual_income": "120000", "monthly_debt": "500", "current_housing_payment": "1200",
        "liquid_assets": "80000", "reserves": "10000", "purchase_price": "250000",
        "annual_rate": "6", "term_months": 360,
        "property_tax_annual": "4000", "insurance_annual": "2000",
        "expected_monthly_rent": "999999",
    }
    saved = cl.put(path, json=application)
    assert saved.status_code == 200, saved.text
    assert saved.json()["preliminary_estimate"]["stale"] is True
    case = saved.json()
    estimate = cl.post(path + "/estimate", json={
        "version": case["version"], "max_dti_percent": "40",
        "max_ltv_percent": "80", "closing_cost_percent": "3",
    })
    assert estimate.status_code == 200, estimate.text
    result = estimate.json()["result"]
    assert result["status"] == "within_assumptions"
    assert result["rent_counted"] is False
    assert result["illustrative_max_loan"] == "200000.00"
    assert result["requested_ltv_percent"] == "80.00"
    assert result["estimated_closing_costs"] == "7500.00"
    assert result["cash_required_for_requested_loan"] == "67500.00"
    assert estimate.json()["stale"] is False

    report = cl.post(path + "/reports", json={"title": "Estimate included", "version": case["version"]})
    assert report.status_code == 200, report.text
    snapshot = cl.get(path + "/reports/" + report.json()["id"]).json()["snapshot"]
    assert snapshot["preliminary_estimate"]["result"]["status"] == "within_assumptions"
    assert cl.get(path + "/reports/" + report.json()["id"] + "/pdf").content.startswith(b"%PDF")

    updated = cl.put(path, json={**case["application"], "version": case["version"],
                                 "checklist": case["checklist"], "annual_income": "60000"})
    assert updated.status_code == 200, updated.text
    assert updated.json()["preliminary_estimate"]["stale"] is True
    lower = cl.post(path + "/estimate", json={
        "version": updated.json()["version"], "max_dti_percent": "40",
        "max_ltv_percent": "80", "closing_cost_percent": "3",
    }).json()["result"]
    assert lower["status"] == "outside_assumptions"
    assert any("debt" in reason.lower() for reason in lower["reasons"])


def test_origination_options_recommendation_and_report_snapshot(client):
    cl, _ = client
    cl.post("/api/auth/logout")
    cl.post("/api/auth/login", json={"identity": "yonathan"})
    created = cl.post("/api/individual-cases/practice", json={
        "applicant_name": "Fictional applicant", "requested_loan": "200000",
    }).json()
    path = "/api/individual-cases/" + created["id"]
    case = cl.get(path).json()
    saved = cl.put(path, json={
        **case["application"], "version": case["version"], "checklist": case["checklist"],
        "annual_income": "120000", "monthly_debt": "500", "current_housing_payment": "1200",
        "liquid_assets": "90000", "reserves": "10000", "purchase_price": "250000",
        "property_tax_annual": "4000", "insurance_annual": "2000",
        "expected_monthly_rent": "999999",
    }).json()
    terms = {
        "version": saved["version"], "name": "Fixed A", "loan_amount": "200000",
        "annual_rate": "8", "term_months": 360, "points_percent": "1",
        "lender_fees": "1000", "other_closing_costs": "4000",
        "lender_credits": "0", "mortgage_insurance_monthly": "0",
        "max_dti_percent": "40", "max_ltv_percent": "80",
    }
    response = cl.post(path + "/offers", json=terms)
    assert response.status_code == 200, response.text
    offer = response.json()["offers"][0]
    assert offer["result"]["status"] == "within_assumptions"
    assert offer["result"]["cash_to_close"] == "57000.00"
    assert offer["result"]["cash_after_closing"] == "33000.00"
    assert offer["result"]["monthly_total_housing"] == "1967.53"
    assert offer["result"]["five_year_interest_and_lender_cost"] != "0.00"
    assert offer["result"]["rent_counted_for_qualification"] is False
    second = cl.post(path + "/offers", json={**terms, "name": "Fixed B", "annual_rate": "9", "points_percent": "0"})
    assert second.status_code == 200, second.text
    assert len(second.json()["offers"]) == 2
    rec = cl.post(path + "/recommendation", json={
        "version": saved["version"], "offer_id": offer["id"],
        "rationale": "Option A has a lower monthly payment and leaves adequate reserves.",
        "conditions": "Verify credit, income, assets, appraisal, and program rules.",
    })
    assert rec.status_code == 200, rec.text
    assert rec.json()["recommendation"]["stale"] is False
    report = cl.post(path + "/reports", json={"title": "Origination comparison", "version": saved["version"]})
    assert report.status_code == 200, report.text
    snapshot = cl.get(path + "/reports/" + report.json()["id"]).json()["snapshot"]
    assert len(snapshot["offers"]) == 2
    assert snapshot["recommendation"]["offer_id"] == offer["id"]
    assert cl.get(path + "/reports/" + report.json()["id"] + "/pdf").content.startswith(b"%PDF")
    changed = cl.put(path, json={**saved["application"], "version": saved["version"],
                                 "checklist": saved["checklist"], "annual_income": "60000"}).json()
    assert changed["offers"][0]["stale"] is True
    assert changed["recommendation"]["stale"] is True
    assert cl.post(path + "/recommendation", json={
        "version": changed["version"], "offer_id": offer["id"],
        "rationale": "This old option no longer matches the borrower worksheet.",
        "conditions": "Verify all required documents.",
    }).status_code == 409


def test_practice_underwriting_and_closing_require_verification(client):
    cl, _ = client
    cl.post("/api/auth/logout")
    cl.post("/api/auth/login", json={"identity": "yonathan"})
    created = cl.post("/api/individual-cases/practice", json={
        "applicant_name": "Fictional case", "requested_loan": "200000",
    }).json()
    path = "/api/individual-cases/" + created["id"]
    case = cl.get(path).json()
    saved = cl.put(path, json={
        **case["application"], "version": case["version"], "checklist": case["checklist"],
        "property_address": "123 Example Street", "purchase_price": "250000",
        "annual_income": "120000", "liquid_assets": "90000", "reserves": "10000",
        "property_tax_annual": "4000", "insurance_annual": "2000",
        "first_due_date": "2026-12-01", "credit_authorized": True,
    }).json()
    option = cl.post(path + "/offers", json={
        "version": saved["version"], "name": "Fixed", "loan_amount": "200000",
        "annual_rate": "8", "term_months": 360,
    }).json()["offers"][0]
    rec = cl.post(path + "/recommendation", json={
        "version": saved["version"], "offer_id": option["id"],
        "rationale": "This option fits the practice ratios and leaves savings after closing.",
        "conditions": "Verify every document and the property appraisal.",
    })
    assert rec.status_code == 200, rec.text
    decision = cl.post(path + "/practice-decision", json={
        "version": saved["version"], "decision": "conditional",
        "comment": "Proceed only when the document checklist is complete.",
    })
    assert decision.status_code == 200, decision.text
    assert cl.post(path + "/practice-close", json={"version": saved["version"]}).status_code == 422
    verified = [{**item, "status": "verified"} for item in saved["checklist"]]
    updated = cl.put(path, json={
        **saved["application"], "version": saved["version"], "checklist": verified,
    }).json()
    assert updated["recommendation"]["stale"] is False
    closed = cl.post(path + "/practice-close", json={"version": updated["version"]})
    assert closed.status_code == 200, closed.text
    assert closed.json()["status"] == "active"
    assert closed.json()["application"]["annual_rate"] == "8"
    assert closed.json()["recommendation"]["stale"] is False


def test_coach_uses_luna_low_and_omits_identity(client, monkeypatch):
    cl, _ = client
    cl.post("/api/auth/logout")
    cl.post("/api/auth/login", json={"identity": "yonathan"})
    created = cl.post("/api/individual-cases/practice", json={
        "applicant_name": "Private Person", "requested_loan": "200000",
    }).json()
    path = "/api/individual-cases/" + created["id"]
    case = cl.get(path).json()
    saved = cl.put(path, json={
        **case["application"], "version": case["version"], "checklist": case["checklist"],
        "property_address": "Private Address", "annual_income": "120000",
    })
    assert saved.status_code == 200
    seen = {}

    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"output": [{"content": [{"type": "output_text", "text": "Check the saved figures next."}]}]}

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            pass

        async def post(self, url, json, headers):
            seen.update({"url": url, "payload": json, "headers": headers})
            return FakeResponse()

    monkeypatch.setenv("OPENAI_API_KEY", "test-only")
    monkeypatch.setattr(main.httpx, "AsyncClient", lambda timeout: FakeClient())
    result = cl.post(path + "/coach", json={"stage": "application", "question": "What next?"})
    assert result.status_code == 200, result.text
    assert result.json()["answer"] == "Check the saved figures next."
    assert seen["payload"]["model"] == "gpt-6-luna"
    assert seen["payload"]["reasoning"] == {"effort": "low"}
    assert seen["payload"]["store"] is False
    assert "Private Person" not in seen["payload"]["input"]
    assert "Private Address" not in seen["payload"]["input"]
