"""AI-Assisted Corrective Action Recommendations package.

Public API:
    generate_report_recommendations(report, db) -> list[RecommendationOut]
    generate_cluster_recommendations(cluster, db) -> list[RecommendationOut]
    generate_executive_focus_areas(db, limit) -> list[ExecutiveFocusAreaOut]
    load_recommendations_config() -> RecommendationsConfig
"""
from .config import RecommendationsConfig, load_recommendations_config
from .engine import (
    generate_cluster_recommendations,
    generate_executive_focus_areas,
    generate_report_recommendations,
)
from .schemas import (
    ExecutiveFocusAreaOut,
    RecommendationActionIn,
    RecommendationEditIn,
    RecommendationFeedbackOut,
    RecommendationOut,
    RecommendationRejectIn,
    RecommendationStatus,
)

__all__ = [
    "ExecutiveFocusAreaOut",
    "RecommendationActionIn",
    "RecommendationEditIn",
    "RecommendationFeedbackOut",
    "RecommendationOut",
    "RecommendationRejectIn",
    "RecommendationStatus",
    "RecommendationsConfig",
    "generate_cluster_recommendations",
    "generate_executive_focus_areas",
    "generate_report_recommendations",
    "load_recommendations_config",
]
