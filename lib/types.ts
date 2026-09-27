export type User = { id: string; name: string; role: string };
export type DocumentItem = {
  name: string;
  received: boolean;
  verified: boolean;
};
export type Condition = {
  id: string;
  category: string;
  metric: string;
  operator: string;
  threshold: string;
  period: string;
  enabled: boolean;
};
export type Profile = {
  name: string;
  industry: string;
  location: string;
  owner: string;
  requested_amount: string;
  purpose: string;
  reported_collection_days: number;
  supplier_terms_days: number;
  verified: boolean;
  documents: DocumentItem[];
  opening: Record<string, string>;
  conditions: Condition[];
  reporting_deadline: string;
  expected_report_period: string;
  proposed_terms?: {
    draw: string;
    annual_rate: string;
    principal_due: string;
  } | null;
};
export type Analysis = {
  period: string;
  period_start: string;
  period_end: string;
  revenue: string | null;
  ebitda: string | null;
  cads: string | null;
  dscr: string | null;
  debt_service: string | null;
  cash: string | null;
  current_ratio: string | null;
  working_capital: string | null;
  dso: string | null;
  receivables: string | null;
  ar_as_of: string | null;
  missing: string[];
  reasons: string[];
  reconciliation: string[];
  aging: { name: string; amount: string }[];
  concentration: { name: string; sales: string; share: string }[];
  proposed: {
    status: string;
    reason?: string;
    interest?: string;
    principal?: string;
    dscr?: string;
    terms?: Record<string, string>;
  };
  sources: Record<string, string | null>;
  history: {
    period: string;
    revenue: string;
    cash: string;
    receivables: string;
    payables: string;
  }[];
  bank_classification: { category: string; amount: string }[];
};
export type Assumptions = {
  name: string;
  period: string;
  delay_days: number;
  sales_change: string;
  cost_change: string;
  cash_buffer: string;
  draw: string;
  annual_rate: string;
  maturity_week: number | null;
};
export type ForecastWeek = {
  week: number;
  start: string;
  end: string;
  opening: string;
  collections: string;
  supplier_payments: string;
  payroll: string;
  operating: string;
  tax_capex_distributions: string;
  principal: string;
  interest: string;
  maturity: string;
  financing_inflow: string;
  cash: string;
};
export type Forecast = {
  status: string;
  as_of: string;
  opening_cash: string;
  baseline: {
    weeks: ForecastWeek[];
    lowest_cash: string;
    funding_needed: string;
    ending_cash: string;
  };
  stress: {
    weeks: ForecastWeek[];
    lowest_cash: string;
    funding_needed: string;
    ending_cash: string;
  };
  assumptions: Assumptions;
  notes: string[];
};
export type Scenario = {
  id: string;
  name: string;
  assumptions: Assumptions;
  result: Forecast;
  created_at?: string;
};
export type CaseData = {
  id: string;
  profile: Profile;
  status: string;
  memo: string;
  version: number;
  owner_id: string;
  submissions: {
    id: string;
    memo: string;
    created_at: string;
    author_id: string;
    snapshot: { analysis: Analysis; scenario: Forecast; profile: Profile };
  }[];
  reviews: {
    id: string;
    decision: string;
    comment: string;
    reviewer_id: string;
    created_at: string;
  }[];
  events: {
    id: number;
    actor: string;
    action: string;
    created_at: string;
    detail: Record<string, unknown>;
  }[];
};
export type ImportItem = {
  id: string;
  kind: string;
  filename: string;
  status: string;
  count: number;
  created_at: string;
  correction_reason?: string;
};
export type Preview = {
  id: string;
  count: number;
  errors: { row: number; field: string; message: string }[];
  preview: Record<string, string>[];
  columns: string[];
  corrections: number;
  synthetic: boolean;
};
export type AlertItem = {
  id: string;
  rule_id: string;
  period: string;
  category: string;
  title: string;
  detail: string;
  status: string;
  assignee: string;
  notes: string;
};
