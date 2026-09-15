"""Phase 10 artifact-backed model audit dashboard contracts."""

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import create_token
from app.database import Base, get_db
from app.main import app
from app.models import User


def test_model_evaluation_dashboard_is_artifact_backed_and_admin_restricted():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    db.add_all([
        User(id="evaluation-admin", username="evaluation-admin", password_hash="x", role="admin"),
        User(id="evaluation-analyst", username="evaluation-analyst", password_hash="x", role="analyst"),
    ])
    db.commit()
    db.close()

    def override_db():
        session = Session()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_db
    admin_headers = {"Authorization": f"Bearer {create_token('evaluation-admin', 'access', 60)}"}
    analyst_headers = {"Authorization": f"Bearer {create_token('evaluation-analyst', 'access', 60)}"}
    try:
        with TestClient(app) as client:
            response = client.get("/v1/admin/model-evaluation", headers=admin_headers)
            assert response.status_code == 200
            payload = response.json()
            assert payload["artifact_status"] == "AVAILABLE"
            by_name = {record["model_name"]: record for record in payload["records"]}
            assert {"Baseline", "TF-IDF model", "Semantic model"}.issubset(by_name)
            tfidf = by_name["TF-IDF model"]
            assert all(key in tfidf["metrics"] for key in ("precision", "recall", "f1", "accuracy", "roc_auc", "pr_auc", "specificity", "brier_score"))
            assert set(tfidf["confusion_matrix"]) >= {"tn", "fp", "fn", "tp"}
            assert tfidf["false_positives"] == tfidf["confusion_matrix"]["fp"]
            assert tfidf["false_negatives"] == tfidf["confusion_matrix"]["fn"]

            # A syntactically valid token for a non-admin must not expose artifacts.
            forbidden = client.get("/v1/admin/model-evaluation", headers=analyst_headers)
            assert forbidden.status_code == 403
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)
