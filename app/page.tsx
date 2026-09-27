"use client";
import { useEffect, useState, useCallback } from "react";
import {
  Activity,
  ArrowDownToLine,
  ArrowRight,
  ArrowUpRight,
  BarChart3,
  Bell,
  Building2,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  ClipboardList,
  Clock3,
  FileText,
  FolderOpen,
  HelpCircle,
  Landmark,
  Layers3,
  Loader2,
  LogOut,
  MoreHorizontal,
  Plus,
  RefreshCw,
  Save,
  ShieldCheck,
  SlidersHorizontal,
  UploadCloud,
  UserRound,
  Wallet,
  X,
  AlertTriangle,
  LockKeyhole,
} from "lucide-react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api, money, number } from "@/lib/api";
import type {
  User,
  CaseData,
  Analysis,
  Scenario,
  Assumptions,
  Preview,
  ImportItem,
  AlertItem,
  Profile,
} from "@/lib/types";

type Tab =
  | "overview"
  | "profile"
  | "intake"
  | "analysis"
  | "scenarios"
  | "memo"
  | "monitoring";
const tabs: { id: Tab; label: string; icon: typeof Building2 }[] = [
  { id: "overview", label: "Case overview", icon: FolderOpen },
  { id: "profile", label: "Borrower profile", icon: Building2 },
  { id: "intake", label: "Financial intake", icon: UploadCloud },
  { id: "analysis", label: "Repayment analysis", icon: BarChart3 },
  { id: "scenarios", label: "Cash flow scenarios", icon: SlidersHorizontal },
  { id: "memo", label: "Credit memo & review", icon: FileText },
  { id: "monitoring", label: "Ongoing monitoring", icon: Activity },
];
const kindLabels: Record<string, string> = {
  receivables: "Receivables",
  monthly: "Monthly financials",
  bank: "Bank transactions",
  payables: "Payables",
  debt: "Debt schedule",
};
const initialAssumptions: Assumptions = {
  name: "30-day collection delay",
  period: "2025-12",
  delay_days: 30,
  sales_change: "0",
  cost_change: "0",
  cash_buffer: "15000",
  draw: "0",
  annual_rate: "9",
  maturity_week: null,
};

function Badge({
  children,
  tone = "neutral",
}: {
  children: React.ReactNode;
  tone?: string;
}) {
  return <span className={"badge " + tone}>{children}</span>;
}
function Empty({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="empty">
      <Layers3 size={28} />
      <h3>{title}</h3>
      <p>{children}</p>
    </div>
  );
}
function Metric({
  label,
  value,
  detail,
  icon: Icon,
  accent = false,
}: {
  label: string;
  value: string;
  detail: string;
  icon: typeof Wallet;
  accent?: boolean;
}) {
  return (
    <div className={"metric " + (accent ? "accent" : "")}>
      <div className="metric-top">
        {label}
        <Icon size={16} />
      </div>
      <strong className={value === "Insufficient data" ? "insufficient" : ""}>
        {value}
      </strong>
      <span>{detail}</span>
    </div>
  );
}

export default function Home() {
  const [user, setUser] = useState<User | null>(null),
    [boot, setBoot] = useState(true),
    [tab, setTab] = useState<Tab>("overview");
  const [caseId, setCaseId] = useState("harbor"),
    [caseList, setCaseList] = useState<
      { id: string; profile: Profile; status: string }[]
    >([]);
  const [c, setC] = useState<CaseData | null>(null),
    [a, setA] = useState<Analysis | null>(null),
    [scenarios, setScenarios] = useState<Scenario[]>([]),
    [imports, setImports] = useState<ImportItem[]>([]),
    [alerts, setAlerts] = useState<AlertItem[]>([]);
  const [busy, setBusy] = useState(""),
    [error, setError] = useState(""),
    [success, setSuccess] = useState(""),
    [help, setHelp] = useState(false),
    [newCase, setNewCase] = useState(false);
  const [profile, setProfile] = useState<Profile | null>(null),
    [memo, setMemo] = useState(""),
    [reviewComment, setReviewComment] = useState(""),
    [decision, setDecision] = useState("changes_requested");
  const [kind, setKind] = useState("receivables"),
    [file, setFile] = useState<File | null>(null),
    [preview, setPreview] = useState<Preview | null>(null),
    [correction, setCorrection] = useState("");
  const [assumptions, setAssumptions] = useState(initialAssumptions),
    [selectedScenario, setSelectedScenario] = useState("");
  const [monitorDate, setMonitorDate] = useState("2026-02-16"),
    [evaluations, setEvaluations] = useState<
      {
        id: string;
        metric: string;
        value: string | null;
        status: string;
        evaluated_period: string;
      }[]
    >([]);
  const load = useCallback(
    async (id = caseId) => {
      const [cc, aa, ss, ii, al, cl] = await Promise.all([
        api<CaseData>(`/cases/${id}`),
        api<Analysis>(`/cases/${id}/analysis`),
        api<Scenario[]>(`/cases/${id}/scenarios`),
        api<ImportItem[]>(`/cases/${id}/imports`),
        api<AlertItem[]>(`/cases/${id}/alerts`),
        api<{ id: string; profile: Profile; status: string }[]>("/cases"),
      ]);
      setC(cc);
      setProfile(cc.profile);
      setMemo(cc.memo);
      setA(aa);
      setScenarios(ss);
      setImports(ii);
      setAlerts(al);
      setCaseList(cl);
    },
    [caseId],
  );
  useEffect(() => {
    api<User>("/auth/me")
      .then(setUser)
      .catch(() => {})
      .finally(() => setBoot(false));
  }, []);
  useEffect(() => {
    if (user) {
      setError("");
      load().catch((e) => setError(e.message));
    }
  }, [user, load]);
  useEffect(() => {
    if (success) {
      const t = setTimeout(() => setSuccess(""), 7000);
      return () => clearTimeout(t);
    }
  }, [success]);
  useEffect(() => {
    window.scrollTo({ top: 0 });
  }, [tab, caseId]);
  useEffect(() => {
    if (preview) document.querySelector('.preview-panel')?.scrollIntoView({ block: 'start' });
  }, [preview]);
  useEffect(() => {
    if (!help && !newCase) return;
    const previous = document.activeElement as HTMLElement | null;
    const dialog = document.querySelector<HTMLElement>('[role="dialog"]');
    const controls = () => Array.from(dialog?.querySelectorAll<HTMLElement>('button:not(:disabled), input, select, textarea, a[href]') || []);
    controls()[0]?.focus();
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') { setHelp(false); setNewCase(false); }
      if (e.key === 'Tab') {
        const items = controls(); const first = items[0]; const last = items[items.length - 1];
        if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last?.focus(); }
        if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first?.focus(); }
      }
    };
    document.addEventListener('keydown', handleKey);
    return () => { document.removeEventListener('keydown', handleKey); previous?.focus(); };
  }, [help, newCase]);
  async function act(label: string, fn: () => Promise<void>, message?: string) {
    setBusy(label);
    setError("");
    setSuccess("");
    try {
      await fn();
      if (message) setSuccess(message);
    } catch (e) {
      setError(
        e instanceof Error ? e.message : "Something went wrong. Please retry.",
      );
    } finally {
      setBusy("");
    }
  }
  async function login(identity: string) {
    await act(
      "login",
      async () => {
        setUser(
          await api<User>("/auth/login", {
            method: "POST",
            body: JSON.stringify({ identity }),
          }),
        );
      },
      `Signed in as ${identity === "analyst" ? "Alex Morgan, analyst" : "Jordan Lee, reviewer"}.`,
    );
  }
  function navigate(next: Tab) {
    setTab(next);
    setError("");
    setPreview(null);
  }
  const writable =
    user?.role === "analyst" &&
    !!c &&
    ["draft", "changes_requested"].includes(c.status);
  const selected =
    scenarios.find((s) => s.id === selectedScenario) || scenarios[0];
  const pending = alerts.filter((x) => x.status === "open").length;
  const path = `/cases/${caseId}`;
  const currentSubmission = c?.submissions[0];
  async function upload(chosen: File) {
    const form = new FormData();
    form.append("kind", kind);
    form.append("file", chosen);
    form.append("correction_reason", correction);
    setPreview(
      await api<Preview>(path + "/imports/preview", {
        method: "POST",
        body: form,
      }),
    );
  }
  async function examplePreview(filename: string, chosenKind: string) {
    await act("preview", async () => {
      const response = await fetch("/api/examples/" + filename);
      if (!response.ok) throw new Error("Could not load the example file.");
      const f = new File([await response.blob()], filename, {
        type: "text/csv",
      });
      setFile(f);
      setKind(chosenKind);
      const form = new FormData();
      form.append("kind", chosenKind);
      form.append("file", f);
      form.append("correction_reason", correction);
      setPreview(
        await api<Preview>(path + "/imports/preview", {
          method: "POST",
          body: form,
        }),
      );
      setTab("intake");
    });
  }
  function forecastChart() {
    if (!selected)
      return (
        <Empty title="A forecast starts with your records">
          Import Harbor’s receivables, then run the delayed-collections
          scenario.
        </Empty>
      );
    const data = selected.result.baseline.weeks.map((w, i) => ({
      week: "W" + w.week,
      baseline: Number(w.cash),
      stress: Number(selected.result.stress.weeks[i].cash),
    }));
    return (
      <div
        className="chart"
        role="img"
        aria-label="13-week baseline and stressed ending cash balances"
      >
        <ResponsiveContainer width="100%" height="100%">
          <LineChart
            data={data}
            margin={{ top: 15, right: 15, left: 0, bottom: 0 }}
          >
            <CartesianGrid vertical={false} stroke="#e9eeeb" />
            <XAxis
              dataKey="week"
              axisLine={false}
              tickLine={false}
              fontSize={11}
              tickMargin={12}
            />
            <YAxis
              axisLine={false}
              tickLine={false}
              fontSize={11}
              tickFormatter={(v) => money(v, true)}
              width={65}
            />
            <Tooltip
              formatter={(value) => money(Number(value))}
              contentStyle={{ borderRadius: 8, borderColor: "#dce5df" }}
            />
            <ReferenceLine
              y={Number(selected.assumptions.cash_buffer)}
              stroke="#b49b62"
              strokeDasharray="4 4"
            />
            <Line
              type="monotone"
              dataKey="baseline"
              name="Baseline"
              stroke="#1c6a55"
              strokeWidth={2.5}
              dot={false}
            />
            <Line
              type="monotone"
              dataKey="stress"
              name="Stressed"
              stroke="#d79d56"
              strokeWidth={2.5}
              dot={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    );
  }
  if (boot)
    return (
      <main className="login">
        <Loader2 className="spin" /> Opening InvestOffice…
      </main>
    );
  if (!user)
    return (
      <main className="login">
        <div className="login-art">
          <div className="brand">
            <span className="brandmark">
              <BarChart3 />
            </span>{" "}
            InvestOffice<span className="brand-dot">.</span>
          </div>
          <div>
            <span className="eyebrow">THE CREDIT WORKSPACE</span>
            <h1>
              Good lending starts
              <br />
              with a clear picture.
            </h1>
            <p>
              Follow the numbers. Understand the business.
              <br />
              Make a thoughtful, human decision.
            </p>
            <div className="login-line" />
            <span className="small">
              A commercial lending portfolio project
            </span>
          </div>
          <span className="small">
            FICTIONAL COMMUNITY BANK · SYNTHETIC DATA
          </span>
        </div>
        <section className="login-form">
          <Badge tone="green">Local demonstration</Badge>
          <h2>Welcome to your workspace</h2>
          <p>
            Choose a demo identity to explore the full credit workflow. Each
            identity has a separate server-enforced role.
          </p>
          <button
            className="identity"
            disabled={!!busy}
            onClick={() => login("analyst")}
          >
            <span className="avatar">AM</span>
            <span>
              <strong>Alex Morgan</strong>
              <small>Credit analyst · Prepare and monitor cases</small>
            </span>
            <ArrowRight size={20} />
          </button>
          <button
            className="identity"
            disabled={!!busy}
            onClick={() => login("reviewer")}
          >
            <span className="avatar reviewer">JL</span>
            <span>
              <strong>Jordan Lee</strong>
              <small>Credit reviewer · Independent review</small>
            </span>
            <ArrowRight size={20} />
          </button>
          {error && (
            <div className="notice danger" role="alert">
              {error}
            </div>
          )}
          <div className="login-foot">
            <ShieldCheck size={18} />
            <p>
              No real customers. No automatic approvals.
              <br />
              No paid services or AI credentials required.
            </p>
          </div>
        </section>
      </main>
    );
  return (
    <div className="workspace">
      <aside className="sidebar">
        <a href="/" className="brand">
          <span className="brandmark">
            <BarChart3 size={23} />
          </span>
          InvestOffice<span className="brand-dot">.</span>
        </a>
        <div className="bank-name">
          <Landmark size={15} /> COMMUNITY BANK <span>DEMO</span>
        </div>
        <div className="nav-label">WORKSPACE</div>
        <button className="portfolio" onClick={() => navigate("overview")}>
          <FolderOpen size={18} /> Borrower cases <span>{caseList.length}</span>
        </button>
        <div className="case-picker">
          <span className="company-mini">H</span>
          <select
            aria-label="Select borrower case"
            value={caseId}
            onChange={(e) => {
              setCaseId(e.target.value);
              setC(null);
              setSelectedScenario("");
              setTab("overview");
              setEvaluations([]);
            }}
          >
            {caseList.length ? (
              caseList.map((v) => (
                <option key={v.id} value={v.id}>
                  {v.profile.name}
                </option>
              ))
            ) : (
              <option value="harbor">Harbor Office Supply</option>
            )}
          </select>
          <ChevronDown size={14} />
        </div>
        <nav aria-label="Case workflow">
          {tabs.map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              className={tab === id ? "active" : ""}
              onClick={() => navigate(id)}
            >
              <Icon size={17} />
              {label}
              {id === "monitoring" && pending > 0 && (
                <span className="nav-count">{pending}</span>
              )}
              {id === "intake" && !a?.receivables && (
                <span className="nav-dot" />
              )}
            </button>
          ))}
        </nav>
        <button
          className="new-case"
          onClick={() => setNewCase(true)}
          disabled={user.role !== "analyst"}
        >
          <Plus size={16} /> New borrower case
        </button>
        <div className="sidebar-bottom">
          <div className="demo-card">
            <span className="demo-pulse" /> A safe place to practice
            <p>
              All Harbor records are synthetic.
              <br />
              Every decision stays human.
            </p>
          </div>
          <button className="help-button" onClick={() => setHelp(true)}>
            <HelpCircle size={17} /> Guide to this workspace{" "}
            <ArrowUpRight size={15} />
          </button>
          <div className="user-block">
            <span
              className={
                "avatar " + (user.role === "reviewer" ? "reviewer" : "")
              }
            >
              {user.role === "analyst" ? "AM" : "JL"}
            </span>
            <div>
              <strong>{user.name}</strong>
              <small>
                {user.role === "analyst" ? "Credit analyst" : "Credit reviewer"}
              </small>
            </div>
            <button
              aria-label="Sign out and change demo identity"
              title="Sign out and change identity"
              onClick={() =>
                act("logout", async () => {
                  await api("/auth/logout", { method: "POST" });
                  setUser(null);
                  setC(null);
                })
              }
            >
              <LogOut size={17} />
            </button>
          </div>
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <div className="breadcrumb">
            Borrower cases <ChevronRight size={14} />
            <strong>{c?.profile.name || "Loading case"}</strong>
          </div>
          <div className="top-actions">
            <span className="environment">
              <span /> Demo environment
            </span>
            <button
              className="icon-button"
              aria-label="View monitoring alerts"
              onClick={() => navigate("monitoring")}
            >
              <Bell size={19} />
              {pending > 0 && <i />}
            </button>
            <span className="avatar small-avatar">
              {user.role === "analyst" ? "AM" : "JL"}
            </span>
          </div>
        </header>
        <main className="content">
          {error && (
            <div className="notice danger" role="alert">
              <AlertTriangle size={18} />
              <span>{error}</span>
              <button aria-label="Dismiss error" onClick={() => setError("")}>
                <X size={17} />
              </button>
            </div>
          )}
          {success && (
            <div className="notice success" role="status">
              <CheckCircle2 size={18} />
              <span>{success}</span>
              <button
                aria-label="Dismiss success"
                onClick={() => setSuccess("")}
              >
                <X size={17} />
              </button>
            </div>
          )}
          {busy && (
            <div className="working" role="status">
              <Loader2 size={15} className="spin" /> Working…
            </div>
          )}
          {!c || !a || !profile ? (
            <div className="loading-panel">
              <Loader2 className="spin" />
              <h2>Loading your credit workspace</h2>
              <p>Reading the persisted case and financial records.</p>
              {error && (
                <button
                  className="button"
                  onClick={() => act("reload", () => load())}
                >
                  Retry connection
                </button>
              )}
            </div>
          ) : (
            <>
              <div className="page-heading">
                <div>
                  <div className="eyebrow">
                    COMMERCIAL LENDING <span>/</span>{" "}
                    {caseId === "harbor" ? "CASE HOS–001" : "BORROWER CASE"}
                  </div>
                  <div className="title-row">
                    <h1>
                      {tab === "overview"
                        ? c.profile.name
                        : tabs.find((t) => t.id === tab)?.label}
                    </h1>
                    <Badge
                      tone={
                        c.status === "approved"
                          ? "green"
                          : c.status === "declined"
                            ? "red"
                            : "amber"
                      }
                    >
                      <span className="status-dot" />
                      {c.status.replaceAll("_", " ")}
                    </Badge>
                  </div>
                  <p>
                    {tab === "overview"
                      ? "A clear view of the business. A considered path to a credit decision."
                      : c.profile.name +
                        " · " +
                        c.profile.industry +
                        " · Synthetic demo records"}
                  </p>
                </div>
                <div className="heading-actions">
                  {tab === "overview" ? (
                    <>
                      <button
                        className="button secondary"
                        onClick={() => navigate("memo")}
                      >
                        <FileText size={16} /> Credit memo
                      </button>
                      <button
                        className="button"
                        onClick={() => navigate("intake")}
                      >
                        <UploadCloud size={16} /> Import financials
                      </button>
                    </>
                  ) : (
                    <Badge tone="neutral">
                      <Clock3 size={13} /> {a.period_end} reporting
                    </Badge>
                  )}
                </div>
              </div>
              {tab === "overview" && (
                <>
                  <section className="borrower-strip">
                    <div className="borrower-ident">
                      <div className="company-avatar">
                        <Building2 size={29} />
                      </div>
                      <div>
                        <strong>{c.profile.name}</strong>
                        <span>
                          {c.profile.industry} <i>·</i> {c.profile.location}
                        </span>
                      </div>
                    </div>
                    <div>
                      <small>FACILITY REQUEST</small>
                      <strong>
                        {money(c.profile.requested_amount)}{" "}
                        <span>Revolving line</span>
                      </strong>
                    </div>
                    <div>
                      <small>PRIMARY PURPOSE</small>
                      <strong>Working capital</strong>
                    </div>
                    <Badge tone="green">Synthetic borrower</Badge>
                  </section>
                  <section className="metrics-grid">
                    <Metric
                      label="Annual revenue"
                      value={money(a.revenue, true)}
                      detail={`Trailing 12 months · ${a.period}`}
                      icon={BarChart3}
                    />
                    <Metric
                      label="Existing-debt coverage"
                      value={number(a.dscr, "×")}
                      detail="Cash available ÷ debt service"
                      icon={ShieldCheck}
                    />
                    <Metric
                      label="Cash on hand"
                      value={money(a.cash)}
                      detail={`Reported at ${a.period_end}`}
                      icon={Wallet}
                    />
                    <Metric
                      label="Customer collection cycle"
                      value={
                        a.dso
                          ? number(a.dso, " days")
                          : c.profile.reported_collection_days + " days"
                      }
                      detail={
                        a.dso
                          ? "Ending AR ÷ monthly sales × days"
                          : "Borrower-reported · import to validate"
                      }
                      icon={Clock3}
                      accent
                    />
                  </section>
                  <div className="overview-grid">
                    <section className="panel cash-panel">
                      <div className="panel-heading">
                        <div>
                          <h2>Profit is only part of the picture.</h2>
                          <p>
                            Harbor pays suppliers before its customers pay
                            Harbor.
                          </p>
                        </div>
                        <span className="circle-icon">
                          <Activity size={19} />
                        </span>
                      </div>
                      <div className="timing-diagram">
                        <div className="timing-start">
                          <span className="timeline-dot" />
                          <small>DAY 0</small>
                          <strong>Sale invoiced</strong>
                          <span>Revenue is earned</span>
                        </div>
                        <div className="timing-pay">
                          <span className="timeline-dot amber-dot" />
                          <small>DAY {c.profile.supplier_terms_days}</small>
                          <strong>Suppliers paid</strong>
                          <span>Cash goes out</span>
                        </div>
                        <div className="timing-collect">
                          <span className="timeline-dot" />
                          <small>
                            DAY {c.profile.reported_collection_days}
                          </small>
                          <strong>Customer pays</strong>
                          <span>Cash comes in</span>
                        </div>
                        <div className="gap-line">
                          {c.profile.reported_collection_days -
                            c.profile.supplier_terms_days}
                          -day cash timing gap
                        </div>
                      </div>
                      <div className="insight">
                        <span>
                          <Wallet size={18} />
                        </span>
                        <p>
                          A profitable business can still run short of cash. The
                          requested line would help bridge this timing gap.
                        </p>
                      </div>
                      <button
                        className="text-button"
                        onClick={() => navigate("scenarios")}
                      >
                        Explore the 13-week cash forecast{" "}
                        <ArrowRight size={16} />
                      </button>
                    </section>
                    <section className="panel journey-panel">
                      <div className="panel-heading">
                        <h2>Your case workflow</h2>
                        <Badge>
                          {
                            [
                              !!a.receivables,
                              !!selected,
                              !!c.memo,
                              c.status !== "draft",
                            ].filter(Boolean).length
                          }{" "}
                          / 4
                        </Badge>
                      </div>
                      {[
                        {
                          name: "Validate the source records",
                          detail: a.receivables
                            ? "Receivables imported"
                            : "Upload the sample receivables CSV",
                          done: !!a.receivables,
                          target: "intake",
                        },
                        {
                          name: "Test repayment capacity",
                          detail: selected
                            ? "Scenario version saved"
                            : "Model a delay in customer payments",
                          done: !!selected,
                          target: "scenarios",
                        },
                        {
                          name: "Prepare the credit memo",
                          detail: c.memo
                            ? "Draft saved"
                            : "Document your analysis and open questions",
                          done: !!c.memo,
                          target: "memo",
                        },
                        {
                          name: "Submit for independent review",
                          detail:
                            c.status === "draft"
                              ? "Hand off to the demo reviewer"
                              : c.status.replaceAll("_", " "),
                          done: c.status !== "draft",
                          target: "memo",
                        },
                      ].map((step, i) => (
                        <button
                          key={step.name}
                          className="journey-step"
                          onClick={() => navigate(step.target as Tab)}
                        >
                          <span
                            className={
                              "step-index " + (step.done ? "done" : "")
                            }
                          >
                            {step.done ? <Check size={14} /> : i + 1}
                          </span>
                          <span>
                            <strong>{step.name}</strong>
                            <small>{step.detail}</small>
                          </span>
                          <ChevronRight size={15} />
                        </button>
                      ))}
                    </section>
                  </div>
                  <div className="overview-lower">
                    <section className="panel">
                      <div className="panel-heading">
                        <div>
                          <h2>Cash position</h2>
                          <p>Reported month-end balances · FY 2025 and later</p>
                        </div>
                        <button
                          className="text-button"
                          onClick={() => navigate("analysis")}
                        >
                          View analysis <ArrowUpRight size={15} />
                        </button>
                      </div>
                      {a.history.length ? (
                        <div className="chart overview-chart">
                          <ResponsiveContainer width="100%" height="100%">
                            <AreaChart
                              data={a.history.map((v) => ({
                                ...v,
                                cash: Number(v.cash),
                              }))}
                              margin={{
                                top: 15,
                                right: 10,
                                left: 0,
                                bottom: 0,
                              }}
                            >
                              <defs>
                                <linearGradient
                                  id="cashFill"
                                  x1="0"
                                  y1="0"
                                  x2="0"
                                  y2="1"
                                >
                                  <stop
                                    offset="0%"
                                    stopColor="#408771"
                                    stopOpacity={0.2}
                                  />
                                  <stop
                                    offset="100%"
                                    stopColor="#408771"
                                    stopOpacity={0.01}
                                  />
                                </linearGradient>
                              </defs>
                              <CartesianGrid
                                vertical={false}
                                stroke="#edf0ed"
                              />
                              <XAxis
                                dataKey="period"
                                tickFormatter={(p) =>
                                  new Date(p + "-02").toLocaleDateString(
                                    "en-US",
                                    { month: "short" },
                                  )
                                }
                                axisLine={false}
                                tickLine={false}
                                fontSize={11}
                                minTickGap={18}
                              />
                              <YAxis
                                tickFormatter={(v) => money(v, true)}
                                axisLine={false}
                                tickLine={false}
                                width={60}
                                fontSize={11}
                              />
                              <Tooltip formatter={(v) => money(Number(v))} />
                              <Area
                                type="monotone"
                                dataKey="cash"
                                stroke="#387b64"
                                strokeWidth={2.5}
                                fill="url(#cashFill)"
                              />
                            </AreaChart>
                          </ResponsiveContainer>
                        </div>
                      ) : (
                        <Empty title="No financial reports yet">
                          Import monthly financials to see reported cash
                          balances.
                        </Empty>
                      )}
                    </section>
                    <section className="panel watch-panel">
                      <div className="panel-heading">
                        <h2>On the analyst’s radar</h2>
                        <span className="circle-icon amber-icon">
                          <AlertTriangle size={17} />
                        </span>
                      </div>
                      <div className="watch-item">
                        <span className="tiny-dot amber-dot" />
                        <div>
                          <strong>Customer concentration</strong>
                          <p>
                            {a.concentration.length
                              ? `${a.concentration[0].name} represents ${a.concentration[0].share}% of trailing sales.`
                              : "One customer is reported to represent about 40% of sales. Validate with the invoice records."}
                          </p>
                          <Badge tone="amber">
                            {a.concentration.length
                              ? "Calculated exposure"
                              : "Borrower-reported"}
                          </Badge>
                        </div>
                      </div>
                      <div className="watch-item">
                        <span className="tiny-dot" />
                        <div>
                          <strong>Complete the credit file</strong>
                          <p>
                            {
                              c.profile.documents.filter((d) => !d.received)
                                .length
                            }{" "}
                            requested documents are still outstanding.
                          </p>
                          <button
                            className="text-button"
                            onClick={() => navigate("profile")}
                          >
                            Review checklist <ArrowRight size={14} />
                          </button>
                        </div>
                      </div>
                    </section>
                  </div>
                </>
              )}
              {tab === "profile" && (
                <div className="two-column">
                  <section className="panel form-panel">
                    <div className="panel-heading">
                      <h2>The business behind the numbers</h2>
                      <Badge tone={profile.verified ? "green" : "amber"}>
                        {profile.verified
                          ? "Analyst-verified"
                          : "Borrower-reported"}
                      </Badge>
                    </div>
                    <fieldset disabled={!writable || !!busy}>
                      <div className="form-grid">
                        {(
                          [
                            "name",
                            "industry",
                            "location",
                            "owner",
                            "requested_amount",
                            "reported_collection_days",
                            "supplier_terms_days",
                          ] as const
                        ).map((k) => (
                          <label key={k}>
                            {
                              {
                                name: "Business name",
                                industry: "Industry",
                                location: "Location",
                                owner: "Ownership",
                                requested_amount: "Requested limit ($)",
                                reported_collection_days:
                                  "Reported collection days",
                                supplier_terms_days: "Supplier terms (days)",
                              }[k]
                            }
                            <input
                              type={
                                [
                                  "requested_amount",
                                  "reported_collection_days",
                                  "supplier_terms_days",
                                ].includes(k)
                                  ? "number"
                                  : "text"
                              }
                              value={profile[k]}
                              onChange={(e) =>
                                setProfile({
                                  ...profile,
                                  [k]: k.endsWith("_days")
                                    ? Number(e.target.value)
                                    : e.target.value,
                                })
                              }
                            />
                          </label>
                        ))}
                      </div>
                      <label>
                        Financing purpose
                        <textarea
                          rows={3}
                          value={profile.purpose}
                          onChange={(e) =>
                            setProfile({ ...profile, purpose: e.target.value })
                          }
                        />
                      </label>
                      <label className="check-label">
                        <input
                          type="checkbox"
                          checked={profile.verified}
                          onChange={(e) =>
                            setProfile({
                              ...profile,
                              verified: e.target.checked,
                            })
                          }
                        />{" "}
                        I have independently verified this borrower profile
                      </label>
                      <h3>Proposed financing assumptions</h3>
                      <p className="muted">
                        An unused credit limit creates no principal payment by
                        itself. Enter a constant assumed draw and the principal
                        due over the historical comparison year.
                      </p>
                      <div className="form-grid three">
                        {(
                          ["draw", "annual_rate", "principal_due"] as const
                        ).map((k) => (
                          <label key={k}>
                            {
                              {
                                draw: "Assumed draw ($)",
                                annual_rate: "Annual interest rate (%)",
                                principal_due: "Principal due in year ($)",
                              }[k]
                            }
                            <input
                              type="number"
                              min="0"
                              value={profile.proposed_terms?.[k] || ""}
                              placeholder="Not supplied"
                              onChange={(e) =>
                                setProfile({
                                  ...profile,
                                  proposed_terms: {
                                    draw: "0",
                                    annual_rate: "0",
                                    principal_due: "0",
                                    ...profile.proposed_terms,
                                    [k]: e.target.value,
                                  },
                                })
                              }
                            />
                          </label>
                        ))}
                      </div>
                      <button
                        className="button"
                        onClick={() =>
                          act(
                            "profile",
                            async () => {
                              await api(path + "/profile", {
                                method: "PUT",
                                body: JSON.stringify({
                                  ...profile,
                                  version: c.version,
                                }),
                              });
                              await load();
                            },
                            "Borrower profile and verification status saved.",
                          )
                        }
                      >
                        <Save size={16} /> Save borrower profile
                      </button>
                    </fieldset>
                    {!writable && (
                      <div className="notice">
                        <LockKeyhole size={16} /> This profile is read-only in
                        the current role or review state.
                      </div>
                    )}
                  </section>
                  <div className="stack">
                    <section className="panel">
                      <div className="panel-heading">
                        <h2>Document checklist</h2>
                        <Badge>
                          {profile.documents.filter((d) => d.received).length}/
                          {profile.documents.length}
                        </Badge>
                      </div>
                      {profile.documents.length ? (
                        profile.documents.map((d, i) => (
                          <div className="document-row" key={d.name}>
                            <FileText size={17} />
                            <div>
                              <strong>{d.name}</strong>
                              <div className="document-checks">
                                <label>
                                  <input
                                    type="checkbox"
                                    disabled={!writable}
                                    checked={d.received}
                                    onChange={(e) =>
                                      setProfile({
                                        ...profile,
                                        documents: profile.documents.map(
                                          (item, j) =>
                                            j === i
                                              ? {
                                                  ...item,
                                                  received: e.target.checked,
                                                  verified:
                                                    e.target.checked &&
                                                    item.verified,
                                                }
                                              : item,
                                        ),
                                      })
                                    }
                                  />{" "}
                                  Received
                                </label>
                                <label>
                                  <input
                                    type="checkbox"
                                    disabled={!writable || !d.received}
                                    checked={d.verified}
                                    onChange={(e) =>
                                      setProfile({
                                        ...profile,
                                        documents: profile.documents.map(
                                          (item, j) =>
                                            j === i
                                              ? {
                                                  ...item,
                                                  verified: e.target.checked,
                                                }
                                              : item,
                                        ),
                                      })
                                    }
                                  />{" "}
                                  Verified
                                </label>
                              </div>
                            </div>
                          </div>
                        ))
                      ) : (
                        <p className="muted">
                          New case: add source reports through financial intake.
                        </p>
                      )}
                      <p className="small muted">
                        Save the borrower profile to persist checklist changes.
                        Received does not mean verified.
                      </p>
                    </section>
                    <section className="panel">
                      <h2>Opening balances</h2>
                      <p className="muted">
                        Synthetic starting point ·{" "}
                        {profile.opening.as_of || "Not supplied"}
                      </p>
                      {Object.entries(profile.opening)
                        .filter(([k]) => k !== "as_of")
                        .map(([k, v]) => (
                          <div className="data-row" key={k}>
                            <span>{k.replaceAll("_", " ")}</span>
                            <strong>{money(v)}</strong>
                          </div>
                        ))}
                      <p className="small muted">
                        Opening balances support working-capital changes and
                        bank reconciliation. New cases need a prior-year
                        month-end report.
                      </p>
                    </section>
                  </div>
                </div>
              )}
              {tab === "intake" && (
                <>
                  <div className="section-banner">
                    <span className="circle-icon">
                      <UploadCloud size={20} />
                    </span>
                    <div>
                      <h2>Reliable analysis starts with reliable inputs.</h2>
                      <p>
                        Preview, validate, then commit. Every source file and
                        correction stays in the audit trail.
                      </p>
                    </div>
                    <Badge>CSV · UTF-8 · 2 MB max</Badge>
                  </div>
                  <div className="two-column intake-columns">
                    <section className="panel form-panel">
                      <h2>Import a financial schedule</h2>
                      <fieldset disabled={user.role !== "analyst" || !!busy}>
                        <label>
                          Record type
                          <select
                            value={kind}
                            onChange={(e) => {
                              setKind(e.target.value);
                              setPreview(null);
                              setFile(null);
                            }}
                          >
                            {Object.entries(kindLabels).map(([k, v]) => (
                              <option value={k} key={k}>
                                {v}
                              </option>
                            ))}
                          </select>
                        </label>
                        <div className="upload-zone">
                          <UploadCloud size={32} />
                          <strong>
                            {file ? file.name : "Choose a CSV to validate"}
                          </strong>
                          <span>
                            Your file is previewed before any financial record
                            changes.
                          </span>
                          <input
                            aria-label="Upload financial CSV"
                            type="file"
                            accept=".csv,text/csv"
                            onChange={(e) => {
                              setFile(e.target.files?.[0] || null);
                              setPreview(null);
                            }}
                          />
                        </div>
                        <label>
                          Correction reason{" "}
                          <span className="optional">
                            Only for replacing existing record keys
                          </span>
                          <input
                            value={correction}
                            onChange={(e) => {
                              setCorrection(e.target.value);
                              setPreview(null);
                            }}
                            placeholder="Explain what changed and why"
                          />
                        </label>
                        <div className="button-row">
                          <button
                            className="button"
                            disabled={!file || !!busy}
                            onClick={() => act("preview", () => upload(file!))}
                          >
                            <ShieldCheck size={16} /> Validate & preview
                          </button>
                          <button
                            className="button secondary"
                            onClick={() =>
                              examplePreview(`harbor-${kind}.csv`, kind)
                            }
                          >
                            Use Harbor sample
                          </button>
                        </div>
                      </fieldset>
                      <div className="download-row">
                        <a href={`/api/examples/template-${kind}.csv`}>
                          <ArrowDownToLine size={14} /> Blank template
                        </a>
                        <a href={`/api/examples/harbor-${kind}.csv`}>
                          <ArrowDownToLine size={14} /> Example CSV
                        </a>
                      </div>
                    </section>
                    <section className="panel">
                      <h2>What the importer checks</h2>
                      {[
                        "Exact template columns and required values",
                        "Valid dates, reporting periods, and currency precision",
                        "Duplicate files and existing record identifiers",
                        "Paid amounts, due dates, and balance-sheet arithmetic",
                      ].map((s) => (
                        <div className="check-row" key={s}>
                          <CheckCircle2 size={17} />
                          {s}
                        </div>
                      ))}
                      <div className="insight">
                        <p>
                          <strong>Deposits are not the same as revenue.</strong>
                          <br />
                          Customer receipts, loan proceeds, and internal
                          transfers have separate bank categories. Receivables
                          snapshots contain full invoice history through the
                          report date.
                        </p>
                      </div>
                      <p className="small muted">
                        The first Harbor sample contains 224 synthetic invoices,
                        including opening receivables. PDF extraction is
                        intentionally deferred.
                      </p>
                    </section>
                  </div>
                  {preview && (
                    <section className="panel preview-panel">
                      <div className="panel-heading">
                        <div>
                          <h2>
                            {preview.errors.length
                              ? "Resolve these issues before importing"
                              : "Your file is ready to import"}
                          </h2>
                          <p>
                            {preview.count} parsed records ·{" "}
                            {preview.corrections} corrections ·{" "}
                            {preview.synthetic
                              ? "All rows labeled synthetic"
                              : "Contains records not labeled synthetic"}
                          </p>
                        </div>
                        <Badge tone={preview.errors.length ? "red" : "green"}>
                          {preview.errors.length
                            ? `${preview.errors.length} issues`
                            : "Validation passed"}
                        </Badge>
                      </div>
                      {preview.errors.map((e, i) => (
                        <div className="validation-error" key={i}>
                          <AlertTriangle size={16} />
                          <span>
                            <strong>
                              {e.row ? "Row " + e.row : "File"} · {e.field}
                            </strong>
                            {e.message}
                          </span>
                        </div>
                      ))}
                      {preview.preview.length > 0 && (
                        <div className="table-scroll">
                          <table>
                            <thead>
                              <tr>
                                {preview.columns.map((k) => (
                                  <th key={k}>{k.replaceAll("_", " ")}</th>
                                ))}
                              </tr>
                            </thead>
                            <tbody>
                              {preview.preview.map((r, i) => (
                                <tr key={i}>
                                  {preview.columns.map((k) => (
                                    <td key={k}>{r[k] || "—"}</td>
                                  ))}
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      )}
                      <div className="preview-footer">
                        <span className="small muted">
                          Preview shows the first 8 records. No source records
                          have changed yet.
                        </span>
                        <button
                          className="button"
                          disabled={!!preview.errors.length || !!busy}
                          onClick={() =>
                            act(
                              "commit",
                              async () => {
                                await api(
                                  path + `/imports/${preview.id}/commit`,
                                  { method: "POST" },
                                );
                                setPreview(null);
                                setFile(null);
                                await load();
                              },
                              "Import committed. Financial analysis now uses the persisted records.",
                            )
                          }
                        >
                          <Check size={16} /> Commit {preview.count} records
                        </button>
                      </div>
                    </section>
                  )}
                  <section className="panel">
                    <div className="panel-heading">
                      <h2>Import history</h2>
                      <span className="muted small">
                        Original sources are retained
                      </span>
                    </div>
                    <div className="table-scroll">
                      <table>
                        <thead>
                          <tr>
                            <th>Source file</th>
                            <th>Record type</th>
                            <th>Rows</th>
                            <th>Status</th>
                            <th>Imported / previewed</th>
                            <th>Source</th>
                          </tr>
                        </thead>
                        <tbody>
                          {imports.map((i) => (
                            <tr key={i.id}>
                              <td>
                                <strong>{i.filename}</strong>
                                {i.correction_reason && (
                                  <small>{i.correction_reason}</small>
                                )}
                              </td>
                              <td>{kindLabels[i.kind]}</td>
                              <td>{i.count}</td>
                              <td>
                                <Badge
                                  tone={
                                    i.status === "committed"
                                      ? "green"
                                      : i.status === "invalid"
                                        ? "red"
                                        : "neutral"
                                  }
                                >
                                  {i.status}
                                </Badge>
                              </td>
                              <td>{new Date(i.created_at).toLocaleString()}</td>
                              <td>
                                <a
                                  className="text-button"
                                  href={
                                    path.replace("/cases", "/api/cases") +
                                    `/imports/${i.id}/source`
                                  }
                                  aria-label={"Download original " + i.filename}
                                >
                                  <ArrowDownToLine size={16} />
                                </a>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </section>
                </>
              )}
              {tab === "analysis" && (
                <>
                  <div className="section-banner">
                    <div>
                      <h2>Repayment capacity, with the workings shown.</h2>
                      <p>
                        Trailing 12 months: {a.period_start} to {a.period_end}.
                        Amounts in USD; ratios rounded to two decimals. Tables
                        display whole dollars; source records retain cents.
                      </p>
                    </div>
                    <Badge tone="green">
                      Calculated from persisted records
                    </Badge>
                  </div>
                  {[...a.reasons, ...a.reconciliation].map((r) => (
                    <div className="notice" key={r}>
                      <AlertTriangle size={17} />
                      {r}
                    </div>
                  ))}
                  <div className="metrics-grid">
                    <Metric
                      label="Existing-debt DSCR"
                      value={number(a.dscr, "×")}
                      detail="Historical · excludes proposed financing"
                      icon={ShieldCheck}
                    />
                    <Metric
                      label="Cash available for debt service"
                      value={money(a.cads)}
                      detail="After taxes, capex, distributions, and ΔWC"
                      icon={Wallet}
                    />
                    <Metric
                      label="Current ratio"
                      value={number(a.current_ratio, "×")}
                      detail="Current assets ÷ current liabilities"
                      icon={Layers3}
                    />
                    <Metric
                      label="Receivables outstanding"
                      value={money(a.receivables)}
                      detail={
                        a.ar_as_of
                          ? "Snapshot · " + a.ar_as_of
                          : "A supported snapshot is required"
                      }
                      icon={FileText}
                    />
                  </div>
                  <div className="two-column">
                    <section className="panel">
                      <h2>Follow the coverage calculation</h2>
                      <p className="muted">
                        Demo CADS is a cash-flow proxy, not a universal bank
                        definition.
                      </p>
                      {[
                        { name: "EBITDA", v: a.ebitda },
                        { name: "− Cash taxes", v: a.sources.cash_taxes },
                        {
                          name: "− Maintenance capital expenditure",
                          v: a.sources.maintenance_capex,
                        },
                        {
                          name: "− Owner distributions",
                          v: a.sources.distributions,
                        },
                        {
                          name: "− Increase in operating working capital",
                          v: a.sources.working_capital_change,
                        },
                        {
                          name: "= Cash available for debt service",
                          v: a.cads,
                        },
                        {
                          name: "÷ Scheduled principal + interest + maturity",
                          v: a.debt_service,
                        },
                      ].map((r) => (
                        <div className="data-row" key={r.name}>
                          <span>{r.name}</span>
                          <strong>{money(r.v)}</strong>
                        </div>
                      ))}
                      <div className="formula-result">
                        <span>Existing-debt coverage</span>
                        <strong>{number(a.dscr, "×")}</strong>
                      </div>
                      <details>
                        <summary>Definitions and limits</summary>
                        <p>
                          EBITDA = revenue − cost of goods sold − payroll −
                          other operating expenses. Operating working capital =
                          receivables + inventory − payables. A decrease
                          releases cash. Current assets = cash + receivables +
                          inventory; current liabilities = payables + current
                          debt. Principal reduces cash but is not an
                          income-statement expense.
                        </p>
                        <p>
                          All 12 monthly reports, opening working-capital
                          balances, and a debt schedule covering every month are
                          required. Zero is accepted only when explicitly
                          reported. Coverage does not measure collateral
                          adequacy or guarantee repayment.
                        </p>
                      </details>
                    </section>
                    <div className="stack">
                      <section className="panel">
                        <h2>Including the proposed line</h2>
                        <Badge tone="amber">Illustrative assumptions</Badge>
                        {a.proposed.status === "insufficient_data" ? (
                          <>
                            <p className="muted">{a.proposed.reason}</p>
                            <button
                              className="text-button"
                              onClick={() => navigate("profile")}
                            >
                              Set proposed terms <ArrowRight size={15} />
                            </button>
                          </>
                        ) : (
                          <>
                            <div className="formula-result">
                              <span>Combined coverage</span>
                              <strong>{number(a.proposed.dscr, "×")}</strong>
                            </div>
                            <p className="muted">
                              Adds {money(a.proposed.interest)} interest and{" "}
                              {money(a.proposed.principal)} principal to
                              existing debt service. Assumes the entered draw
                              stays outstanding for the full comparison year.
                            </p>
                          </>
                        )}
                      </section>
                      <section className="panel">
                        <h2>Customer concentration</h2>
                        <p className="muted">
                          Customer invoice sales ÷ reconciled trailing-year
                          sales
                        </p>
                        {a.concentration.length ? (
                          a.concentration.map((r, i) => (
                            <div className="concentration" key={r.name}>
                              <div>
                                <span>
                                  <i
                                    style={{
                                      background: [
                                        "#245c4c",
                                        "#6c9484",
                                        "#aac1b4",
                                        "#d1dcd5",
                                      ][i % 4],
                                    }}
                                  />
                                  {r.name}
                                </span>
                                <strong>{r.share}%</strong>
                              </div>
                              <div className="bar-track">
                                <span
                                  style={{
                                    width: r.share + "%",
                                    background: [
                                      "#245c4c",
                                      "#6c9484",
                                      "#aac1b4",
                                      "#d1dcd5",
                                    ][i % 4],
                                  }}
                                />
                              </div>
                            </div>
                          ))
                        ) : (
                          <Empty title="Invoice history needed">
                            Import the complete receivables sample to reconcile
                            customer sales.
                          </Empty>
                        )}
                      </section>
                    </div>
                  </div>
                  <div className="two-column">
                    <section className="panel">
                      <h2>Receivables aging</h2>
                      <p className="muted">
                        Age measured from the contractual invoice due date ·{" "}
                        {a.ar_as_of || "no snapshot"}
                      </p>
                      {a.aging.length ? (
                        a.aging.map((r) => (
                          <div className="data-row" key={r.name}>
                            <span>{r.name}</span>
                            <strong>{money(r.amount)}</strong>
                          </div>
                        ))
                      ) : (
                        <Empty title="Insufficient data">
                          Upload the reporting-period receivables snapshot.
                        </Empty>
                      )}
                      <p className="small muted">
                        DSO = ending unpaid receivables ÷ current monthly
                        revenue × calendar days in the month. This is a
                        period-end approximation, not the observed time to
                        collect each invoice.
                      </p>
                    </section>
                    <section className="panel">
                      <h2>Cash receipts are classified separately</h2>
                      <p className="muted">
                        Bank transaction totals for the analysis period
                      </p>
                      {a.bank_classification.map((r) => (
                        <div className="data-row" key={r.category}>
                          <span>{r.category.replaceAll("_", " ")}</span>
                          <strong>{money(r.amount)}</strong>
                        </div>
                      ))}
                    </section>
                  </div>
                </>
              )}
              {tab === "scenarios" && (
                <>
                  <div className="two-column scenario-columns">
                    <section className="panel form-panel">
                      <div className="panel-heading">
                        <h2>Stress the timing, not the story.</h2>
                        <Badge>13 weeks</Badge>
                      </div>
                      <p className="muted">
                        Start from a reconciled opening balance. See how a
                        collection delay changes the cash you need.
                      </p>
                      <fieldset disabled={!writable || !!busy}>
                        <label>
                          Scenario name
                          <input
                            value={assumptions.name}
                            onChange={(e) =>
                              setAssumptions({
                                ...assumptions,
                                name: e.target.value,
                              })
                            }
                          />
                        </label>
                        <label>
                          Opening reporting month
                          <select
                            value={assumptions.period}
                            onChange={(e) =>
                              setAssumptions({
                                ...assumptions,
                                period: e.target.value,
                              })
                            }
                          >
                            {a.history.length ? (
                              a.history.map((h) => (
                                <option key={h.period}>{h.period}</option>
                              ))
                            ) : (
                              <option>2025-12</option>
                            )}
                          </select>
                        </label>
                        <div className="range-label">
                          <label htmlFor="delay">
                            Additional collection delay
                          </label>
                          <strong>{assumptions.delay_days} days</strong>
                        </div>
                        <input
                          id="delay"
                          type="range"
                          min="0"
                          max="90"
                          step="5"
                          value={assumptions.delay_days}
                          onChange={(e) =>
                            setAssumptions({
                              ...assumptions,
                              delay_days: Number(e.target.value),
                            })
                          }
                        />
                        <div className="range-ends">
                          <span>No delay</span>
                          <span>90 days later</span>
                        </div>
                        <div className="form-grid">
                          {(
                            [
                              "sales_change",
                              "cost_change",
                              "cash_buffer",
                              "draw",
                              "annual_rate",
                            ] as const
                          ).map((k) => (
                            <label key={k}>
                              {
                                {
                                  sales_change: "Future sales change (%)",
                                  cost_change:
                                    "COGS & operating cost change (%)",
                                  cash_buffer: "Minimum cash buffer ($)",
                                  draw: "Proposed draw in week 1 ($)",
                                  annual_rate: "Proposed annual rate (%)",
                                }[k]
                              }
                              <input
                                type="number"
                                value={assumptions[k]}
                                onChange={(e) =>
                                  setAssumptions({
                                    ...assumptions,
                                    [k]: e.target.value,
                                  })
                                }
                              />
                            </label>
                          ))}
                          <label>
                            Proposed principal maturity
                            <select
                              value={assumptions.maturity_week || ""}
                              onChange={(e) =>
                                setAssumptions({
                                  ...assumptions,
                                  maturity_week: e.target.value
                                    ? Number(e.target.value)
                                    : null,
                                })
                              }
                            >
                              <option value="">
                                Outside the 13-week horizon
                              </option>
                              {Array.from({ length: 13 }, (_, i) => (
                                <option key={i + 1} value={i + 1}>
                                  Week {i + 1}
                                </option>
                              ))}
                            </select>
                          </label>
                        </div>
                        <button
                          className="button full-width"
                          onClick={() =>
                            act(
                              "scenario",
                              async () => {
                                const s = await api<Scenario>(
                                  path + "/scenarios",
                                  {
                                    method: "POST",
                                    body: JSON.stringify(assumptions),
                                  },
                                );
                                setSelectedScenario(s.id);
                                await load();
                              },
                              "Scenario calculated and saved as a new version.",
                            )
                          }
                        >
                          <Activity size={16} /> Run & save scenario
                        </button>
                      </fieldset>
                    </section>
                    <section className="panel forecast-panel">
                      <div className="panel-heading">
                        <div>
                          <h2>Cash through the next 13 weeks</h2>
                          <p>
                            {selected
                              ? `Opening cash ${money(selected.result.opening_cash)} · ${selected.result.as_of}`
                              : "Baseline and stress comparison"}
                          </p>
                        </div>
                        <div className="legend">
                          <span>
                            <i /> Baseline
                          </span>
                          <span>
                            <i className="stress" /> Stressed
                          </span>
                        </div>
                      </div>
                      {forecastChart()}
                      {selected && (
                        <>
                          <div className="forecast-stats">
                            <div>
                              <small>BASELINE LOW POINT</small>
                              <strong>
                                {money(selected.result.baseline.lowest_cash)}
                              </strong>
                            </div>
                            <div>
                              <small>STRESSED LOW POINT</small>
                              <strong
                                className={
                                  Number(selected.result.stress.lowest_cash) < 0
                                    ? "negative"
                                    : ""
                                }
                              >
                                {money(selected.result.stress.lowest_cash)}
                              </strong>
                            </div>
                            <div>
                              <small>ADDITIONAL FUNDING NEEDED</small>
                              <strong>
                                {money(selected.result.stress.funding_needed)}
                              </strong>
                            </div>
                          </div>
                          <div className="insight">
                            <AlertTriangle size={18} />
                            <p>
                              To stay above the{" "}
                              {money(selected.assumptions.cash_buffer)} cash
                              buffer, this scenario needs{" "}
                              {money(selected.result.stress.funding_needed)} in
                              additional funding. This is a liquidity estimate,
                              not a recommended loan amount.
                            </p>
                          </div>
                          <p className="small muted">
                            Showing saved version: {selected.name} · +
                            {selected.assumptions.delay_days} collection days ·{" "}
                            {selected.assumptions.sales_change}% sales ·{" "}
                            {selected.assumptions.cost_change}% selected costs
                          </p>
                        </>
                      )}
                    </section>
                  </div>
                  {scenarios.length > 0 && (
                    <section className="panel">
                      <div className="panel-heading">
                        <h2>Saved scenario versions</h2>
                        <select
                          aria-label="Select saved scenario"
                          value={selected?.id}
                          onChange={(e) => setSelectedScenario(e.target.value)}
                        >
                          {scenarios.map((s, i) => (
                            <option key={s.id} value={s.id}>
                              {s.name} · Version {scenarios.length - i} ·{" "}
                              {new Date(s.created_at || "").toLocaleString()}
                            </option>
                          ))}
                        </select>
                      </div>
                      {selected && (
                        <>
                          <details open>
                            <summary>Forecast assumptions and method</summary>
                            {selected.result.notes.map((n) => (
                              <p key={n}>{n}</p>
                            ))}
                          </details>
                          <div className="table-scroll">
                            <table>
                              <thead>
                                <tr>
                                  <th>Week</th>
                                  <th>Collections</th>
                                  <th>Suppliers</th>
                                  <th>Payroll</th>
                                  <th>Operating</th>
                                  <th>Tax / capex / distributions</th>
                                  <th>Debt principal</th>
                                  <th>Interest</th>
                                  <th>Maturity</th>
                                  <th>Financing in</th>
                                  <th>Ending cash</th>
                                </tr>
                              </thead>
                              <tbody>
                                {selected.result.stress.weeks.map((w) => (
                                  <tr key={w.week}>
                                    <td>
                                      W{w.week}
                                      <small>{w.start}</small>
                                    </td>
                                    {(
                                      [
                                        "collections",
                                        "supplier_payments",
                                        "payroll",
                                        "operating",
                                        "tax_capex_distributions",
                                        "principal",
                                        "interest",
                                        "maturity",
                                        "financing_inflow",
                                        "cash",
                                      ] as const
                                    ).map((k) => (
                                      <td
                                        key={k}
                                        className={
                                          k === "cash" && Number(w.cash) < 0
                                            ? "negative"
                                            : ""
                                        }
                                      >
                                        {money(w[k])}
                                      </td>
                                    ))}
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                        </>
                      )}
                    </section>
                  )}
                </>
              )}
              {tab === "memo" && (
                <>
                  <div className="section-banner">
                    <span className="circle-icon">
                      <FileText size={21} />
                    </span>
                    <div>
                      <h2>A clear recommendation. An independent review.</h2>
                      <p>
                        The template uses saved calculations. Edit it with your
                        judgment before submitting.
                      </p>
                    </div>
                    <Badge>Deterministic · No AI required</Badge>
                  </div>
                  <div className="memo-grid">
                    <section className="panel memo-editor">
                      <div className="panel-heading">
                        <h2>
                          {writable ? "Draft credit memo" : "Credit memo"}
                        </h2>
                        {writable && (
                          <button
                            className="button secondary"
                            disabled={!!busy}
                            onClick={() =>
                              act(
                                "template",
                                async () => {
                                  const t = await api<{ memo: string }>(
                                    path + "/memo/template",
                                  );
                                  setMemo(t.memo);
                                },
                                "Template generated. Review it, then save your draft.",
                              )
                            }
                          >
                            <RefreshCw size={14} />{" "}
                            {memo ? "Regenerate template" : "Generate template"}
                          </button>
                        )}
                      </div>
                      {writable ? (
                        <>
                          <label className="sr-only" htmlFor="memo">
                            Credit memo text
                          </label>
                          <textarea
                            id="memo"
                            className="memo-text"
                            value={memo}
                            onChange={(e) => setMemo(e.target.value)}
                            placeholder="Generate a deterministic template from your saved records and scenario, then add your recommendation."
                          />
                          <div className="preview-footer">
                            <span className="small muted">
                              {memo === c.memo
                                ? "All draft changes saved"
                                : "Unsaved draft changes"}{" "}
                              · {memo.length.toLocaleString()} characters
                            </span>
                            <button
                              className="button"
                              disabled={!!busy || memo.length < 20}
                              onClick={() =>
                                act(
                                  "memo",
                                  async () => {
                                    await api(path + "/memo", {
                                      method: "PUT",
                                      body: JSON.stringify({
                                        memo,
                                        version: c.version,
                                      }),
                                    });
                                    await load();
                                  },
                                  "Draft memo saved.",
                                )
                              }
                            >
                              <Save size={16} /> Save draft
                            </button>
                          </div>
                        </>
                      ) : (
                        <pre className="memo-display">
                          {currentSubmission?.memo ||
                            c.memo ||
                            "No memo has been drafted yet."}
                        </pre>
                      )}
                    </section>
                    <div className="stack">
                      <section className="panel">
                        <h2>Review status</h2>
                        <div className="review-status">
                          <Badge
                            tone={c.status === "approved" ? "green" : "amber"}
                          >
                            {c.status.replaceAll("_", " ")}
                          </Badge>
                        </div>
                        <p className="muted">
                          Submitted memos include a frozen copy of the profile,
                          source records, financial analysis, and scenario.
                        </p>
                        {writable ? (
                          <>
                            <button
                              className="button full-width"
                              disabled={!!busy || !c.memo || memo !== c.memo}
                              onClick={() =>
                                act(
                                  "submit",
                                  async () => {
                                    await api(path + "/submit", {
                                      method: "POST",
                                    });
                                    await load();
                                  },
                                  "Submitted. Sign out and choose Jordan Lee to conduct the independent review.",
                                )
                              }
                            >
                              <ArrowUpRight size={16} /> Submit for review
                            </button>
                            <p className="small muted">
                              Save draft changes first. Missing documents remain
                              visible as unresolved questions.
                            </p>
                          </>
                        ) : user.role === "reviewer" &&
                          c.status === "submitted" ? (
                          <>
                            <label>
                              Review decision
                              <select
                                value={decision}
                                onChange={(e) => setDecision(e.target.value)}
                              >
                                <option value="changes_requested">
                                  Request changes
                                </option>
                                <option value="approved">
                                  Approve (simulation)
                                </option>
                                <option value="declined">
                                  Decline (simulation)
                                </option>
                              </select>
                            </label>
                            <label>
                              Reviewer comment
                              <textarea
                                rows={5}
                                value={reviewComment}
                                onChange={(e) =>
                                  setReviewComment(e.target.value)
                                }
                                placeholder="Explain your assessment and required follow-up (at least 10 characters)."
                              />
                            </label>
                            <button
                              className="button full-width"
                              disabled={
                                !!busy || reviewComment.trim().length < 10
                              }
                              onClick={() =>
                                act(
                                  "review",
                                  async () => {
                                    await api(path + "/review", {
                                      method: "POST",
                                      body: JSON.stringify({
                                        decision,
                                        comment: reviewComment,
                                      }),
                                    });
                                    setReviewComment("");
                                    await load();
                                  },
                                  "Independent review recorded. No funds were disbursed.",
                                )
                              }
                            >
                              <ShieldCheck size={16} /> Record review decision
                            </button>
                          </>
                        ) : (
                          <div className="notice">
                            <LockKeyhole size={16} />
                            {c.status === "submitted"
                              ? "Awaiting the independent demo reviewer."
                              : "The current review state is read-only."}
                          </div>
                        )}
                        <p className="small muted">
                          Approval is a simulated review decision. It never
                          triggers a disbursement.
                        </p>
                      </section>
                      {currentSubmission && (
                        <section className="panel">
                          <h2>Submitted analysis snapshot</h2>
                          <p className="small muted">
                            {new Date(
                              currentSubmission.created_at,
                            ).toLocaleString()}{" "}
                            · {currentSubmission.author_id}
                          </p>
                          <div className="data-row">
                            <span>Reporting period</span>
                            <strong>
                              {currentSubmission.snapshot.analysis.period}
                            </strong>
                          </div>
                          <div className="data-row">
                            <span>Existing DSCR</span>
                            <strong>
                              {number(
                                currentSubmission.snapshot.analysis.dscr,
                                "×",
                              )}
                            </strong>
                          </div>
                          <div className="data-row">
                            <span>Stressed funding need</span>
                            <strong>
                              {money(
                                currentSubmission.snapshot.scenario.stress
                                  .funding_needed,
                              )}
                            </strong>
                          </div>
                          <details>
                            <summary>
                              View frozen analysis and assumptions
                            </summary>
                            <pre className="json-preview">
                              {JSON.stringify(
                                {
                                  analysis: currentSubmission.snapshot.analysis,
                                  assumptions:
                                    currentSubmission.snapshot.scenario
                                      .assumptions,
                                },
                                null,
                                2,
                              )}
                            </pre>
                          </details>
                        </section>
                      )}
                      {c.reviews.map((r) => (
                        <section className="panel" key={r.id}>
                          <div className="panel-heading">
                            <h2>Reviewer comment</h2>
                            <Badge>{r.decision.replaceAll("_", " ")}</Badge>
                          </div>
                          <p>{r.comment}</p>
                          <p className="small muted">
                            Jordan Lee ·{" "}
                            {new Date(r.created_at).toLocaleString()}
                          </p>
                        </section>
                      ))}
                    </div>
                  </div>
                  {c.submissions.length > 1 && (
                    <section className="panel">
                      <h2>Previous submissions</h2>
                      {c.submissions.slice(1).map((s) => (
                        <details key={s.id}>
                          <summary>
                            {new Date(s.created_at).toLocaleString()} ·{" "}
                            {s.snapshot.analysis.period}
                          </summary>
                          <pre className="memo-display">{s.memo}</pre>
                        </details>
                      ))}
                    </section>
                  )}
                </>
              )}
              {tab === "monitoring" && (
                <>
                  <div className="section-banner">
                    <span className="circle-icon">
                      <Activity size={21} />
                    </span>
                    <div>
                      <h2>The work continues after review.</h2>
                      <p>
                        Track reporting, collection trends, and the conditions
                        you explicitly configure.
                      </p>
                    </div>
                    <Badge tone={pending ? "amber" : "green"}>
                      {pending} open alerts
                    </Badge>
                  </div>
                  <div className="two-column">
                    <section className="panel">
                      <div className="panel-heading">
                        <h2>Load the next chapter</h2>
                        <Badge>January 2026</Badge>
                      </div>
                      <p className="muted">
                        Atlas delays its payments by an additional 45 days.
                        Harbor remains profitable, but receivables rise to
                        $240,000. Preview and commit both schedules, then
                        evaluate monitoring.
                      </p>
                      <div className="button-row">
                        <button
                          className="button secondary"
                          disabled={user.role !== "analyst" || !!busy}
                          onClick={() =>
                            examplePreview(
                              "harbor-receivables-2026-01.csv",
                              "receivables",
                            )
                          }
                        >
                          <UploadCloud size={16} /> Later receivables
                        </button>
                        <button
                          className="button secondary"
                          disabled={user.role !== "analyst" || !!busy}
                          onClick={() =>
                            examplePreview(
                              "harbor-monthly-2026-01.csv",
                              "monthly",
                            )
                          }
                        >
                          <UploadCloud size={16} /> Later financial report
                        </button>
                      </div>
                      <div className="download-row">
                        <a href="/api/examples/harbor-receivables-2026-01.csv">
                          Download later receivables
                        </a>
                        <a href="/api/examples/harbor-monthly-2026-01.csv">
                          Download later report
                        </a>
                      </div>
                      <div className="monitor-run">
                        <label>
                          Evaluate as of (demo clock)
                          <input
                            type="date"
                            value={monitorDate}
                            onChange={(e) => setMonitorDate(e.target.value)}
                          />
                        </label>
                        <button
                          className="button"
                          disabled={user.role !== "analyst" || !!busy}
                          onClick={() =>
                            act(
                              "monitor",
                              async () => {
                                const result = await api<{
                                  evaluations: typeof evaluations;
                                }>(path + "/monitoring/evaluate", {
                                  method: "POST",
                                  body: JSON.stringify({ as_of: monitorDate }),
                                });
                                setEvaluations(result.evaluations);
                                await load();
                              },
                              "Monitoring evaluated. Review the alerts and record your follow-up.",
                            )
                          }
                        >
                          <Activity size={16} /> Evaluate monitoring
                        </button>
                      </div>
                      {evaluations.map((e) => (
                        <div className="data-row" key={e.id}>
                          <span>
                            {e.metric.toUpperCase()} · {e.evaluated_period}
                          </span>
                          <Badge
                            tone={e.status === "breach" ? "amber" : "neutral"}
                          >
                            {e.value || "Insufficient data"} ·{" "}
                            {e.status === "breach"
                              ? "threshold exceeded"
                              : e.status.replaceAll("_", " ")}
                          </Badge>
                        </div>
                      ))}
                    </section>
                    <section className="panel form-panel">
                      <h2>Explicit monitoring conditions</h2>
                      <p className="muted">
                        Thresholds below are illustrative. An internal warning
                        is not a contractual covenant.
                      </p>
                      <fieldset disabled={user.role !== "analyst" || !!busy}>
                        <div className="form-grid">
                          <label>
                            Expected report
                            <input
                              type="month"
                              value={profile.expected_report_period}
                              onChange={(e) =>
                                setProfile({
                                  ...profile,
                                  expected_report_period: e.target.value,
                                })
                              }
                            />
                          </label>
                          <label>
                            Reporting deadline
                            <input
                              type="date"
                              value={profile.reporting_deadline}
                              onChange={(e) =>
                                setProfile({
                                  ...profile,
                                  reporting_deadline: e.target.value,
                                })
                              }
                            />
                          </label>
                        </div>
                        {profile.conditions.map((r, i) => (
                          <div className="condition" key={r.id}>
                            <div>
                              <label className="check-label">
                                <input
                                  type="checkbox"
                                  checked={r.enabled}
                                  onChange={(e) =>
                                    setProfile({
                                      ...profile,
                                      conditions: profile.conditions.map(
                                        (item, j) =>
                                          j === i
                                            ? {
                                                ...item,
                                                enabled: e.target.checked,
                                              }
                                            : item,
                                      ),
                                    })
                                  }
                                />
                                {r.metric === "dso"
                                  ? "Collection-days warning"
                                  : "Illustrative DSCR covenant"}
                              </label>
                              <Badge
                                tone={
                                  r.category === "contractual_covenant"
                                    ? "amber"
                                    : "neutral"
                                }
                              >
                                {r.category.replaceAll("_", " ")}
                              </Badge>
                            </div>
                            <p className="small muted">
                              {r.metric === "dso"
                                ? "Monthly ending AR ÷ sales × calendar days. Alert above:"
                                : "Trailing 12-month CADS ÷ scheduled debt service. Alert below:"}
                            </p>
                            <input
                              aria-label={r.metric + " threshold"}
                              type="number"
                              step="0.01"
                              value={r.threshold}
                              onChange={(e) =>
                                setProfile({
                                  ...profile,
                                  conditions: profile.conditions.map(
                                    (item, j) =>
                                      j === i
                                        ? { ...item, threshold: e.target.value }
                                        : item,
                                  ),
                                })
                              }
                            />
                          </div>
                        ))}
                        <button
                          className="button secondary"
                          onClick={() =>
                            act(
                              "conditions",
                              async () => {
                                await api(path + "/monitoring", {
                                  method: "PUT",
                                  body: JSON.stringify({
                                    conditions: profile.conditions,
                                    reporting_deadline:
                                      profile.reporting_deadline,
                                    expected_report_period:
                                      profile.expected_report_period,
                                  }),
                                });
                                await load();
                              },
                              "Monitoring definitions saved. Evaluate to apply them.",
                            )
                          }
                        >
                          <Save size={15} /> Save conditions
                        </button>
                      </fieldset>
                    </section>
                  </div>
                  <section className="panel">
                    <div className="panel-heading">
                      <h2>Actionable alerts</h2>
                      <Badge>{alerts.length} recorded</Badge>
                    </div>
                    {alerts.length ? (
                      alerts.map((alert) => (
                        <AlertEditor
                          key={alert.id + alert.status + alert.notes}
                          alert={alert}
                          disabled={!!busy}
                          save={(body) =>
                            act(
                              "alert",
                              async () => {
                                await api(path + `/alerts/${alert.id}`, {
                                  method: "PUT",
                                  body: JSON.stringify(body),
                                });
                                await load();
                              },
                              "Alert assignment and follow-up saved.",
                            )
                          }
                        />
                      ))
                    ) : (
                      <Empty title="No alerts have been generated">
                        Load the subsequent reports and evaluate monitoring. An
                        empty alert list does not mean the borrower meets every
                        condition.
                      </Empty>
                    )}
                  </section>
                </>
              )}
              <footer className="footer">
                <span>
                  <ShieldCheck size={13} /> Synthetic portfolio demo · Human
                  judgment required
                </span>
                <span>USD · Calculations by FastAPI · {a.period_end}</span>
              </footer>
            </>
          )}
        </main>
      </div>
      {help && (
        <div className="modal-backdrop" onClick={() => setHelp(false)}>
          <section
            className="modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="guide-title"
            onClick={(e) => e.stopPropagation()}
          >
            <button
              className="close-modal"
              aria-label="Close guide"
              onClick={() => setHelp(false)}
            >
              <X />
            </button>
            <Badge tone="green">Your first case</Badge>
            <h2 id="guide-title">Follow Harbor from intake to monitoring.</h2>
            <ol className="guide-list">
              <li>
                Sign in as Alex. In Financial intake, choose Receivables and use
                the Harbor sample. Validate, preview, and commit.
              </li>
              <li>
                Explore Repayment analysis. Every figure comes from persisted
                source records.
              </li>
              <li>
                Run and save the default 30-day delayed-collections scenario.
              </li>
              <li>
                Generate a memo, add your recommendation, save, and submit.
              </li>
              <li>
                Sign out using the sidebar icon. Choose Jordan, open Credit memo
                & review, and record a decision with comments.
              </li>
              <li>
                Return as Alex. In Monitoring, preview and commit both January
                schedules, then evaluate. Assign and resolve the collections
                alert.
              </li>
            </ol>
            <p className="muted">
              This is a learning environment with two selectable demo
              identities, not production authentication. No real loan is
              approved or funded.
            </p>
            <button
              className="button"
              onClick={() => {
                setHelp(false);
                navigate("intake");
              }}
            >
              Start with the records <ArrowRight size={16} />
            </button>
          </section>
        </div>
      )}
      {newCase && (
        <div className="modal-backdrop">
          <section
            className="modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="new-case-title"
          >
            <button
              className="close-modal"
              aria-label="Close new case"
              onClick={() => setNewCase(false)}
            >
              <X />
            </button>
            <h2 id="new-case-title">Create a borrower case</h2>
            <p className="muted">
              Start an empty synthetic case. No figures will be assumed.
            </p>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                const data = new FormData(e.currentTarget);
                act(
                  "new-case",
                  async () => {
                    const v = await api<{ id: string }>("/cases", {
                      method: "POST",
                      body: JSON.stringify({
                        name: data.get("name"),
                        industry: data.get("industry"),
                        amount: data.get("amount"),
                      }),
                    });
                    setNewCase(false);
                    setCaseId(v.id);
                    setC(null);
                    setTab("profile");
                  },
                  "New borrower case created.",
                );
              }}
            >
              <label>
                Business name
                <input name="name" required minLength={2} />
              </label>
              <label>
                Industry
                <input name="industry" required />
              </label>
              <label>
                Requested amount ($)
                <input name="amount" type="number" min="1" required />
              </label>
              <button className="button" disabled={!!busy}>
                Create case <ArrowRight size={16} />
              </button>
            </form>
          </section>
        </div>
      )}
    </div>
  );
}

function AlertEditor({
  alert,
  disabled,
  save,
}: {
  alert: AlertItem;
  disabled: boolean;
  save: (body: {
    status: string;
    assignee: string;
    notes: string;
  }) => Promise<void>;
}) {
  const [notes, setNotes] = useState(alert.notes),
    [assignee, setAssignee] = useState(alert.assignee),
    [status, setStatus] = useState(alert.status);
  return (
    <article
      className={
        "alert-card " + (alert.status === "resolved" ? "resolved" : "")
      }
    >
      <div className="alert-title">
        <span className="circle-icon amber-icon">
          {alert.status === "resolved" ? (
            <CheckCircle2 size={18} />
          ) : (
            <AlertTriangle size={18} />
          )}
        </span>
        <div>
          <h3>{alert.title}</h3>
          <span className="small muted">Reporting period {alert.period}</span>
        </div>
        <Badge tone={alert.status === "resolved" ? "green" : "amber"}>
          {alert.status}
        </Badge>
        <Badge>{alert.category.replaceAll("_", " ")}</Badge>
      </div>
      <p>{alert.detail}</p>
      <div className="form-grid three">
        <label>
          Assigned to
          <select
            value={assignee}
            onChange={(e) => setAssignee(e.target.value)}
          >
            <option value="analyst">Alex Morgan · Analyst</option>
            <option value="reviewer">Jordan Lee · Reviewer</option>
          </select>
        </label>
        <label>
          Status
          <select value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="open">Open</option>
            <option value="resolved">Resolved</option>
          </select>
        </label>
        <label>
          Follow-up / resolution note
          <input
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            placeholder="Record the action taken"
          />
        </label>
      </div>
      <button
        className="button secondary"
        disabled={disabled}
        onClick={() => save({ status, assignee, notes })}
      >
        <Save size={15} /> Save follow-up
      </button>
    </article>
  );
}
