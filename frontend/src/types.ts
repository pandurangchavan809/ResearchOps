export interface Credits {
  limit: number;
  used: number;
  remaining: number;
}

export interface User {
  id: string;
  email: string;
  credits: Credits;
}

export interface TokenResponse {
  access_token: string;
  expires_in: number;
  user: User;
}

export interface ModelInfo {
  id: string;
  label: string;
  name: string;
  provider: string;
  provider_label: string;
  role: string;
}

export interface AppConfig {
  models: ModelInfo[];
  auto_chain: string[];
  search_configured: boolean;
  max_question_chars: number;
  max_reports_per_run: number;
  default_report_pages: number;
  max_report_pages: number;
}

export interface Step {
  step: string;
  label: string;
  status: "running" | "done";
  detail?: string | null;
  duration_ms?: number;
}

export type ClaimStatus = "supported" | "partially_supported" | "conflicting" | "unsupported";

export interface Claim {
  text: string;
  status: ClaimStatus;
  rationale: string;
  citations: number[];
}

export interface Source {
  id: number;
  url: string;
  title: string;
  domain: string;
  published_date: string | null;
  excerpts: string[];
}

export interface ResearchResult {
  title: string;
  answer_markdown: string;
  claims: Claim[];
  sources: Source[];
  limitations: string[];
  models_used: string[];
  stats: { searches: number; pages_fetched: number; sources_considered: number; iterations: number; tokens_used: number };
  steps: Step[];
}

export interface ReportInfo {
  status: "none" | "generating" | "ready" | "failed";
  title: string | null;
  pages: number | null;
  requested_pages: number | null;
  generations: number;
  generations_limit: number;
}

export interface RunSummary {
  id: string;
  title: string;
  status: string;
  created_at: number;
}

export interface RunDetail extends RunSummary {
  question: string;
  error: string | null;
  result: ResearchResult | null;
  report: ReportInfo;
}

export type ResearchEvent =
  | { event: "started"; data: { run_id: string; credits: Credits } }
  | { event: "step"; data: Step }
  | { event: "result"; data: { run_id: string; title: string; result: ResearchResult; credits: Credits; report_request: { pages: number } | null } }
  | { event: "rejected"; data: { run_id: string; message: string; credits: Credits } }
  | { event: "error"; data: { run_id: string; message: string; credits: Credits } };

export type ViewStatus = "streaming" | "done" | "stopped" | "rejected" | "error";

export interface ResearchView {
  runId: string | null;
  question: string;
  status: ViewStatus;
  steps: Step[];
  result: ResearchResult | null;
  message: string | null;
  report: ReportInfo | null;
  reportError: string | null;
  reportPages: number | null;
}
