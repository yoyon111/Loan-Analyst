"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { ArrowRight, CheckCircle2, ClipboardList, Download, FileText, Home, Landmark, LogOut, Plus, Save, Wallet, Sparkles } from "lucide-react";
import { api, money } from "@/lib/api";
import styles from "./individual.module.css";

type User = { id: string; name: string; role: string };
type ChecklistStatus = "needed" | "received" | "verified" | "not_required";
type ChecklistItem = { key: string; status: ChecklistStatus; note: string };
type Application = {
  mode?: "self_practice";
  applicant_name: string; co_applicant_name: string; property_address: string;
  purchase_price: string; requested_loan: string; down_payment: string;
  down_payment_source: string; annual_income: string; employer: string;
  employment_notes: string; liquid_assets: string; reserves: string;
  monthly_debt: string; expected_monthly_rent: string;
  current_housing_payment: string;
  property_tax_annual: string; insurance_annual: string; hoa_monthly: string;
  annual_rate: string; term_months: number; first_due_date: string;
  credit_authorized: boolean; rental_property: boolean; notes: string;
};
type Payment = {
  id: string; due_date: string; effective_date: string; amount: string;
  interest: string; escrow: string; principal: string; balance: string;
};
type IndividualCase = {
  id: string; application: Application; checklist: ChecklistItem[];
  status: string; review_comment: string; version: number;
  preliminary_estimate: PracticeEstimate | null;
  offers: PracticeOffer[];
  recommendation: PracticeRecommendation | null;
  origination_decision: { id: string; decision: string; comment: string; stale: boolean; created_at: string } | null;
  servicing: { mode: "originated"; annual_rate: string; balance: string;
    scheduled_principal_interest: string; full_payment_due: string;
    monthly_escrow: string; next_due_date: string | null; payments: Payment[] };
};
type PracticeOffer = { id: string; created_at: string; stale: boolean; terms: {
  name: string; loan_amount: string; annual_rate: string; term_months: number;
  points_percent: string; lender_fees: string; other_closing_costs: string;
  lender_credits: string; mortgage_insurance_monthly: string;
  max_dti_percent: string; max_ltv_percent: string;
}; result: {
  status: string; reasons: string[]; monthly_principal_interest: string;
  monthly_total_housing: string; dti_percent: string | null; ltv_percent: string | null;
  estimated_closing_costs: string; cash_to_close: string; cash_after_closing: string;
  five_year_interest_and_lender_cost: string; balance_after_five_years: string;
} };
type PracticeRecommendation = { id: string; offer_id: string; rationale: string; conditions: string; stale: boolean; created_at: string };
type PracticeEstimate = {
  id: string; created_at: string; stale: boolean;
  assumptions: { max_dti_percent: string; max_ltv_percent: string; closing_cost_percent: string };
  result: {
    status: "needs_information" | "outside_assumptions" | "within_assumptions";
    missing: string[]; reasons: string[]; warnings: string[];
    gross_monthly_income: string; existing_monthly_debts_including_housing: string;
    property_costs_monthly: string; maximum_housing_payment: string;
    debt_based_max_loan: string; ltv_based_max_loan: string;
    illustrative_max_loan: string | null; requested_principal_interest: string;
    requested_total_housing_payment: string; requested_dti_percent: string | null;
    requested_ltv_percent: string | null; estimated_closing_costs: string;
    cash_required_for_requested_loan: string; cash_available: string;
    reserves_held_back: string; rent_counted: false;
  };
};
type CaseSummary = { id: string; applicant_name: string; property_address: string; mode: string; status: string };
type SavedReport = { id: string; title: string; created_at: string; status: string; payments_count: number };
type Section = "application" | "documents" | "estimate" | "offers" | "recommendation" | "closing" | "review" | "servicing" | "reports";

const checklistLabels: Record<string, { title: string; help: string }> = {
  identity: { title: "Identity and Social Security number", help: "Mark verification status only. Do not enter ID numbers here." },
  application: { title: "Completed rental-property loan application", help: "Confirm the applicant disclosed the intended rental use." },
  income: { title: "Pay stubs, W-2s, and requested tax returns", help: "Track income documents for each applicant." },
  employment: { title: "Employment verification", help: "Record whether current employment was checked." },
  assets: { title: "Bank and investment statements", help: "Track statements and available funds." },
  funds_source: { title: "Down payment and closing funds source", help: "Document the origin of funds." },
  reserves: { title: "Post-closing reserves", help: "Mark not required when the practice scenario has no reserve requirement." },
  debts: { title: "Existing debts", help: "Include mortgages, auto, cards, and student loans." },
  credit_permission: { title: "Permission to check credit", help: "Record authorization; this app never requests a credit report." },
  purchase: { title: "Property address, price, purchase agreement", help: "Track the signed agreement." },
  appraisal: { title: "Property appraisal", help: "Track lender-arranged appraisal status." },
  rent: { title: "Existing leases or market-rent appraisal", help: "Use whichever applies to the scenario." },
  property_costs: { title: "Property tax, insurance, and HOA costs", help: "Track supporting cost information." },
};
const moneyFields: { key: keyof Application; label: string }[] = [
  { key: "purchase_price", label: "Purchase price" },
  { key: "requested_loan", label: "Requested loan" },
  { key: "down_payment", label: "Down payment" },
  { key: "annual_income", label: "Annual income" },
  { key: "liquid_assets", label: "Bank and investment assets" },
  { key: "reserves", label: "Savings after purchase" },
  { key: "monthly_debt", label: "Other monthly debts (excluding housing)" },
  { key: "current_housing_payment", label: "Current monthly housing payment" },
  { key: "expected_monthly_rent", label: "Expected monthly rent" },
  { key: "property_tax_annual", label: "Annual property tax" },
  { key: "insurance_annual", label: "Annual property insurance" },
  { key: "hoa_monthly", label: "Monthly HOA dues" },
];
const statusLabel: Record<string, string> = {
  draft: "Draft", in_review: "In review", changes_requested: "Changes requested",
  approved: "Approved in simulation", active: "After closing practice",
};
const cents = (value: string | number) => new Intl.NumberFormat("en-US", {
  style: "currency", currency: "USD", minimumFractionDigits: 2, maximumFractionDigits: 2,
}).format(Number(value));

export default function IndividualPage() {
  const [user, setUser] = useState<User | null>(null);
  const [booting, setBooting] = useState(true);
  const [cases, setCases] = useState<CaseSummary[]>([]);
  const [selected, setSelected] = useState<IndividualCase | null>(null);
  const [draft, setDraft] = useState<IndividualCase | null>(null);
  const [dirty, setDirty] = useState(false);
  const [section, setSection] = useState<Section>("application");
  const [newName, setNewName] = useState("");
  const [newAmount, setNewAmount] = useState("");
  const [reviewComment, setReviewComment] = useState("");
  const [paymentDate, setPaymentDate] = useState("");
  const [paymentAmount, setPaymentAmount] = useState("");
  const [reports, setReports] = useState<SavedReport[]>([]);
  const [reportTitle, setReportTitle] = useState("Workflow report");
  const [estimateAssumptions, setEstimateAssumptions] = useState({
    max_dti_percent: "40", max_ltv_percent: "80", closing_cost_percent: "3",
  });
  const [offerDraft, setOfferDraft] = useState({ name: "Option A", loan_amount: "", annual_rate: "8", term_months: "360", points_percent: "0", lender_fees: "0", other_closing_costs: "0", lender_credits: "0", mortgage_insurance_monthly: "0" });
  const [selectedOfferId, setSelectedOfferId] = useState("");
  const [rationale, setRationale] = useState("");
  const [conditions, setConditions] = useState("Verify credit, income, assets, property appraisal, and program eligibility before any real decision.");
  const [decisionChoice, setDecisionChoice] = useState("conditional");
  const [decisionComment, setDecisionComment] = useState("Conditional practice decision; complete all verification before simulated closing.");
  const [coachQuestion, setCoachQuestion] = useState("");
  const [coachAnswer, setCoachAnswer] = useState("");
  const [coachBusy, setCoachBusy] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const refreshList = useCallback(async () => {
    const rows = await api<CaseSummary[]>("/individual-cases");
    setCases(rows);
    return rows;
  }, []);
  const loadCase = useCallback(async (id: string) => {
    const detail = await api<IndividualCase>(`/individual-cases/${id}`);
    const savedReports = await api<SavedReport[]>(`/individual-cases/${id}/reports`);
    setSelected(detail); setDraft(detail); setDirty(false);
    setReports(savedReports); setReportTitle(`${detail.application.applicant_name} - workflow report`);
    setEstimateAssumptions(detail.preliminary_estimate?.assumptions || {
      max_dti_percent: "40", max_ltv_percent: "80", closing_cost_percent: "3",
    });
    setOfferDraft(prev => ({ ...prev, loan_amount: detail.application.requested_loan, annual_rate: Number(detail.application.annual_rate) > 0 ? detail.application.annual_rate : "8" }));
    setSelectedOfferId(detail.recommendation?.offer_id || "");
    setRationale(detail.recommendation?.rationale || "");
    setConditions(detail.recommendation?.conditions || "Verify credit, income, assets, property appraisal, and program eligibility before any real decision.");
    setDecisionChoice(detail.origination_decision?.decision || "conditional");
    setDecisionComment(detail.origination_decision?.comment || "Conditional practice decision; complete all verification before simulated closing.");
    setCoachAnswer("");
    setSection("application");
    return detail;
  }, []);
  useEffect(() => {
    let live = true;
    (async () => {
      try {
        const who = await api<User>("/auth/me");
        if (!live) return;
        setUser(who);
        const rows = await refreshList();
        if (live && rows.length) await loadCase(rows[0].id);
      } catch { /* A new visitor chooses a demo identity below. */ }
      finally { if (live) setBooting(false); }
    })();
    return () => { live = false; };
  }, [refreshList, loadCase]);
  useEffect(() => {
    if (selected?.status === "active") {
      setPaymentAmount(selected.servicing.full_payment_due);
      setPaymentDate(selected.servicing.next_due_date || "");
    } else {
      setPaymentAmount(""); setPaymentDate("");
    }
  }, [selected?.id, selected?.status, selected?.servicing.payments.length]);

  async function run(task: () => Promise<void>, message?: string) {
    setBusy(true); setError(""); setNotice("");
    try { await task(); if (message) setNotice(message); }
    catch (e) { setError(e instanceof Error ? e.message : "Please try again."); }
    finally { setBusy(false); }
  }
  async function login(identity: string) {
    await run(async () => {
      const who = await api<User>("/auth/login", { method: "POST", body: JSON.stringify({ identity }) });
      setUser(who);
      const rows = await refreshList();
      if (rows.length) await loadCase(rows[0].id);
    });
  }
  async function logout() {
    await run(async () => {
      await api("/auth/logout", { method: "POST" });
      setUser(null); setCases([]); setSelected(null); setDraft(null); setReports([]);
    });
  }
  function change<K extends keyof Application>(key: K, value: Application[K]) {
    setDraft(prev => prev ? { ...prev, application: { ...prev.application, [key]: value } } : prev);
    setDirty(true);
  }
  function changeChecklist(key: string, patch: Partial<ChecklistItem>) {
    setDraft(prev => prev ? { ...prev, checklist: prev.checklist.map(item => item.key === key ? { ...item, ...patch } : item) } : prev);
    setDirty(true);
  }
  function fillExample() {
    setDraft(prev => prev ? { ...prev, application: {
      ...prev.application, applicant_name: "Fictional rental borrower", property_address: "123 Example Street",
      purchase_price: "250000", requested_loan: "200000", down_payment: "50000",
      down_payment_source: "Fictional savings", annual_income: "120000", employer: "Example employer",
      liquid_assets: "90000", reserves: "10000", monthly_debt: "500",
      current_housing_payment: "1200", expected_monthly_rent: "2200",
      property_tax_annual: "4000", insurance_annual: "2000", hoa_monthly: "0",
      annual_rate: "8", term_months: 360,
    } } : prev);
    setDirty(true);
  }
  async function save() {
    if (!draft) return;
    await run(async () => {
      const updated = await api<IndividualCase>(`/individual-cases/${draft.id}`, {
        method: "PUT", body: JSON.stringify({ ...draft.application, checklist: draft.checklist, version: draft.version }),
      });
      setSelected(updated); setDraft(updated); setDirty(false); await refreshList();
    }, "Application and checklist saved.");
  }
  async function transition(path: string, body: object, message: string) {
    if (!selected) return;
    await run(async () => {
      const updated = await api<IndividualCase>(`/individual-cases/${selected.id}/${path}`, {
        method: "POST", body: JSON.stringify({ version: selected.version, ...body }),
      });
      setSelected(updated); setDraft(updated); setDirty(false); await refreshList();
      if (path === "submit") setSection("review");
      if (path === "activate" || path === "practice-activate") setSection("servicing");
      if (path === "practice-close") setSection("reports");
    }, message);
  }
  async function saveReport() {
    if (!selected || dirty) return;
    await run(async () => {
      await api(`/individual-cases/${selected.id}/reports`, {
        method: "POST", body: JSON.stringify({ title: reportTitle, version: selected.version }),
      });
      setReports(await api<SavedReport[]>(`/individual-cases/${selected.id}/reports`));
    }, "Report snapshot saved. You can reopen or download it later.");
  }
  async function runEstimate() {
    if (!selected || dirty) return;
    await run(async () => {
      const assessment = await api<PracticeEstimate>(`/individual-cases/${selected.id}/estimate`, {
        method: "POST", body: JSON.stringify({ version: selected.version, ...estimateAssumptions }),
      });
      setSelected(prev => prev ? { ...prev, preliminary_estimate: assessment } : prev);
      setDraft(prev => prev ? { ...prev, preliminary_estimate: assessment } : prev);
    }, "Practice estimate saved with this case.");
  }
  async function addOffer() {
    if (!selected || dirty) return;
    await run(async () => {
      const updated = await api<IndividualCase>(`/individual-cases/${selected.id}/offers`, {
        method: "POST", body: JSON.stringify({ version: selected.version, ...offerDraft,
          term_months: Number(offerDraft.term_months),
          max_dti_percent: estimateAssumptions.max_dti_percent,
          max_ltv_percent: estimateAssumptions.max_ltv_percent }),
      });
      setSelected(updated); setDraft(updated);
      setOfferDraft(prev => ({ ...prev, name: `Option ${String.fromCharCode(65 + updated.offers.length)}` }));
    }, "Loan option added to the comparison.");
  }
  async function removeOffer(offerId: string) {
    if (!selected) return;
    await run(async () => {
      const updated = await api<IndividualCase>(`/individual-cases/${selected.id}/offers/${offerId}`, { method: "DELETE" });
      setSelected(updated); setDraft(updated);
    }, "Option removed.");
  }
  async function saveRecommendation() {
    if (!selected || dirty) return;
    await run(async () => {
      const updated = await api<IndividualCase>(`/individual-cases/${selected.id}/recommendation`, {
        method: "POST", body: JSON.stringify({ version: selected.version, offer_id: selectedOfferId, rationale, conditions }),
      });
      setSelected(updated); setDraft(updated);
    }, "Preliminary practice recommendation saved.");
  }
  async function saveDecision() {
    if (!selected || dirty) return;
    await transition("practice-decision", { decision: decisionChoice, comment: decisionComment }, "Practice underwriting decision saved.");
  }
  async function askCoach() {
    if (!selected || dirty || !coachQuestion.trim()) return;
    setCoachBusy(true); setError(""); setCoachAnswer("");
    try {
      const result = await api<{answer: string}>(`/individual-cases/${selected.id}/coach`, {
        method: "POST", body: JSON.stringify({ stage: section === "servicing" || section === "review" ? "recommendation" : section, question: coachQuestion }),
      });
      setCoachAnswer(result.answer);
    } catch (e) { setError(e instanceof Error ? e.message : "Coach unavailable."); }
    finally { setCoachBusy(false); }
  }
  const editable = user?.role === "analyst" && (selected?.status === "draft" || selected?.status === "changes_requested");
  const verifiedCount = draft?.checklist.filter(item => item.status === "verified" || item.status === "not_required").length ?? 0;
  const monthlyDue = selected?.servicing.full_payment_due || "";

  if (booting) return <main className={styles.shell}><p>Opening individual loan practice…</p></main>;
  if (!user) return (
    <main className={styles.signin}>
      <div className={styles.signinCard}>
        <div className={styles.brand}><Landmark size={28} /> InvestOffice <span>Individual lending</span></div>
        <h1>Practice rental loan origination</h1>
        <p>Work from borrower intake through loan comparison and a preliminary recommendation. Use fictional information only.</p>
        <div className={styles.actions}>
          <button disabled={busy} onClick={() => login("yonathan")}>Continue as Yonathan <ArrowRight size={17} /></button>
        </div>
        {error && <p className={styles.error} role="alert">{error}</p>}
        <a href="/individual-rental-loan-intake.pdf" download>Download the borrower worksheet</a><br />
        <Link href="/">Open business lending workspace</Link>
      </div>
    </main>
  );
  return (
    <main className={styles.shell}>
      <header className={styles.topbar}>
        <div className={styles.brand}><Landmark size={26} /> InvestOffice <span>Individual lending</span></div>
        <div className={styles.topActions}><a href="/individual-rental-loan-intake.pdf" download>Download borrower form</a><Link href="/">Business cases</Link><span>{user.name}</span>{user.id !== "yonathan" && <button onClick={() => login("yonathan")}>Switch to Yonathan</button>}<button title="Sign out" onClick={logout}><LogOut size={17} /></button></div>
      </header>
      <div className={styles.layout}>
        <aside className={styles.sidebar}>
          <p className={styles.eyebrow}>PRACTICE CASES</p>
          {cases.map(item => <button key={item.id} className={selected?.id === item.id ? styles.selectedCase : styles.caseButton} onClick={() => { if (dirty && !window.confirm("Discard unsaved changes?")) return; run(async () => { await loadCase(item.id); }); }}>
            <strong>{item.applicant_name}</strong><small>{item.mode === "self_practice" ? "Rental-property origination practice" : item.property_address || "Property not entered"}</small><span>{statusLabel[item.status]}</span>
          </button>)}
          {user.role === "analyst" && <form className={styles.newCase} onSubmit={e => { e.preventDefault(); run(async () => {
            const created = await api<{ id: string }>("/individual-cases/practice", { method: "POST", body: JSON.stringify({ applicant_name: newName, requested_loan: newAmount }) });
            await refreshList(); await loadCase(created.id); setNewName(""); setNewAmount("");
          }, "Individual case created."); }}>
            <h3><Plus size={17} /> New origination case</h3>
            <label>Practice case label<input required minLength={2} value={newName} onChange={e => setNewName(e.target.value)} placeholder="Rental loan practice" /></label>
            <label>Requested loan ($)<input required min="1" type="number" step="0.01" value={newAmount} onChange={e => setNewAmount(e.target.value)} /></label>
            <button disabled={busy}>Create case</button>
          </form>}
          <p className={styles.safety}>1. Enter borrower and property figures. 2. Track documents. 3. Estimate affordability. 4. Compare options. 5. Explain your recommendation. 6. Record a practice decision and review closing conditions.</p>
          <p className={styles.safety}>Practice data only. Do not enter real SSNs, upload ID files, or use this for a real credit decision.</p>
        </aside>
        <div className={styles.content}>
          {error && <div className={styles.error} role="alert">{error}</div>}
          {notice && <div className={styles.notice} role="status">{notice}</div>}
          {!selected || !draft ? <div className={styles.empty}><Home size={35} /><h1>No practice case selected</h1><p>Create an origination case from the borrower worksheet.</p></div> : <>
            <div className={styles.hero}>
              <div><p className={styles.eyebrow}>INDIVIDUAL · RENTAL PROPERTY</p><h1>{draft.application.applicant_name}</h1><p>{draft.application.property_address || "Enter the worksheet and proposed loan terms"}</p></div>
              <span className={styles.status}>{statusLabel[selected.status]}</span>
            </div>
            <nav className={styles.tabs} aria-label="Individual loan workflow">
              {((draft.application.mode === "self_practice" ? [["application", "1. Intake", ClipboardList], ["documents", "2. Documents", FileText], ["estimate", "3. Affordability", CheckCircle2], ["offers", "4. Compare loans", Landmark], ["recommendation", "5. Recommendation", CheckCircle2], ["closing", "6. Review & close", ClipboardList], ["reports", "7. Reports", Download], ["servicing", "After closing", Wallet]] : [["application", "Application", ClipboardList], ["documents", "Documents", FileText], ["estimate", "Estimate", CheckCircle2], ["offers", "Compare loans", Landmark], ["recommendation", "Recommendation", CheckCircle2], ["review", "Review", CheckCircle2], ["servicing", "Servicing", Wallet], ["reports", "Reports", Download]]) as [Section, string, typeof Wallet][]).map(([key, label, Icon]) =>
                <button key={key} className={section === key ? styles.activeTab : ""} onClick={() => setSection(key)}><Icon size={17} /> {label}</button>)}
            </nav>
            {section === "application" && <div className={styles.panel}>
              <div className={styles.panelHead}><div><h2>Loan application</h2><p>Applicant, property, income, assets, debts, and proposed loan terms.</p></div></div>
              {editable && <div className={styles.actions}><button className={styles.secondary} disabled={busy} onClick={fillExample}>Fill fictional example</button><small>Try the whole workflow without personal data.</small></div>}
              <fieldset disabled={!editable || busy}>
                <div className={styles.grid}>
                  <label>Applicant name<input value={draft.application.applicant_name} onChange={e => change("applicant_name", e.target.value)} /></label>
                  <label>Co-applicant name<input value={draft.application.co_applicant_name} onChange={e => change("co_applicant_name", e.target.value)} /></label>
                  <label className={styles.wide}>Rental property address<input value={draft.application.property_address} onChange={e => change("property_address", e.target.value)} /></label>
                  {moneyFields.slice(0, 3).map(field => <label key={field.key}>{field.label} ($)<input type="number" min="0" step="0.01" value={String(draft.application[field.key])} onChange={e => change(field.key, e.target.value)} /></label>)}
                  <label className={styles.wide}>Source of down payment and closing funds<textarea rows={2} value={draft.application.down_payment_source} onChange={e => change("down_payment_source", e.target.value)} /></label>
                  <label>Employer<input value={draft.application.employer} onChange={e => change("employer", e.target.value)} /></label>
                  <label className={styles.wide}>Employment details<textarea rows={2} value={draft.application.employment_notes} onChange={e => change("employment_notes", e.target.value)} /></label>
                  {moneyFields.slice(3).map(field => <label key={field.key}>{field.label} ($)<input type="number" min="0" step="0.01" value={String(draft.application[field.key])} onChange={e => change(field.key, e.target.value)} /></label>)}
                  <label>Annual interest rate (%)<input type="number" min="0" max="30" step="0.001" value={draft.application.annual_rate} onChange={e => change("annual_rate", e.target.value)} /></label>
                  <label>Term (months)<input type="number" min="12" max="480" value={draft.application.term_months} onChange={e => change("term_months", Number(e.target.value))} /></label>
                  <label>First payment due date<input type="date" value={draft.application.first_due_date} onChange={e => change("first_due_date", e.target.value)} /></label>
                  <label className={styles.wide}>Case notes<textarea rows={3} value={draft.application.notes} onChange={e => change("notes", e.target.value)} /></label>
                </div>
                <label className={styles.check}><input type="checkbox" checked={draft.application.credit_authorized} onChange={e => change("credit_authorized", e.target.checked)} /> Applicant permission to check credit has been documented in this practice case</label>
                <p className={styles.hint}>Checking this box does not request a credit report.</p>
              </fieldset>
              {editable && <div className={styles.actions}><button disabled={busy || !dirty} onClick={save}><Save size={17} /> Save application</button><button className={styles.secondary} disabled={dirty} onClick={() => setSection("documents")}>Next: documents <ArrowRight size={17} /></button></div>}
            </div>}
            {section === "documents" && <div className={styles.panel}>
              <div className={styles.panelHead}><div><h2>Document checklist</h2><p>{verifiedCount} of {draft.checklist.length} items verified or marked not required. This tracks status; it does not store document files.</p></div></div>
              <div className={styles.documentList}>{draft.checklist.map((item, index) => <div className={styles.documentRow} key={item.key}>
                <div className={styles.documentNumber}>{index + 1}</div>
                <div><strong>{checklistLabels[item.key]?.title || item.key}</strong><p>{checklistLabels[item.key]?.help}</p><input aria-label={`Notes for ${checklistLabels[item.key]?.title}`} placeholder="Optional review note" value={item.note} disabled={!editable || busy} onChange={e => changeChecklist(item.key, { note: e.target.value })} /></div>
                <select aria-label={`Status for ${checklistLabels[item.key]?.title}`} value={item.status} disabled={!editable || busy} onChange={e => changeChecklist(item.key, { status: e.target.value as ChecklistStatus })}>
                  <option value="needed">Needed</option><option value="received">Received</option><option value="verified">Verified</option><option value="not_required">Not required</option>
                </select>
              </div>)}</div>
              {editable && <div className={styles.actions}><button disabled={busy || !dirty} onClick={save}><Save size={17} /> Save checklist</button></div>}
            </div>}
            {section === "estimate" && <div className={styles.panel}>
              <h2>Step 3: illustrative loan amount</h2>
              <p>Enter income, debts, current housing payment, savings, a target purchase price, property costs, and hypothetical loan terms under Worksheet & terms. This calculation does not count expected rent.</p>
              <div className={styles.estimateInputs}>
                <label>Practice debt-to-income limit (%)<input type="number" min="1" max="100" step="0.1" value={estimateAssumptions.max_dti_percent} onChange={e => setEstimateAssumptions({ ...estimateAssumptions, max_dti_percent: e.target.value })} /></label>
                <label>Practice loan-to-value limit (%)<input type="number" min="1" max="100" step="0.1" value={estimateAssumptions.max_ltv_percent} onChange={e => setEstimateAssumptions({ ...estimateAssumptions, max_ltv_percent: e.target.value })} /></label>
                <label>Estimated closing costs (% of price)<input type="number" min="0" max="20" step="0.1" value={estimateAssumptions.closing_cost_percent} onChange={e => setEstimateAssumptions({ ...estimateAssumptions, closing_cost_percent: e.target.value })} /></label>
              </div>
              <p className={styles.hint}>These editable percentages are exercise assumptions, not any lender&apos;s rules. Savings after purchase is treated as a reserve amount held back from closing.</p>
              {user.role === "analyst" && <div className={styles.actions}><button disabled={busy || dirty || !estimateAssumptions.max_dti_percent || !estimateAssumptions.max_ltv_percent || !estimateAssumptions.closing_cost_percent} onClick={runEstimate}>Calculate practice estimate</button>{dirty && <small>Save worksheet changes first.</small>}</div>}
              <h2 className={styles.estimateHeading}>Step 4: practice preliminary result</h2>
              {!selected.preliminary_estimate ? <p>Run the estimate to see a conditional practice result.</p> : <>
                {selected.preliminary_estimate.stale && <div className={styles.error}>Worksheet figures changed after this estimate. Recalculate before using it in a report.</div>}
                <div className={styles.notice}><strong>{selected.preliminary_estimate.result.status === "within_assumptions" ? "Fits these practice assumptions" : selected.preliminary_estimate.result.status === "outside_assumptions" ? "Outside these practice assumptions" : "More information needed"}</strong> · Saved {new Date(selected.preliminary_estimate.created_at).toLocaleString()}</div>
                <div className={styles.summary}>
                  <div><span>Illustrative maximum at target price</span><strong>{selected.preliminary_estimate.result.illustrative_max_loan ? cents(selected.preliminary_estimate.result.illustrative_max_loan) : "Not available"}</strong></div>
                  <div><span>Debt-based loan ceiling</span><strong>{cents(selected.preliminary_estimate.result.debt_based_max_loan)}</strong></div>
                  <div><span>Proposed monthly housing payment</span><strong>{cents(selected.preliminary_estimate.result.requested_total_housing_payment)}</strong></div>
                  <div><span>Cash needed incl. closing + reserves</span><strong>{cents(selected.preliminary_estimate.result.cash_required_for_requested_loan)}</strong></div>
                  <div><span>Available cash</span><strong>{cents(selected.preliminary_estimate.result.cash_available)}</strong></div>
                  <div><span>Proposed debt-to-income</span><strong>{selected.preliminary_estimate.result.requested_dti_percent ? `${selected.preliminary_estimate.result.requested_dti_percent}%` : "Unknown"}</strong></div>
                  <div><span>Proposed loan-to-value</span><strong>{selected.preliminary_estimate.result.requested_ltv_percent ? `${selected.preliminary_estimate.result.requested_ltv_percent}%` : "Unknown"}</strong></div>
                </div>
                {selected.preliminary_estimate.result.missing.length > 0 && <div className={styles.estimateNotes}><strong>Enter to complete the estimate</strong><ul>{selected.preliminary_estimate.result.missing.map(item => <li key={item}>{item}</li>)}</ul></div>}
                {selected.preliminary_estimate.result.reasons.length > 0 && <div className={styles.estimateNotes}><strong>Why this request falls outside the assumptions</strong><ul>{selected.preliminary_estimate.result.reasons.map(item => <li key={item}>{item}</li>)}</ul></div>}
                <div className={styles.estimateNotes}><strong>What remains unchecked</strong><ul>{selected.preliminary_estimate.result.warnings.map(item => <li key={item}>{item}</li>)}</ul></div>
              </>}
              <p className={styles.hint}>This is an educational scenario result, not a preapproval, loan offer, credit decision, or lender commitment. A real lender must verify finances, credit, property, and program eligibility. <a href="https://www.consumerfinance.gov/owning-a-home/explore/get-a-preapproval-letter/" target="_blank" rel="noreferrer">What real preapproval means</a>.</p>
            </div>}
            {section === "offers" && <div className={styles.panel}>
              <h2>Compare possible loans</h2>
              <p>Add at least two options for the same property. Enter hypothetical figures for practice, or figures from lender Loan Estimates. The app calculates each option separately.</p>
              <div className={styles.grid}>
                <label>Option name<input value={offerDraft.name} onChange={e => setOfferDraft({ ...offerDraft, name: e.target.value })} /></label>
                <label>Loan amount ($)<input type="number" min="1" step="0.01" value={offerDraft.loan_amount} onChange={e => setOfferDraft({ ...offerDraft, loan_amount: e.target.value })} /></label>
                <label>Interest rate (%)<input type="number" min="0" max="30" step="0.001" value={offerDraft.annual_rate} onChange={e => setOfferDraft({ ...offerDraft, annual_rate: e.target.value })} /></label>
                <label>Term (months)<input type="number" min="12" max="480" value={offerDraft.term_months} onChange={e => setOfferDraft({ ...offerDraft, term_months: e.target.value })} /></label>
                <label>Discount points (% of loan)<input type="number" min="0" max="10" step="0.01" value={offerDraft.points_percent} onChange={e => setOfferDraft({ ...offerDraft, points_percent: e.target.value })} /></label>
                <label>Other lender fees ($)<input type="number" min="0" step="0.01" value={offerDraft.lender_fees} onChange={e => setOfferDraft({ ...offerDraft, lender_fees: e.target.value })} /></label>
                <label>Other closing costs ($)<input type="number" min="0" step="0.01" value={offerDraft.other_closing_costs} onChange={e => setOfferDraft({ ...offerDraft, other_closing_costs: e.target.value })} /></label>
                <label>Lender credits ($)<input type="number" min="0" step="0.01" value={offerDraft.lender_credits} onChange={e => setOfferDraft({ ...offerDraft, lender_credits: e.target.value })} /></label>
                <label>Monthly mortgage insurance ($)<input type="number" min="0" step="0.01" value={offerDraft.mortgage_insurance_monthly} onChange={e => setOfferDraft({ ...offerDraft, mortgage_insurance_monthly: e.target.value })} /></label>
              </div>
              <p className={styles.hint}>Fixed-rate, fully amortizing practice options. Taxes, insurance, and HOA come from the worksheet. The DTI and LTV limits come from the Affordability tab and are exercise assumptions.</p>
              {editable && <div className={styles.actions}><button disabled={busy || dirty || !offerDraft.name.trim() || !Number(offerDraft.loan_amount)} onClick={addOffer}><Plus size={17} /> Add option</button>{dirty && <small>Save worksheet changes first.</small>}</div>}
              {selected.offers.length > 0 && <div className={styles.offerGrid}>{selected.offers.map(offer => <article className={styles.offerCard} key={offer.id}>
                <div className={styles.offerTitle}><h3>{offer.terms.name}</h3><span>{offer.stale ? "Recalculate after worksheet change" : offer.result.status === "within_assumptions" ? "Fits practice assumptions" : offer.result.status === "needs_information" ? "Needs information" : "Outside assumptions"}</span></div>
                <p>{cents(offer.terms.loan_amount)} · {offer.terms.annual_rate}% · {offer.terms.term_months} months</p>
                <dl>
                  <div><dt>Total monthly housing</dt><dd>{cents(offer.result.monthly_total_housing)}</dd></div>
                  <div><dt>Cash to close</dt><dd>{cents(offer.result.cash_to_close)}</dd></div>
                  <div><dt>Cash left after closing</dt><dd>{cents(offer.result.cash_after_closing)}</dd></div>
                  <div><dt>DTI / LTV</dt><dd>{offer.result.dti_percent ?? "—"}% / {offer.result.ltv_percent ?? "—"}%</dd></div>
                  <div><dt>Five-year interest + lender costs</dt><dd>{cents(offer.result.five_year_interest_and_lender_cost)}</dd></div>
                </dl>
                {offer.result.reasons.length > 0 && <ul>{offer.result.reasons.map(reason => <li key={reason}>{reason}</li>)}</ul>}
                {editable && <button className={styles.textButton} disabled={busy} onClick={() => removeOffer(offer.id)}>Remove option</button>}
              </article>)}</div>}
              <p className={styles.hint}>Five-year figure is this simulator&apos;s interest plus points and lender fees, net of lender credits. It is not the official Loan Estimate comparison figure or APR. Rent is not counted for qualification.</p>
              <div className={styles.actions}><button className={styles.secondary} onClick={() => setSection("recommendation")}>Next: recommendation <ArrowRight size={17} /></button></div>
            </div>}
            {section === "recommendation" && <div className={styles.panel}>
              <h2>Your preliminary recommendation</h2>
              <p>Choose an option that fits the practice assumptions. Explain why its payment, cash to close, and cost make sense for this case. List what remains to be checked.</p>
              {selected.offers.length < 2 && <div className={styles.notice}>Add at least two options in Compare loans so you can explain the tradeoff. You can still save a recommendation after one option.</div>}
              <div className={styles.grid}>
                <label>Recommended option<select value={selectedOfferId} onChange={e => setSelectedOfferId(e.target.value)}><option value="">Choose an option</option>{selected.offers.filter(o => !o.stale && o.result.status === "within_assumptions").map(o => <option value={o.id} key={o.id}>{o.terms.name} — {o.terms.annual_rate}%</option>)}</select></label>
                <label className={styles.wide}>Why this option?<textarea rows={4} value={rationale} onChange={e => setRationale(e.target.value)} placeholder="Compare its monthly payment, cash to close, remaining reserves, and five-year cost with the other options." /></label>
                <label className={styles.wide}>Conditions and missing checks<textarea rows={4} value={conditions} onChange={e => setConditions(e.target.value)} /></label>
              </div>
              {editable && <div className={styles.actions}><button disabled={busy || dirty || !selectedOfferId || rationale.trim().length < 20 || conditions.trim().length < 10} onClick={saveRecommendation}><Save size={17} /> Save recommendation</button></div>}
              {selected.recommendation && <div className={styles.recommendationSaved}><strong>{selected.recommendation.stale ? "Saved recommendation needs review after worksheet changes" : "Saved preliminary recommendation"}</strong><p>{selected.offers.find(o => o.id === selected.recommendation?.offer_id)?.terms.name || "Option"}</p><p>{selected.recommendation.rationale}</p><p><strong>Conditions:</strong> {selected.recommendation.conditions}</p></div>}
              <p className={styles.hint}>This is your practice judgment, not a lender approval or commitment. A lender would verify credit, income, assets, property, appraisal, and its own program rules.</p>
              <div className={styles.actions}><button className={styles.secondary} onClick={() => setSection(draft.application.mode === "self_practice" ? "closing" : "reports")}>Next: {draft.application.mode === "self_practice" ? "review and close" : "save report"} <ArrowRight size={17} /></button></div>
            </div>}
            {section === "closing" && <div className={styles.panel}>
              <h2>Simulated underwriting and closing</h2>
              <p>Record your practice decision. A conditional result means the chosen option fit your assumptions; it does not mean a lender approved it.</p>
              <div className={styles.summary}>
                <div><span>Current recommendation</span><strong>{selected.recommendation && !selected.recommendation.stale ? "Saved" : "Missing or stale"}</strong></div>
                <div><span>Documents resolved</span><strong>{verifiedCount} / {draft.checklist.length}</strong></div>
                <div><span>Credit permission recorded</span><strong>{draft.application.credit_authorized ? "Yes" : "No"}</strong></div>
                <div><span>First payment due date</span><strong>{draft.application.first_due_date || "Missing"}</strong></div>
              </div>
              <div className={styles.grid}>
                <label>Practice decision<select value={decisionChoice} onChange={e => setDecisionChoice(e.target.value)}><option value="conditional">Conditional</option><option value="needs_information">Needs information</option><option value="declined">Declined under practice assumptions</option></select></label>
                <label className={styles.wide}>Decision notes<textarea rows={3} value={decisionComment} onChange={e => setDecisionComment(e.target.value)} /></label>
              </div>
              {editable && <div className={styles.actions}><button disabled={busy || dirty || !selected.recommendation || selected.recommendation.stale || decisionComment.trim().length < 10} onClick={saveDecision}>Record practice decision</button></div>}
              {selected.origination_decision && <div className={styles.recommendationSaved}><strong>{selected.origination_decision.stale ? "Decision needs review" : `Recorded: ${selected.origination_decision.decision.replace("_", " ")}`}</strong><p>{selected.origination_decision.comment}</p></div>}
              <p className={styles.hint}>To simulate closing, resolve all document items, verify identity, application, and credit permission, enter a property address and first payment due date, and save the worksheet. The selected option supplies the final loan amount, rate, and term. This action locks the practice case.</p>
              {editable && <div className={styles.actions}><button disabled={busy || dirty || !selected.origination_decision || selected.origination_decision.stale || selected.origination_decision.decision !== "conditional" || verifiedCount !== draft.checklist.length || !draft.application.credit_authorized || !draft.application.first_due_date} onClick={() => transition("practice-close", {}, "Simulated closing completed. The after-closing ledger is available.")}>Complete simulated closing</button></div>}
            </div>}
            {section === "review" && <div className={styles.panel}>
              <h2>Case review</h2>
              <p>Analysts submit a saved case. The reviewer can request changes or record a simulated approval after the checklist is complete.</p>
              <div className={styles.summary}>
                <div><span>Requested loan</span><strong>{money(selected.application.requested_loan)}</strong></div>
                <div><span>Purchase price</span><strong>{money(selected.application.purchase_price)}</strong></div>
                <div><span>Expected rent</span><strong>{money(selected.application.expected_monthly_rent)} / month</strong></div>
                <div><span>Checklist complete</span><strong>{selected.checklist.filter(item => item.status === "verified" || item.status === "not_required").length} / 13</strong></div>
              </div>
              {selected.review_comment && <div className={styles.notice}><strong>Latest reviewer comment:</strong> {selected.review_comment}</div>}
              {editable && <div className={styles.actions}><button disabled={busy || dirty} onClick={() => transition("submit", {}, "Case submitted for review.")}>Submit for review <ArrowRight size={17} /></button>{dirty && <small>Save your changes before submitting.</small>}</div>}
              {user.role === "reviewer" && selected.status === "in_review" && <div className={styles.reviewBox}>
                <label>Reviewer comment<textarea required minLength={3} rows={3} value={reviewComment} onChange={e => setReviewComment(e.target.value)} /></label>
                <div className={styles.actions}><button className={styles.secondary} disabled={busy || reviewComment.trim().length < 3} onClick={() => transition("review", { decision: "changes_requested", comment: reviewComment }, "Changes requested.")}>Request changes</button><button disabled={busy || reviewComment.trim().length < 3} onClick={() => transition("review", { decision: "approved", comment: reviewComment }, "Simulated approval recorded.")}>Approve in simulation</button></div>
              </div>}
              {user.role === "analyst" && selected.status === "approved" && <div className={styles.actions}><button disabled={busy} onClick={() => transition("activate", {}, "Practice servicing opened.")}>Open servicing ledger <ArrowRight size={17} /></button></div>}
            </div>}
            {section === "servicing" && <div className={styles.panel}>
              <h2>Payment servicing practice</h2>
              {selected.status !== "active" ? <p>{selected.application.mode === "self_practice" ? "Save the loan terms under Worksheet & terms, then select Start servicing practice." : "The payment ledger opens after a simulated review and activation."}</p> : <>
                <div className={styles.summary}>
                  <div><span>Principal balance</span><strong>{cents(selected.servicing.balance)}</strong></div>
                  <div><span>Annual interest rate</span><strong>{selected.servicing.annual_rate}%</strong></div>
                  <div><span>Scheduled principal + interest</span><strong>{cents(selected.servicing.scheduled_principal_interest)}</strong></div>
                  <div><span>Monthly tax + insurance escrow</span><strong>{cents(selected.servicing.monthly_escrow)}</strong></div>
                  <div><span>Full monthly payment</span><strong>{cents(monthlyDue)}</strong></div>
                  <div><span>Next due date</span><strong>{selected.servicing.next_due_date || "Paid off"}</strong></div>
                </div>
                <p className={styles.hint}>HOA dues are shown in the application but are not included in escrow. This practice ledger accepts full monthly payments and optional extra principal.</p>
                {user.role === "analyst" && Number(selected.servicing.balance) > 0 && <form className={styles.paymentForm} onSubmit={e => { e.preventDefault(); transition("payments", { effective_date: paymentDate, amount: paymentAmount }, "Payment posted to the practice ledger."); }}>
                  <label>Payment date<input type="date" required value={paymentDate} onChange={e => setPaymentDate(e.target.value)} /></label>
                  <label>Amount ($)<input type="number" min="0.01" step="0.01" required placeholder={monthlyDue} value={paymentAmount} onChange={e => setPaymentAmount(e.target.value)} /></label>
                  <button disabled={busy || !paymentDate}>Post payment</button>
                </form>}
                <div className={styles.tableWrap}><table><thead><tr><th>Due</th><th>Posted</th><th>Paid</th><th>Interest</th><th>Escrow</th><th>Principal</th><th>Balance</th></tr></thead><tbody>
                  {selected.servicing.payments.length ? selected.servicing.payments.map(p => <tr key={p.id}><td>{p.due_date}</td><td>{p.effective_date}</td><td>{cents(p.amount)}</td><td>{cents(p.interest)}</td><td>{cents(p.escrow)}</td><td>{cents(p.principal)}</td><td>{cents(p.balance)}</td></tr>) : <tr><td colSpan={7}>No payments posted yet.</td></tr>}
                </tbody></table></div>
              </>}
            </div>}
            {section === "reports" && <div className={styles.panel}>
              <h2>Saved workflow reports</h2>
              <p>Save a snapshot of the intake, document statuses, estimate, loan comparisons, and your recommendation. You can reopen or download it later.</p>
              {user.role === "analyst" && <div className={styles.reportSave}>
                <label>Report title<input maxLength={120} minLength={2} value={reportTitle} onChange={e => setReportTitle(e.target.value)} /></label>
                <button disabled={busy || dirty || reportTitle.trim().length < 2} onClick={saveReport}><Save size={16} /> Save report</button>
                {dirty && <small>Save your worksheet or checklist changes before saving a report.</small>}
              </div>}
              {reports.length ? <div className={styles.reportList}>{reports.map(report => <div className={styles.reportRow} key={report.id}>
                <div><strong>{report.title}</strong><span>{new Date(report.created_at).toLocaleString()} · {statusLabel[report.status] || report.status} · {report.payments_count} payment{report.payments_count === 1 ? "" : "s"}</span></div>
                <div className={styles.reportLinks}><a href={`/api/individual-cases/${selected.id}/reports/${report.id}/pdf?view=true`} target="_blank" rel="noreferrer">Open PDF</a><a href={`/api/individual-cases/${selected.id}/reports/${report.id}/pdf`} download><Download size={15} /> Download</a></div>
              </div>)}</div> : <p className={styles.hint}>No reports saved for this case yet.</p>}
              <p className={styles.hint}>Reports stay in this app's local database. Download a PDF if you need a copy outside this computer.</p>
            </div>}
            {section !== "servicing" && section !== "review" && <div className={styles.coachPanel}>
              <h2><Sparkles size={19} /> Ask the origination coach</h2>
              <p>GPT-6 Luna (low reasoning) explains this step using saved numeric case details. It cannot approve a loan or supply a real rate. Case names and addresses are omitted; do not type personal details in your question.</p>
              <div className={styles.coachAsk}><input aria-label="Question for origination coach" maxLength={800} value={coachQuestion} onChange={e => setCoachQuestion(e.target.value)} onKeyDown={e => { if (e.key === "Enter") askCoach(); }} placeholder="What should I check at this step?" /><button disabled={coachBusy || dirty || !coachQuestion.trim()} onClick={askCoach}>{coachBusy ? "Thinking…" : "Ask coach"}</button></div>
              {dirty && <small>Save worksheet changes before asking so the coach sees current figures.</small>}
              {coachAnswer && <div className={styles.coachAnswer}>{coachAnswer}</div>}
            </div>}
          </>}
        </div>
      </div>
    </main>
  );
}
