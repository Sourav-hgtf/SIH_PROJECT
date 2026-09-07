from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, EmailStr, Field


Role = Literal["analyst", "site_manager", "leadership", "admin"]
ReportType = Literal["ua_uc", "near_miss", "incident"]
FeedbackType = Literal["confirm_sif", "override_sif", "adjust_lsr"]
TagSource = Literal["rule", "model", "analyst"]


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    role: Role
    username: str
    user_id: str


class PhraseWeight(BaseModel):
    phrase: str
    weight: float


class LsrEvidenceItem(BaseModel):
    text: str
    type: str = "phrase"


class LsrTagOut(BaseModel):
    rule_id: str | None = None
    rule_name: str | None = None
    lsr_category: str
    confidence: float
    source: TagSource
    evidence: list[LsrEvidenceItem] = Field(default_factory=list)


class LsrRuleMetadataOut(BaseModel):
    rule_id: str
    name: str
    short_name: str
    description: str
    related_energy_types: list[str] = Field(default_factory=list)
    related_exposure_types: list[str] = Field(default_factory=list)
    related_barrier_types: list[str] = Field(default_factory=list)


class ReportCreate(BaseModel):
    source_report_id: str
    report_type: ReportType
    site_id: str
    department: str | None = None
    shift: str | None = None
    equipment_type: str | None = None
    job_type: str | None = None
    raw_text: str
    reported_at: datetime


from app.priority.schemas import PriorityBreakdown, PriorityComponent, PriorityOut, PrioritySummaryRow, PriorityTier


class ReportSummary(BaseModel):
    id: str
    report_type: str
    site_id: str
    site_name: str | None = None
    department: str | None = None
    reported_at: datetime
    sif_label: bool | None = None
    sif_probability: float | None = None
    lifecycle_status: str = "AI_ANALYZED"
    final_sif_label: bool | None = None
    final_priority: str | None = None
    lsr_tags: list[LsrTagOut] = Field(default_factory=list)
    excerpt: str | None = None
    priority: PriorityOut | None = None
    predicted_sif: bool | None = None
    human_label: str = "UNLABELED"
    validated_label: str | None = None
    label_source: str = "UNLABELED"
    validation_status: str = "UNLABELED"
    data_type: str = "synthetic"


class LabelReviewIn(BaseModel):
    label: str  # "SIF", "NON_SIF", "UNCERTAIN"
    reason: str
    notes: str | None = None


class LabelReviewOut(BaseModel):
    id: str
    report_id: str
    reviewer_id: str
    reviewer_username: str | None = None
    reviewer_role: str | None = None
    label: str
    reason: str
    notes: str | None = None
    review_version: int
    created_at: datetime


class ReportLabelHistoryOut(BaseModel):
    report_id: str
    predicted_sif: bool | None = None
    human_label: str
    validated_label: str | None = None
    label_source: str
    validation_status: str
    total_reviews: int
    unique_reviewers_count: int
    distinct_labels: list[str] = Field(default_factory=list)
    is_consensus_validated: bool
    has_disagreement: bool
    reviews: list[LabelReviewOut] = Field(default_factory=list)


class ReviewerAgreementSummaryOut(BaseModel):
    multi_reviewed_reports: int
    total_comparison_pairs: int
    consensus_agreements: int
    disagreements: int
    cohens_kappa: float
    observed_agreement: float
    expected_agreement: float
    sample_size: int
    interpretation: str


class ReportReviewOut(BaseModel):
    id: str
    report_id: str
    user_id: str | None = None
    username: str | None = None
    decision: str
    final_sif_label: bool
    reason: str
    notes: str | None = None
    ai_sif_label: bool
    ai_sif_probability: float
    ai_model_version: str
    final_priority: str | None = None
    priority_reason: str | None = None
    created_at: datetime
    updated_at: datetime


class ReportDetail(ReportSummary):
    raw_text_redacted: str
    shift: str | None = None
    equipment_type: str | None = None
    job_type: str | None = None
    contributing_phrases: list[PhraseWeight] = Field(default_factory=list)
    model_version: str | None = None
    classified_at: datetime | None = None
    cluster_id: str | None = None
    resolution_notes: str | None = None
    resolved_at: datetime | None = None
    features: dict[str, Any] = Field(default_factory=dict)
    feedback_history: list[dict[str, Any]] = Field(default_factory=list)
    review: ReportReviewOut | None = None
    label_reviews: list[LabelReviewOut] = Field(default_factory=list)
    precursor_triples: list[dict[str, Any]] = Field(default_factory=list)



class SifClassificationOut(BaseModel):
    report_id: str
    sif_probability: float
    sif_label: bool
    model_version: str
    contributing_phrases: list[PhraseWeight]
    classified_at: datetime


class PrecursorClusterOut(BaseModel):
    id: str
    representative_activity: str
    representative_location: str
    representative_barrier_failure: str
    cluster_size: int
    trend_status: str
    first_seen_at: datetime | None = None
    last_updated_at: datetime | None = None
    priority: PriorityOut | None = None


class PrecursorClusterDetail(PrecursorClusterOut):
    member_reports: list[ReportSummary]


class DensityRow(BaseModel):
    group_label: str
    sif_count: int
    total_count: int
    sif_rate: float


class LsrDistributionRow(BaseModel):
    rule_id: str | None = None
    rule_name: str | None = None
    lsr_category: str
    count: int


class TrendRow(BaseModel):
    period: str
    sif_count: int
    total_count: int


class FeedbackCreate(BaseModel):
    report_id: str
    feedback_type: FeedbackType
    new_value: dict[str, Any] | None = None
    comment: str | None = None


class FeedbackRecord(FeedbackCreate):
    id: str
    user_id: str
    created_at: datetime


class UserOut(BaseModel):
    id: str
    username: str
    role: Role
    site_scope: list[str] = Field(default_factory=list)
    email: str | None = None
    is_active: bool


class UserCreate(BaseModel):
    username: str
    password: str
    role: Role
    site_scope: list[str] = Field(default_factory=list)
    email: str | None = None


class AuditLogEntry(BaseModel):
    id: str
    user_id: str | None
    action_type: str
    entity_type: str
    entity_id: str | None
    before_value: dict[str, Any] | None = None
    after_value: dict[str, Any] | None = None
    created_at: datetime


class PaginatedReports(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[ReportSummary]


class SiteOut(BaseModel):
    id: str
    name: str
    region: str


class ModelTrainingRunOut(BaseModel):
    id: str
    model_version: str
    feedback_count: int
    metrics_before: dict[str, Any]
    metrics_after: dict[str, Any]
    created_at: datetime


class ReportUploadItem(BaseModel):
    source_report_id: str | None = None
    report_type: str = "near_miss"
    site_id: str | None = None
    site_name: str | None = None
    department: str | None = None
    shift: str | None = None
    equipment_type: str | None = None
    job_type: str | None = None
    raw_text: str
    reported_at: str | datetime | None = None


class ValidationIssue(BaseModel):
    field: str
    severity: Literal["error", "warning", "info"]
    message: str


class ValidatedRowPreview(BaseModel):
    row_index: int
    is_valid: bool
    is_duplicate: bool
    data: dict[str, Any]
    pii_redacted_text: str
    pii_count: int
    issues: list[ValidationIssue] = Field(default_factory=list)


class IngestionQualityReport(BaseModel):
    total_rows: int
    valid_rows: int
    invalid_rows: int
    duplicate_rows: int
    pii_total_redactions: int
    data_quality_score: float  # 0 to 100
    completeness_breakdown: dict[str, float]  # Percentage complete for each field
    issues_summary: dict[str, int]
    preview_rows: list[ValidatedRowPreview]


class IngestionConfirmRequest(BaseModel):
    rows: list[ReportUploadItem]
    source_name: str = "User Upload"
    default_site_id: str | None = None


class IngestionJobOut(BaseModel):
    id: str
    source: str
    record_count: int
    processed_count: int
    status: str
    error_log: list[Any] | None = None
    created_at: datetime
    completed_at: datetime | None = None


class ReportConfirmIn(BaseModel):
    notes: str | None = None


class ReportOverrideIn(BaseModel):
    final_sif_label: bool
    reason: str
    notes: str | None = None


class LsrReviewIn(BaseModel):
    selected_rule_ids: list[str] = Field(default_factory=list)
    reason: str | None = None


class PrecursorReviewIn(BaseModel):
    activity: str
    location_asset: str
    barrier_failure: str
    comment: str | None = None


class PriorityAdjustmentIn(BaseModel):
    priority_tier: str
    reason: str


class CaseResolutionIn(BaseModel):
    resolution_notes: str
    completion_date: str | datetime | None = None
    evidence_reference: str | None = None


class CaseReopenIn(BaseModel):
    reason: str


class TimelineEventOut(BaseModel):
    id: str
    timestamp: datetime
    event_type: str
    actor: str | None = None
    title: str
    description: str
    badge_type: str = "info"
    metadata: dict[str, Any] = Field(default_factory=dict)


class LifecycleKpiOut(BaseModel):
    pending_review: int
    confirmed_sif: int
    ai_overrides: int
    open_actions: int
    overdue_actions: int
    resolved_cases: int
    reopened_cases: int
    agreement_rate: float


class AgreementAnalyticsOut(BaseModel):
    total_reviewed: int
    agreement_count: int
    agreement_rate: float
    confirm_count: int
    confirm_rate: float
    override_count: int
    override_rate: float
    false_positives: int
    false_negatives: int
    reason_breakdown: dict[str, int]


# --- Prompt 11: Model Monitoring & Analytics Schemas ---

class ConfusionMatrixOut(BaseModel):
    tp: int
    tn: int
    fp: int
    fn: int


class ModelHealthOut(BaseModel):
    total_reviewed: int
    insufficient_data: bool
    agreement_rate: float
    cohen_kappa: float
    confusion_matrix: ConfusionMatrixOut
    false_positive_rate: float
    false_negative_rate: float
    agreement_by_model_version: dict[str, float]


class ErrorReportItem(BaseModel):
    report_id: str
    source_report_id: str
    excerpt: str
    ai_sif_label: bool
    human_sif_label: bool
    model_version: str
    site_name: str | None = None
    reviewed_at: str | None = None


class ErrorAnalysisOut(BaseModel):
    insufficient_data: bool
    false_positives: list[ErrorReportItem]
    false_negatives: list[ErrorReportItem]
    errors_by_model_version: dict[str, dict[str, int]]
    errors_by_site: dict[str, dict[str, int]]
    errors_by_lsr: dict[str, dict[str, int]]


class ModelVersionMetrics(BaseModel):
    model_version: str
    created_at: str | None = None
    feedback_count: int = 0
    precision: float | None = None
    recall: float | None = None
    f1: float | None = None
    roc_auc: float | None = None
    accuracy: float | None = None
    sample_size: int | None = None


class ModelDriftOut(BaseModel):
    versions: list[ModelVersionMetrics]
    has_regression: bool


class InterventionEffectivenessOut(BaseModel):
    insufficient_data: bool
    total_recommendations: int
    accepted: int
    rejected: int
    implemented: int
    resolved: int
    acceptance_rate: float
    implementation_rate: float
    resolution_rate: float
    mean_days_to_resolution: float | None = None
    monthly_resolution_trend: list[dict[str, Any]]
    sif_rate_before_intervention: float | None = None
    sif_rate_after_intervention: float | None = None


class AgreementTrendRow(BaseModel):
    month: str
    total_reviews: int
    agreement_rate: float
    false_positive_rate: float
    false_negative_rate: float


