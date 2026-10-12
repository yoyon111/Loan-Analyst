"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { ArrowRight, CheckCircle2, ClipboardList, FileText, Home, Landmark, LogOut, Plus, Save, Wallet } from "lucide-react";
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
  servicing: { mode: "originated"; annual_rate: string; balance: string;
    scheduled_principal_interest: string; full_payment_due: string;
    monthly_escrow: string; next_due_date: string | null; payments: Payment[] };
};
type CaseSummary = { id: string; applicant_name: string; property_address: string; mode: string; status: string };
type Section = "application" | "documents" | "review" | "servicing";

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
  { key: "monthly_debt", label: "Existing monthly debt payments" },
  { key: "expected_monthly_rent", label: "Expected monthly rent" },
  { key: "property_tax_annual", label: "Annual property tax" },
  { key: "insurance_annual", label: "Annual property insurance" },
  { key: "hoa_monthly", label: "Monthly HOA dues" },
];
const statusLabel: Record<string, string> = {
  draft: "Draft", in_review: "In review", changes_requested: "Changes requested",
  approved: "Approved in simulation", active: "Practice servicing",
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
    setSelected(detail); setDraft(detail); setDirty(false);
    setSection(detail.application.mode === "self_practice" && detail.status === "active" ? "servicing" : "application");
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
      setUser(null); setCases([]); setSelected(null); setDraft(null);
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
    }, message);
  }
  const editable = user?.role === "analyst" && (selected?.status === "draft" || selected?.status === "changes_requested");
  const verifiedCount = draft?.checklist.filter(item => item.status === "verified" || item.status === "not_required").length ?? 0;
  const monthlyDue = selected?.servicing.full_payment_due || "";

  if (booting) return <main className={styles.shell}><p>Opening individual loan practice…</p></main>;
  if (!user) return (
    <main className={styles.signin}>
      <div className={styles.signinCard}>
        <div className={styles.brand}><Landmark size={28} /> InvestOffice <span>Individual lending</span></div>
        <h1>Practice individual loan servicing</h1>
        <p>Enter a rental-property worksheet, set up a practice loan, and simulate its payments. Use fictional or rounded information only.</p>
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
            <strong>{item.applicant_name}</strong><small>{item.mode === "self_practice" ? "Rental-property servicing practice" : item.property_address || "Property not entered"}</small><span>{statusLabel[item.status]}</span>
          </button>)}
          {user.role === "analyst" && <form className={styles.newCase} onSubmit={e => { e.preventDefault(); run(async () => {
            const created = await api<{ id: string }>("/individual-cases/practice", { method: "POST", body: JSON.stringify({ applicant_name: newName, requested_loan: newAmount }) });
            await refreshList(); await loadCase(created.id); setNewName(""); setNewAmount("");
          }, "Individual case created."); }}>
            <h3><Plus size={17} /> Start from borrower worksheet</h3>
            <label>Practice case label<input required minLength={2} value={newName} onChange={e => setNewName(e.target.value)} placeholder="Rental loan practice" /></label>
            <label>Loan amount ($)<input required min="1" type="number" step="0.01" value={newAmount} onChange={e => setNewAmount(e.target.value)} /></label>
            <button disabled={busy}>Create practice loan</button>
          </form>}
          <p className={styles.safety}>Enter the borrower worksheet answers and loan terms, save, then start servicing. Post a payment to inspect the principal, interest, and escrow split. The document checklist is optional practice.</p>
          <p className={styles.safety}>Practice data only. Do not enter real SSNs, upload ID files, or use this for a real credit decision.</p>
        </aside>
        <div className={styles.content}>
          {error && <div className={styles.error} role="alert">{error}</div>}
          {notice && <div className={styles.notice} role="status">{notice}</div>}
          {!selected || !draft ? <div className={styles.empty}><Home size={35} /><h1>No practice case selected</h1><p>Create a practice loan from the borrower worksheet.</p></div> : <>
            <div className={styles.hero}>
              <div><p className={styles.eyebrow}>INDIVIDUAL · RENTAL PROPERTY</p><h1>{draft.application.applicant_name}</h1><p>{draft.application.property_address || "Enter the worksheet and proposed loan terms"}</p></div>
              <span className={styles.status}>{statusLabel[selected.status]}</span>
            </div>
            <nav className={styles.tabs} aria-label="Individual loan workflow">
              {((draft.application.mode === "self_practice" ? [["application", "Worksheet & terms", ClipboardList], ["documents", "Documents", FileText], ["servicing", "Servicing", Wallet]] : [["application", "Application", ClipboardList], ["documents", "Documents", FileText], ["review", "Review", CheckCircle2], ["servicing", "Servicing", Wallet]]) as [Section, string, typeof Wallet][]).map(([key, label, Icon]) =>
                <button key={key} className={section === key ? styles.activeTab : ""} onClick={() => setSection(key)}><Icon size={17} /> {label}</button>)}
            </nav>
            {section === "application" && <div className={styles.panel}>
              <div className={styles.panelHead}><div><h2>Loan application</h2><p>Applicant, property, income, assets, debts, and proposed loan terms.</p></div></div>
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
              {editable && <div className={styles.actions}><button disabled={busy || !dirty} onClick={save}><Save size={17} /> Save application</button>{draft.application.mode === "self_practice" && <button disabled={busy || dirty || !selected.application.first_due_date} onClick={() => transition("practice-activate", {}, "Servicing practice opened.")}>Start servicing practice <ArrowRight size={17} /></button>}{draft.application.mode === "self_practice" && <small>Save the interest rate and first payment due date before starting.</small>}</div>}
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
          </>}
        </div>
      </div>
    </main>
  );
}
