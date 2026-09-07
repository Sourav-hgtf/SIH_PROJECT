from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload

from app.auth import get_current_user, scoped_site_ids
from app.database import get_db
from app.models import ClusterMember, PrecursorCluster, PrecursorTriple, Report, User
from app.priority.engine import score_cluster, score_report
from app.schemas import PrecursorClusterDetail, PrecursorClusterOut, ReportSummary, LsrTagOut

router = APIRouter(tags=["Clusters"])


def _visible_cluster_ids(db: Session, user: User) -> set[str] | None:
    allowed = scoped_site_ids(user)
    if allowed is None:
        return None
    rows = (
        db.query(ClusterMember.cluster_id)
        .join(PrecursorTriple, PrecursorTriple.id == ClusterMember.triple_id)
        .join(Report, Report.id == PrecursorTriple.report_id)
        .filter(Report.site_id.in_(allowed or ["__none__"]))
        .distinct()
        .all()
    )
    return {r[0] for r in rows}


@router.get("/clusters", response_model=list[PrecursorClusterOut])
def list_clusters(
    site_id: str | None = None,
    sort_by: str = Query("priority", pattern="^(size|trend|recent|priority)$"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    q = db.query(PrecursorCluster)
    visible = _visible_cluster_ids(db, user)
    if visible is not None:
        q = q.filter(PrecursorCluster.id.in_(visible or ["__none__"]))
    if site_id:
        ids = (
            db.query(ClusterMember.cluster_id)
            .join(PrecursorTriple, PrecursorTriple.id == ClusterMember.triple_id)
            .join(Report, Report.id == PrecursorTriple.report_id)
            .filter(Report.site_id == site_id)
            .distinct()
        )
        q = q.filter(PrecursorCluster.id.in_(ids))
    if sort_by == "recent":
        q = q.order_by(PrecursorCluster.last_updated_at.desc())
    elif sort_by == "trend":
        q = q.order_by(PrecursorCluster.trend_status.asc(), PrecursorCluster.cluster_size.desc())
    elif sort_by == "size":
        q = q.order_by(PrecursorCluster.cluster_size.desc())

    clusters = q.all()
    results = [
        PrecursorClusterOut(
            id=c.id,
            representative_activity=c.representative_activity,
            representative_location=c.representative_location,
            representative_barrier_failure=c.representative_barrier_failure,
            cluster_size=c.cluster_size,
            trend_status=c.trend_status,
            first_seen_at=c.first_seen_at,
            last_updated_at=c.last_updated_at,
            priority=score_cluster(c, db),
        )
        for c in clusters
    ]

    if sort_by == "priority":
        results.sort(key=lambda x: (x.priority.score if x.priority else 0.0), reverse=True)

    return results


@router.get("/clusters/{cluster_id}", response_model=PrecursorClusterDetail)
def cluster_detail(cluster_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    cluster = db.get(PrecursorCluster, cluster_id)
    if not cluster:
        raise HTTPException(status_code=404, detail="Cluster not found")
    visible = _visible_cluster_ids(db, user)
    if visible is not None and cluster_id not in visible:
        raise HTTPException(status_code=403, detail="Outside site scope")
    members = (
        db.query(Report)
        .join(PrecursorTriple, PrecursorTriple.report_id == Report.id)
        .join(ClusterMember, ClusterMember.triple_id == PrecursorTriple.id)
        .options(
            joinedload(Report.classification),
            joinedload(Report.lsr_tags),
            joinedload(Report.site),
            joinedload(Report.triples),
        )
        .filter(ClusterMember.cluster_id == cluster_id)
        .all()
    )
    allowed = scoped_site_ids(user)
    if allowed is not None:
        members = [r for r in members if r.site_id in allowed]
    summaries = [
        ReportSummary(
            id=r.id,
            report_type=r.report_type,
            site_id=r.site_id,
            site_name=r.site.name if r.site else None,
            department=r.department,
            reported_at=r.reported_at,
            sif_label=r.classification.sif_label if r.classification else None,
            sif_probability=r.classification.sif_probability if r.classification else None,
            lsr_tags=[
                LsrTagOut(lsr_category=t.lsr_category, confidence=t.confidence, source=t.source)  # type: ignore[arg-type]
                for t in r.lsr_tags
            ],
            excerpt=(r.raw_text_redacted or "")[:180],
            priority=score_report(r, db),
        )
        for r in members
    ]
    cluster_priority = score_cluster(cluster, db)
    return PrecursorClusterDetail(
        id=cluster.id,
        representative_activity=cluster.representative_activity,
        representative_location=cluster.representative_location,
        representative_barrier_failure=cluster.representative_barrier_failure,
        cluster_size=len(summaries),
        trend_status=cluster.trend_status,
        first_seen_at=cluster.first_seen_at,
        last_updated_at=cluster.last_updated_at,
        priority=cluster_priority,
        member_reports=summaries,
    )
