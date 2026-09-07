export type Role = "analyst" | "site_manager" | "leadership" | "admin";

export type LsrEvidence = {
  text: string;
  type: "phrase" | "keyword" | "energy" | "barrier" | "exposure" | string;
};

export type LsrTag = {
  rule_id?: string;
  rule_name?: string;
  lsr_category: string;
  confidence: number;
  source: "rule" | "model" | string;
  evidence?: LsrEvidence[];
};

export type LsrRuleMetadata = {
  rule_id: string;
  name: string;
  short_name: string;
  description: string;
  related_energy_types: string[];
  related_exposure_types: string[];
  related_barrier_types: string[];
};

export type PriorityTier = "CRITICAL" | "HIGH" | "MEDIUM" | "LOW";

export type PriorityComponent = {
  name: string;
  raw_value: unknown;
  score: number;
  weight: number;
  weighted_score: number;
  description: string;
};

export type PriorityBreakdown = {
  sif_probability: PriorityComponent;
  barrier_criticality: PriorityComponent;
  recurrence: PriorityComponent;
  trend: PriorityComponent;
  exposure: PriorityComponent;
  cross_site: PriorityComponent;
};

export type PriorityOut = {
  score: number;
  tier: PriorityTier;
  version: string;
  explanation_summary: string;
  action_recommendation: string;
  components: PriorityBreakdown;
};

export type PrioritySummaryRow = {
  tier: PriorityTier;
  count: number;
  percentage: number;
};

export type LifecycleStatus =
  | "INGESTED"
  | "AI_ANALYZED"
  | "HSE_REVIEW"
  | "CONFIRMED"
  | "OVERRIDDEN"
  | "ACTION_ASSIGNED"
  | "IN_PROGRESS"
  | "RESOLVED"
  | "REOPENED"
  | "REJECTED";

export type ReportReviewOut = {
  id: string;
  report_id: string;
  user_id?: string | null;
  decision: "CONFIRMED" | "OVERRIDDEN" | string;
  previous_ai_classification: boolean;
  final_classification: boolean;
  reason?: string | null;
  notes?: string | null;
  model_version?: string | null;
  created_at: string;
};

export type TimelineEventOut = {
  id: string;
  event_type: string;
  title: string;
  description: string;
  user_id?: string | null;
  user_name?: string | null;
  timestamp: string;
  metadata_json?: Record<string, unknown>;
};

export type LifecycleKpiOut = {
  pending_review: number;
  confirmed_sif: number;
  ai_overrides: number;
  open_actions: number;
  overdue_actions: number;
  resolved_cases: number;
  reopened_cases: number;
  agreement_rate: number;
  total_cases: number;
};

export type AgreementAnalyticsOut = {
  total_reviewed: number;
  confirm_count: number;
  override_count: number;
  agreement_rate: number;
  override_rate: number;
  false_positive_count: number;
  false_negative_count: number;
  reason_breakdown: Record<string, number>;
  monthly_trend: Array<{ month: string; confirmed: number; overridden: number; agreement_rate: number }>;
};

export type LabelState = "SIF" | "NON_SIF" | "UNCERTAIN" | "UNLABELED";

export type LabelReviewOut = {
  id: string;
  report_id: string;
  reviewer_id: string;
  reviewer_username?: string | null;
  reviewer_role?: string | null;
  label: LabelState;
  reason: string;
  notes?: string | null;
  review_version: number;
  created_at: string;
};

export type ReportLabelHistoryOut = {
  report_id: string;
  predicted_sif?: boolean | null;
  human_label: string;
  validated_label?: string | null;
  label_source: string;
  validation_status: string;
  total_reviews: number;
  unique_reviewers_count: number;
  distinct_labels: string[];
  is_consensus_validated: boolean;
  has_disagreement: boolean;
  reviews: LabelReviewOut[];
};

export type ReviewerAgreementSummaryOut = {
  multi_reviewed_reports: number;
  total_comparison_pairs: number;
  consensus_agreements: number;
  disagreements: number;
  cohens_kappa: number;
  observed_agreement: number;
  expected_agreement: number;
  sample_size: number;
  interpretation: string;
};

export type Phrase = { phrase: string; weight: number };

export type ReportSummary = {
  id: string;
  report_type: string;
  site_id: string;
  site_name?: string | null;
  department?: string | null;
  reported_at: string;
  sif_label?: boolean | null;
  sif_probability?: number | null;
  lsr_tags: LsrTag[];
  excerpt?: string | null;
  priority?: PriorityOut | null;
  lifecycle_status?: LifecycleStatus;
  final_sif_label?: boolean | null;
  final_priority?: PriorityTier | string | null;
  resolution_notes?: string | null;
  resolved_at?: string | null;
  review?: ReportReviewOut | null;
  predicted_sif?: boolean | null;
  human_label?: string;
  validated_label?: string | null;
  label_source?: string;
  validation_status?: string;
  data_type?: string;
};

export type ReportDetail = ReportSummary & {
  raw_text_redacted: string;
  shift?: string | null;
  equipment_type?: string | null;
  job_type?: string | null;
  contributing_phrases: Phrase[];
  model_version?: string | null;
  classified_at?: string | null;
  cluster_id?: string | null;
  features: Record<string, unknown>;
  feedback_history: Array<Record<string, unknown>>;
  label_reviews: LabelReviewOut[];
};

export type Cluster = {
  id: string;
  representative_activity: string;
  representative_location: string;
  representative_barrier_failure: string;
  cluster_size: number;
  trend_status: string;
  priority?: PriorityOut | null;
};

export type RecommendationStatus =
  | "PENDING_REVIEW"
  | "ACCEPTED"
  | "EDITED"
  | "REJECTED"
  | "IMPLEMENTED"
  | "RESOLVED";

export type RecommendationFeedback = {
  id: string;
  recommendation_id: string;
  user_id?: string | null;
  decision: string;
  original_text: string;
  edited_text?: string | null;
  reason?: string | null;
  created_at: string;
};

export type Recommendation = {
  id: string;
  report_id?: string | null;
  cluster_id?: string | null;
  site_id?: string | null;
  activity?: string | null;
  category: string;
  title: string;
  action: string;
  confidence: number;
  priority: PriorityTier | string;
  evidence: string[];
  source_signals: Record<string, unknown>;
  rationale: string;
  status: RecommendationStatus;
  version: string;
  assigned_owner?: string | null;
  due_date?: string | null;
  resolution_notes?: string | null;
  created_at: string;
  updated_at: string;
  feedback_history: RecommendationFeedback[];
};

export type ExecutiveFocusArea = {
  area_name: string;
  priority_tier: PriorityTier | string;
  cluster_id?: string | null;
  site_count: number;
  trend_status: string;
  report_count: number;
  sif_rate: number;
  recommended_actions: string[];
  primary_barrier_failure: string;
};

export type ConfusionMatrixOut = {
  tp: number;
  tn: number;
  fp: number;
  fn: number;
};

export type ModelHealthOut = {
  total_reviewed: number;
  insufficient_data: boolean;
  agreement_rate: number;
  cohen_kappa: number;
  confusion_matrix: ConfusionMatrixOut;
  false_positive_rate: number;
  false_negative_rate: number;
  agreement_by_model_version: Record<string, number>;
};

export type ErrorReportItem = {
  report_id: string;
  source_report_id: string;
  excerpt: string;
  ai_sif_label: boolean;
  human_sif_label: boolean;
  model_version: string;
  site_name?: string | null;
  reviewed_at?: string | null;
};

export type ErrorAnalysisOut = {
  insufficient_data: boolean;
  false_positives: ErrorReportItem[];
  false_negatives: ErrorReportItem[];
  errors_by_model_version: Record<string, Record<string, number>>;
  errors_by_site: Record<string, Record<string, number>>;
  errors_by_lsr: Record<string, Record<string, number>>;
};

export type ModelVersionMetrics = {
  model_version: string;
  created_at?: string | null;
  feedback_count: number;
  precision?: number | null;
  recall?: number | null;
  f1?: number | null;
  roc_auc?: number | null;
  accuracy?: number | null;
  sample_size?: number | null;
};

export type ModelDriftOut = {
  versions: ModelVersionMetrics[];
  has_regression: boolean;
};

export type InterventionEffectivenessOut = {
  insufficient_data: boolean;
  total_recommendations: number;
  accepted: number;
  rejected: number;
  implemented: number;
  resolved: number;
  acceptance_rate: number;
  implementation_rate: number;
  resolution_rate: number;
  mean_days_to_resolution?: number | null;
  monthly_resolution_trend: Array<{ month: string; resolved_count: number }>;
  sif_rate_before_intervention?: number | null;
  sif_rate_after_intervention?: number | null;
};


const TOKEN_KEY = "sif_access_token";
const USER_KEY = "sif_user";

export function getToken() {
  return localStorage.getItem(TOKEN_KEY);
}

export function getStoredUser(): { username: string; role: Role; user_id: string } | null {
  const raw = localStorage.getItem(USER_KEY);
  return raw ? JSON.parse(raw) : null;
}

export function clearSession() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Content-Type", "application/json");
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const res = await fetch(path, { ...init, headers });
  if (res.status === 401) {
    clearSession();
    if (!path.includes("/auth/login")) window.location.href = "/login";
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail));
  }
  return res.json();
}

export async function login(username: string, password: string) {
  const data = await request<{
    access_token: string;
    refresh_token: string;
    role: Role;
    username: string;
    user_id: string;
  }>("/v1/auth/login", {
    method: "POST",
    body: JSON.stringify({ username, password }),
  });
  localStorage.setItem(TOKEN_KEY, data.access_token);
  localStorage.setItem(USER_KEY, JSON.stringify({ username: data.username, role: data.role, user_id: data.user_id }));
  return data;
}

export type ValidationIssue = {
  field: string;
  severity: "error" | "warning" | "info";
  message: string;
};

export type ValidatedRowPreview = {
  row_index: number;
  is_valid: boolean;
  is_duplicate: boolean;
  data: Record<string, unknown>;
  pii_redacted_text: string;
  pii_count: number;
  issues: ValidationIssue[];
};

export type IngestionQualityReport = {
  total_rows: number;
  valid_rows: number;
  invalid_rows: number;
  duplicate_rows: number;
  pii_total_redactions: number;
  data_quality_score: number;
  completeness_breakdown: Record<string, number>;
  issues_summary: Record<string, number>;
  preview_rows: ValidatedRowPreview[];
};

export type ReportUploadItem = {
  source_report_id?: string | null;
  report_type?: string;
  site_id?: string | null;
  site_name?: string | null;
  department?: string | null;
  shift?: string | null;
  equipment_type?: string | null;
  job_type?: string | null;
  raw_text: string;
  reported_at?: string | null;
};

export type IngestionConfirmRequest = {
  rows: ReportUploadItem[];
  source_name?: string;
  default_site_id?: string | null;
};

export type IngestionJobOut = {
  id: string;
  source: string;
  record_count: number;
  processed_count: number;
  status: "PENDING" | "IN_PROGRESS" | "COMPLETED" | "FAILED" | string;
  error_log?: Array<Record<string, unknown>> | null;
  created_at: string;
  completed_at?: string | null;
};

export const api = {
  kpis: () => request<{ total_reports: number; sif_flagged: number; sif_rate: number; avg_confidence: number; queue_size: number }>("/v1/dashboard/kpis"),
  sites: () => request<Array<{ id: string; name: string; region: string }>>("/v1/dashboard/sites"),
  density: (group_by = "site") =>
    request<Array<{ group_label: string; sif_count: number; total_count: number; sif_rate: number }>>(
      `/v1/dashboard/sif-density?group_by=${group_by}`,
    ),
  lsr: () =>
    request<Array<{ rule_id?: string; rule_name?: string; lsr_category: string; count: number }>>(
      "/v1/dashboard/lsr-distribution",
    ),
  lsrRules: () => request<LsrRuleMetadata[]>("/v1/lsr-rules"),
  trend: () => request<Array<{ period: string; sif_count: number; total_count: number }>>("/v1/dashboard/trend?interval=week"),
  reports: (params: Record<string, string | number | boolean | undefined>) => {
    const q = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== "" && v !== "all") q.set(k, String(v));
    });
    return request<{ total: number; page: number; page_size: number; items: ReportSummary[] }>(`/v1/reports?${q}`);
  },
  report: (id: string) => request<ReportDetail>(`/v1/reports/${id}`),
  clusters: () => request<Cluster[]>("/v1/clusters"),
  cluster: (id: string) => request<Cluster & { member_reports: ReportSummary[] }>(`/v1/clusters/${id}`),
  feedback: (body: Record<string, unknown>) =>
    request("/v1/feedback", { method: "POST", body: JSON.stringify(body) }),
  users: () => request<Array<{ id: string; username: string; role: Role; site_scope: string[]; is_active: boolean; email?: string }>>("/v1/admin/users"),
  createUser: (body: Record<string, unknown>) =>
    request("/v1/admin/users", { method: "POST", body: JSON.stringify(body) }),
  audit: () => request<Array<{ id: string; user_id: string | null; action_type: string; entity_type: string; entity_id: string | null; created_at: string }>>("/v1/admin/audit-log"),
  trainingRuns: () =>
    request<Array<{ id: string; model_version: string; feedback_count: number; metrics_before: Record<string, number>; metrics_after: Record<string, number>; created_at: string }>>(
      "/v1/admin/training-runs",
    ),
  createTrainingRun: () => request<{ model_version: string }>("/v1/admin/training-runs", { method: "POST" }),
  prioritySummary: (site_id?: string) =>
    request<PrioritySummaryRow[]>(`/v1/dashboard/priority-summary${site_id ? `?site_id=${site_id}` : ""}`),
  priorityConfig: () => request<Record<string, unknown>>("/v1/admin/priority-config"),
  reportRecommendations: (reportId: string) =>
    request<Recommendation[]>(`/v1/reports/${reportId}/recommendations`),
  acceptRecommendation: (id: string) =>
    request<Recommendation>(`/v1/recommendations/${id}/accept`, { method: "POST" }),
  editRecommendation: (id: string, body: { edited_title?: string; edited_action: string; reason?: string }) =>
    request<Recommendation>(`/v1/recommendations/${id}/edit`, { method: "POST", body: JSON.stringify(body) }),
  rejectRecommendation: (id: string, reason: string) =>
    request<Recommendation>(`/v1/recommendations/${id}/reject`, { method: "POST", body: JSON.stringify({ reason }) }),
  implementRecommendation: (id: string, body: { assigned_owner?: string; due_date?: string; resolution_notes?: string }) =>
    request<Recommendation>(`/v1/recommendations/${id}/implement`, { method: "POST", body: JSON.stringify(body) }),
  resolveRecommendation: (id: string, body: { resolution_notes?: string }) =>
    request<Recommendation>(`/v1/recommendations/${id}/resolve`, { method: "POST", body: JSON.stringify(body) }),
  clusterRecommendations: (clusterId: string) =>
    request<Recommendation[]>(`/v1/clusters/${clusterId}/recommendations`),
  recommendedFocusAreas: () =>
    request<ExecutiveFocusArea[]>("/v1/dashboard/recommended-focus-areas"),
  
  // Ingestion API
  validateIngestionFile: async (file: File) => {
    const formData = new FormData();
    formData.append("file", file);
    const token = getToken();
    const headers: Record<string, string> = {};
    if (token) headers["Authorization"] = `Bearer ${token}`;
    const res = await fetch("/v1/ingestion/validate-file", {
      method: "POST",
      body: formData,
      headers,
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || "Validation failed");
    }
    return res.json() as Promise<IngestionQualityReport>;
  },
  validateIngestionJson: (rows: ReportUploadItem[]) =>
    request<IngestionQualityReport>("/v1/ingestion/validate-json", {
      method: "POST",
      body: JSON.stringify(rows),
    }),
  confirmIngestion: (body: IngestionConfirmRequest) =>
    request<IngestionJobOut>("/v1/ingestion/confirm", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  ingestionJobs: () => request<IngestionJobOut[]>("/v1/ingestion/jobs"),
  ingestionJobStatus: (id: string) => request<IngestionJobOut>(`/v1/ingestion/jobs/${id}`),

  // Lifecycle & HSE Review API
  confirmReport: (reportId: string, body: { notes?: string }) =>
    request<ReportDetail>(`/v1/reports/${reportId}/confirm`, { method: "POST", body: JSON.stringify(body) }),
  overrideReport: (reportId: string, body: { final_sif_label: boolean; reason: string; notes?: string }) =>
    request<ReportDetail>(`/v1/reports/${reportId}/override`, { method: "POST", body: JSON.stringify(body) }),
  lsrReview: (reportId: string, body: { selected_rule_ids: string[]; reason?: string }) =>
    request<ReportDetail>(`/v1/reports/${reportId}/lsr-review`, { method: "POST", body: JSON.stringify(body) }),
  precursorReview: (reportId: string, body: { activity?: string; location_asset?: string; barrier_failure?: string; comment?: string }) =>
    request<ReportDetail>(`/v1/reports/${reportId}/precursor-review`, { method: "POST", body: JSON.stringify(body) }),
  priorityReview: (reportId: string, body: { priority_tier: string; reason: string }) =>
    request<ReportDetail>(`/v1/reports/${reportId}/priority-review`, { method: "POST", body: JSON.stringify(body) }),
  resolveReport: (reportId: string, body: { resolution_notes: string; evidence_reference?: string }) =>
    request<ReportDetail>(`/v1/reports/${reportId}/resolve`, { method: "POST", body: JSON.stringify(body) }),
  reopenReport: (reportId: string, body: { reason: string }) =>
    request<ReportDetail>(`/v1/reports/${reportId}/reopen`, { method: "POST", body: JSON.stringify(body) }),
  reportTimeline: (reportId: string) =>
    request<TimelineEventOut[]>(`/v1/reports/${reportId}/timeline`),
  lifecycleKpis: (site_id?: string) =>
    request<LifecycleKpiOut>(`/v1/dashboard/lifecycle-kpis${site_id ? `?site_id=${site_id}` : ""}`),
  agreementAnalytics: () =>
    request<AgreementAnalyticsOut>("/v1/dashboard/agreement-analytics"),

  // Prompt 11: Model Monitoring & Safety Effectiveness API
  modelHealth: () => request<ModelHealthOut>("/v1/dashboard/model-health"),
  errorAnalysis: () => request<ErrorAnalysisOut>("/v1/dashboard/error-analysis"),
  modelDrift: () => request<ModelDriftOut>("/v1/dashboard/model-drift"),
  interventionEffectiveness: () => request<InterventionEffectivenessOut>("/v1/dashboard/intervention-effectiveness"),

  // Task 2: Human-in-the-Loop SIF Labelling Workflow
  submitLabelReview: (reportId: string, body: { label: "SIF" | "NON_SIF" | "UNCERTAIN"; reason: string; notes?: string }) =>
    request<ReportDetail>(`/v1/reports/${reportId}/label-review`, { method: "POST", body: JSON.stringify(body) }),
  reportLabelHistory: (reportId: string) =>
    request<ReportLabelHistoryOut>(`/v1/reports/${reportId}/label-history`),
  reviewerAgreement: () =>
    request<ReviewerAgreementSummaryOut>("/v1/reports/reviewer-agreement"),
};

