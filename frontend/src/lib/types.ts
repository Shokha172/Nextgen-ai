/** API response types — mirrors backend/app/schemas/*. Nothing is computed here. */

export type Lang = "uz" | "ru" | "en" | "kk" | "tr" | "ky";
export type Role = "owner" | "admin" | "analyst" | "viewer";
export type Severity = "critical" | "warning" | "info";

export interface ApiErrorBody {
  error: { code: string; message: string; request_id?: string; details?: unknown };
}

export interface User {
  id: string;
  email: string;
  full_name: string;
  locale: Lang;
  is_active: boolean;
  is_demo: boolean;
  email_verified: boolean;
  last_login_at: string | null;
}

export interface Membership {
  organization_id: string;
  role: Role;
  status: string;
  department: string | null;
  title: string | null;
  name?: string;
  slug?: string;
  is_demo?: boolean;
}

export interface Session {
  user: User;
  memberships: Membership[];
  active_organization: {
    id: string;
    name: string;
    slug: string;
    is_demo: boolean;
    role?: Role;
    currency?: string;
    timezone?: string;
  } | null;
  role: Role | null;
  token?: { access_token: string; token_type: string; expires_in: number };
}

export interface Organization {
  id: string;
  name: string;
  slug: string;
  industry: string;
  country: string;
  region: string | null;
  city: string | null;
  address: string | null;
  timezone: string;
  currency: string;
  anomaly_z_threshold: string | number;
  anomaly_min_deviation_pct: string | number;
  is_demo: boolean;
  is_active: boolean;
  created_at: string;
}

export interface Meter {
  id: string;
  name: string;
  serial_number: string;
  department: string | null;
  location: string | null;
  meter_type: string;
  unit: string;
  multiplier: string;
  interval_minutes: number;
  max_power_kw: string | null;
  status: string;
  notes: string | null;
  created_at: string;
  readings?: number;
  first_reading_at?: string | null;
  last_reading_at?: string | null;
  total_kwh?: string | null;
}

export interface Tariff {
  id: string;
  name: string;
  currency: string;
  price_per_kwh: string;
  peak_multiplier: string;
  offpeak_multiplier: string;
  valid_from: string;
  valid_to: string | null;
  is_default: boolean;
  notes: string | null;
}

export interface Reading {
  id: string;
  meter_id: string;
  ts: string;
  consumption_kwh: string;
  interval_minutes: number;
  power_kw: string | null;
  quality: string;
  source: string;
}

export interface ReadingPage {
  items: Reading[];
  page: number;
  page_size: number;
  total: number;
  has_next: boolean;
}

export interface Coverage {
  expected_intervals: number;
  present_intervals: number;
  coverage_pct: number;
}

export interface Member {
  id: string;
  user_id: string;
  role: Role;
  status: string;
  title: string | null;
  department: string | null;
  invited_email: string | null;
  accepted_at: string | null;
  created_at: string;
  email: string | null;
  full_name: string | null;
}

/* ---- dashboard ------------------------------------------------------- */
export interface PeriodWindow {
  name?: string;
  start: string;
  end: string;
  start_local?: string;
  end_local?: string;
  timezone?: string;
  granularity?: string;
}

export interface TariffRef {
  id?: string;
  name: string;
  price_per_kwh: number | string;
  note?: string;
}

export interface DashboardSummary {
  period: PeriodWindow;
  has_data: boolean;
  consumption: {
    total_kwh: number;
    readings: number;
    average_power_kw: number;
    peak_power_kw: number;
    meters_contributing: number;
    data_coverage_pct: number;
  };
  cost: { estimated: number | null; currency: string; tariff: TariffRef | null };
  trend: {
    vs_previous_period_pct: number | null;
    previous_period_kwh: number;
    vs_last_year_pct: number | null;
    last_year_kwh: number;
    previous_period_range: { start: string; end: string } | null;
  };
  efficiency: { kwh_per_meter_day: number | null; peak_to_average_ratio: number | null };
  anomalies: {
    count: number;
    unacknowledged: number;
    critical?: number;
    by_severity?: Record<string, number>;
    latest?: Array<{
      id: string;
      meter: string;
      ts: string;
      observed_kwh: number;
      expected_kwh: number;
      deviation_pct: number;
      severity: Severity;
    }>;
    top?: Array<{
      id: string;
      meter: string;
      ts: string;
      observed_kwh: number;
      expected_kwh: number;
      deviation_pct: number;
      severity: Severity;
    }>;
  };
  forecast?: { total_kwh: number | null; mape: number | null; confidence: string | null } | null;
  top_meters?: Array<{ meter_id: string; name: string; consumption_kwh: number; share_pct: number }>;
  narrative?: string | null;
}

/* ---- analytics ------------------------------------------------------- */
export interface SeriesPoint {
  bucket: string;
  label: string;
  consumption_kwh: number;
  readings: number;
  average_power_kw: number;
  peak_power_kw: number;
  estimated_cost: number | null;
}

export interface MeterBreakdown {
  meter_id: string;
  name: string;
  serial_number: string;
  department: string | null;
  consumption_kwh: number;
  readings: number;
  peak_power_kw: number;
  share_pct: number;
  estimated_cost: number | null;
  currency: string;
}

export interface ConsumptionAnalytics {
  window: PeriodWindow;
  totals: {
    consumption_kwh: number;
    readings: number;
    average_power_kw: number;
    peak_power_kw: number;
    meters: number;
    expected_intervals: number;
    data_coverage_pct: number;
    estimated_cost: number | null;
    currency: string;
    tariff: TariffRef | null;
  };
  series: SeriesPoint[];
  by_meter: MeterBreakdown[];
  by_department: Array<{ department: string; consumption_kwh: number; share_pct: number }>;
  hourly_profile: Array<{ hour: number; average_kwh: number; total_kwh: number; readings: number }>;
  peaks: Array<{
    ts: string;
    consumption_kwh: number;
    power_kw?: number;
    meter: string;
    meter_id?: string;
  }>;
}

export interface Comparison {
  mode: string;
  current: { start: string; end: string; consumption_kwh: number; estimated_cost: number | null; data_coverage_pct: number; readings: number };
  baseline: { start: string; end: string; consumption_kwh: number; estimated_cost: number | null; data_coverage_pct: number; readings: number };
  difference_kwh: number;
  difference_pct: number | null;
  why_null_pct: string | null;
}

/* ---- anomalies ------------------------------------------------------- */
export interface Anomaly {
  id: string;
  meter_id: string;
  meter: string;
  ts: string;
  observed_kwh: number;
  expected_kwh: number;
  deviation_pct: number;
  severity: Severity;
  method: string;
  explanation: string;
  explanations?: Partial<Record<Lang, string>>;
  details?: Record<string, unknown>;
  acknowledged: boolean;
}

export interface AnomalyPage {
  items: Anomaly[];
  total: number;
  limit: number;
  offset: number;
}

/* ---- forecast -------------------------------------------------------- */
export interface Forecast {
  forecast_id: string;
  generated_at: string;
  horizon_days: number;
  method: string;
  granularity: string;
  meter_id: string | null;
  total_kwh: number;
  total_cost: number | null;
  currency: string;
  tariff: TariffRef | null;
  accuracy_mape: number | null;
  confidence: string;
  data_coverage_pct: number;
  history_days: number;
  points: Array<{ date: string; consumption_kwh: number; estimated_cost: number | null }>;
  history?: Array<{ date: string; consumption_kwh: number }>;
  backtest?: Record<string, unknown> | null;
  note?: string | null;
}

/* ---- AI advisor ------------------------------------------------------ */
export interface AiInsight {
  insight_id: string;
  intent: string;
  language: Lang;
  answer: string;
  measured_facts: Record<string, unknown>;
  suggestions?: string[];
  limitations?: string[];
  guard_flags?: Record<string, unknown>;
  grounding?: { passed: boolean; rejected_numbers?: string[]; provider?: string };
  provider?: string;
  created_at?: string;
  facts?: Record<string, unknown>;
}

export interface AiInsightPage {
  items: AiInsight[];
  total: number;
}

/* ---- savings --------------------------------------------------------- */
export interface SavingsReport {
  id: string;
  name: string;
  period_start: string;
  period_end: string;
  baseline_method: string;
  baseline_start: string | null;
  baseline_end: string | null;
  baseline_kwh: number | null;
  current_kwh: number | null;
  savings_kwh: number | null;
  savings_amount: number | null;
  currency: string;
  baseline_coverage_pct: number | null;
  current_coverage_pct: number | null;
  quality: "verified" | "indicative" | "insufficient";
  verified: boolean;
  explanation: string;
  created_at: string;
}

/* ---- reports --------------------------------------------------------- */
export interface Report {
  id: string;
  kind: string;
  format: string;
  filename: string;
  size_bytes: number;
  created_at: string;
  period?: string | null;
  language?: string | null;
  title?: string | null;
}

/* ---- notifications --------------------------------------------------- */
export interface Notification {
  id: string;
  type: string;
  title: string;
  body: string;
  severity: Severity;
  read_at: string | null;
  created_at: string;
  link?: string | null;
}

export interface NotificationPage {
  items: Notification[];
  total: number;
  unread: number;
  limit: number;
  offset: number;
}

/* ---- imports --------------------------------------------------------- */
export interface ImportPreviewRow {
  row: number;
  ts: string | null;
  consumption_kwh: string | number | null;
  power_kw: string | number | null;
  status: "valid" | "error" | "duplicate" | "out_of_order";
  message: string | null;
}

export interface ImportJob {
  id: string;
  filename: string;
  status: string;
  reading_type: string;
  meter_id: string | null;
  column_mapping: Record<string, string | null>;
  total_rows: number;
  valid_rows: number;
  invalid_rows: number;
  duplicate_rows: number;
  missing_intervals: number;
  errors: unknown[];
  warnings: unknown[];
  preview: ImportPreviewRow[];
  created_at: string;
  confirmed_at: string | null;
}

export interface ImportResult {
  job_id: string;
  status: string;
  inserted: number;
  skipped_duplicates: number;
  invalid: number;
  missing_intervals: number;
  first_reading_at: string | null;
  last_reading_at: string | null;
  message: string;
}

/* ---- telegram -------------------------------------------------------- */
export interface TelegramAccount {
  id: string;
  telegram_user_id: number;
  telegram_username: string | null;
  language: Lang;
  is_demo: boolean;
  alerts_enabled: boolean;
  created_at: string;
}

export interface LinkCode {
  code: string;
  expires_at: string;
  bot_mode: string;
  bot_username?: string | null;
  organization: string;
  is_demo: boolean;
}
