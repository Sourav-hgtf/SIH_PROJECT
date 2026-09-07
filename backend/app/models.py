import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    return str(uuid.uuid4())


class Site(Base):
    __tablename__ = "sites"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    region: Mapped[str] = mapped_column(String(100), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    reports = relationship("Report", back_populates="site")


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    username: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(50), nullable=False)
    site_scope: Mapped[list | None] = mapped_column(JSON, default=list)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    source_report_id: Mapped[str] = mapped_column(String(100), nullable=False)
    report_type: Mapped[str] = mapped_column(String(50), nullable=False)
    site_id: Mapped[str] = mapped_column(String(36), ForeignKey("sites.id"), nullable=False)
    department: Mapped[str | None] = mapped_column(String(100), nullable=True)
    shift: Mapped[str | None] = mapped_column(String(50), nullable=True)
    equipment_type: Mapped[str | None] = mapped_column(String(150), nullable=True)
    job_type: Mapped[str | None] = mapped_column(String(150), nullable=True)
    raw_text_redacted: Mapped[str] = mapped_column(Text, nullable=False)
    processed_text: Mapped[str] = mapped_column(Text, default="")
    reported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    vector_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    lifecycle_status: Mapped[str] = mapped_column(String(50), default="AI_ANALYZED")
    data_type: Mapped[str] = mapped_column(String(20), default="synthetic")
    human_label: Mapped[str] = mapped_column(String(20), default="UNLABELED")  # SIF, NON_SIF, UNCERTAIN, UNLABELED
    validated_label: Mapped[str | None] = mapped_column(String(20), nullable=True)  # SIF, NON_SIF, UNCERTAIN, None
    label_source: Mapped[str] = mapped_column(String(50), default="UNLABELED")  # UNLABELED, HEURISTIC_PREDICTION, HUMAN_REVIEW, CONSENSUS_VALIDATED, SENIOR_HSE_OVERRIDE
    validation_status: Mapped[str] = mapped_column(String(50), default="UNLABELED")  # UNLABELED, PENDING_CONSENSUS, DISAGREEMENT, VALIDATED
    final_sif_label: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    final_priority: Mapped[str | None] = mapped_column(String(20), nullable=True)
    resolution_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    site = relationship("Site", back_populates="reports")
    classification = relationship("SifClassification", back_populates="report", uselist=False)
    lsr_tags = relationship("LsrTag", back_populates="report")
    triples = relationship("PrecursorTriple", back_populates="report")
    feedback = relationship("AnalystFeedback", back_populates="report")
    recommendations = relationship("Recommendation", back_populates="report")
    reviews = relationship("ReportReview", back_populates="report", cascade="all, delete-orphan")
    precursor_feedback = relationship("PrecursorFeedback", back_populates="report", cascade="all, delete-orphan")
    label_reviews = relationship("LabelReview", back_populates="report", cascade="all, delete-orphan", order_by="LabelReview.created_at.desc()")

    @property
    def predicted_sif(self) -> bool | None:
        """Heuristic or ML model predicted SIF potential (separate from human-validated label)."""
        return self.classification.sif_label if self.classification else None


class SifClassification(Base):
    __tablename__ = "sif_classifications"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    report_id: Mapped[str] = mapped_column(String(36), ForeignKey("reports.id"), unique=True)
    sif_probability: Mapped[float] = mapped_column(Float, nullable=False)
    sif_label: Mapped[bool] = mapped_column(Boolean, nullable=False)
    model_version: Mapped[str] = mapped_column(String(50), default="heuristic-v1")
    contributing_phrases: Mapped[list] = mapped_column(JSON, default=list)
    features: Mapped[dict] = mapped_column(JSON, default=dict)
    classified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    report = relationship("Report", back_populates="classification")


class LsrTag(Base):
    __tablename__ = "lsr_tags"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    report_id: Mapped[str] = mapped_column(String(36), ForeignKey("reports.id"))
    lsr_category: Mapped[str] = mapped_column(String(100), nullable=False)
    rule_id: Mapped[str | None] = mapped_column(String(20), nullable=True)
    rule_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    evidence: Mapped[list | None] = mapped_column(JSON, default=list, nullable=True)
    tagged_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    report = relationship("Report", back_populates="lsr_tags")


class PrecursorTriple(Base):
    __tablename__ = "precursor_triples"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    report_id: Mapped[str] = mapped_column(String(36), ForeignKey("reports.id"))
    activity: Mapped[str] = mapped_column(String(255), nullable=False)
    location_asset: Mapped[str] = mapped_column(String(255), nullable=False)
    barrier_failure: Mapped[str] = mapped_column(String(255), nullable=False)
    vector_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    extracted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    report = relationship("Report", back_populates="triples")


class PrecursorCluster(Base):
    __tablename__ = "precursor_clusters"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    representative_activity: Mapped[str] = mapped_column(String(255), nullable=False)
    representative_location: Mapped[str] = mapped_column(String(255), nullable=False)
    representative_barrier_failure: Mapped[str] = mapped_column(String(255), nullable=False)
    cluster_size: Mapped[int] = mapped_column(Integer, default=0)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    trend_status: Mapped[str] = mapped_column(String(20), default="stable")

    members = relationship("ClusterMember", back_populates="cluster")
    recommendations = relationship("Recommendation", back_populates="cluster")


class ClusterMember(Base):
    __tablename__ = "cluster_members"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    cluster_id: Mapped[str] = mapped_column(String(36), ForeignKey("precursor_clusters.id"))
    triple_id: Mapped[str] = mapped_column(String(36), ForeignKey("precursor_triples.id"))
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    cluster = relationship("PrecursorCluster", back_populates="members")


class AnalystFeedback(Base):
    __tablename__ = "analyst_feedback"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    report_id: Mapped[str] = mapped_column(String(36), ForeignKey("reports.id"))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    feedback_type: Mapped[str] = mapped_column(String(50), nullable=False)
    previous_value: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    new_value: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    report = relationship("Report", back_populates="feedback")


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    action_type: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    before_value: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    after_value: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class IngestionRun(Base):
    __tablename__ = "ingestion_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    source: Mapped[str] = mapped_column(String(255), nullable=False)
    record_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(50), default="PENDING")
    processed_count: Mapped[int] = mapped_column(Integer, default=0)
    error_log: Mapped[list | None] = mapped_column(JSON, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ModelTrainingRun(Base):
    """Immutable record of an active-learning calibration run."""

    __tablename__ = "model_training_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    model_version: Mapped[str] = mapped_column(String(80), nullable=False)
    artifact_path: Mapped[str] = mapped_column(String(500), nullable=False)
    feedback_count: Mapped[int] = mapped_column(Integer, default=0)
    metrics_before: Mapped[dict] = mapped_column(JSON, default=dict)
    metrics_after: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Recommendation(Base):
    __tablename__ = "recommendations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    report_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("reports.id"), nullable=True)
    cluster_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("precursor_clusters.id"), nullable=True)
    site_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("sites.id"), nullable=True)
    activity: Mapped[str | None] = mapped_column(String(255), nullable=True)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    priority: Mapped[str] = mapped_column(String(20), nullable=False)
    evidence: Mapped[list] = mapped_column(JSON, default=list)
    source_signals: Mapped[dict] = mapped_column(JSON, default=dict)
    rationale: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(30), default="PENDING_REVIEW")
    version: Mapped[str] = mapped_column(String(50), default="recommendations-v1")
    assigned_owner: Mapped[str | None] = mapped_column(String(100), nullable=True)
    due_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolution_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    report = relationship("Report", back_populates="recommendations")
    cluster = relationship("PrecursorCluster", back_populates="recommendations")
    site = relationship("Site")
    feedback_records = relationship("RecommendationFeedback", back_populates="recommendation", cascade="all, delete-orphan")


class RecommendationFeedback(Base):
    __tablename__ = "recommendation_feedback"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    recommendation_id: Mapped[str] = mapped_column(String(36), ForeignKey("recommendations.id"), nullable=False)
    user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    decision: Mapped[str] = mapped_column(String(30), nullable=False)
    original_text: Mapped[str] = mapped_column(Text, nullable=False)
    edited_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    recommendation = relationship("Recommendation", back_populates="feedback_records")
    user = relationship("User")


class ReportReview(Base):
    __tablename__ = "report_reviews"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    report_id: Mapped[str] = mapped_column(String(36), ForeignKey("reports.id"), nullable=False)
    user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    decision: Mapped[str] = mapped_column(String(50), nullable=False)  # CONFIRMED, OVERRIDDEN, REJECTED
    final_sif_label: Mapped[bool] = mapped_column(Boolean, nullable=False)
    reason: Mapped[str] = mapped_column(String(255), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    ai_sif_label: Mapped[bool] = mapped_column(Boolean, nullable=False)
    ai_sif_probability: Mapped[float] = mapped_column(Float, nullable=False)
    ai_model_version: Mapped[str] = mapped_column(String(50), default="heuristic-v1")
    final_priority: Mapped[str | None] = mapped_column(String(20), nullable=True)
    priority_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    report = relationship("Report", back_populates="reviews")
    user = relationship("User")


class PrecursorFeedback(Base):
    __tablename__ = "precursor_feedback"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    report_id: Mapped[str] = mapped_column(String(36), ForeignKey("reports.id"), nullable=False)
    user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    original_activity: Mapped[str] = mapped_column(String(255), nullable=False)
    corrected_activity: Mapped[str] = mapped_column(String(255), nullable=False)
    original_barrier_failure: Mapped[str] = mapped_column(String(255), nullable=False)
    corrected_barrier_failure: Mapped[str] = mapped_column(String(255), nullable=False)
    original_location: Mapped[str] = mapped_column(String(255), default="")
    corrected_location: Mapped[str] = mapped_column(String(255), default="")
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    report = relationship("Report", back_populates="precursor_feedback")
    user = relationship("User")


class LabelReview(Base):
    """Immutable human-in-the-loop review record for SIF potential determination.

    Supports multiple independent reviewers per incident, disagreement tracking,
    and consensus validation without ever overwriting historical reviews.
    """

    __tablename__ = "label_reviews"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    report_id: Mapped[str] = mapped_column(String(36), ForeignKey("reports.id"), nullable=False)
    reviewer_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    label: Mapped[str] = mapped_column(String(20), nullable=False)  # SIF, NON_SIF, UNCERTAIN
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    review_version: Mapped[int] = mapped_column(Integer, default=1)
    reviewer_role: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    report = relationship("Report", back_populates="label_reviews")
    reviewer = relationship("User")


