from __future__ import annotations

import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

ACTIVITY_PATTERNS = [
    (r"\bwelding\b", "hot work / welding"),
    (r"\bgrinding\b", "grinding"),
    (r"\blifting\b|\bcrane\b|\brigging\b", "mechanical lifting"),
    (r"\bconfined space\b|\btank entry\b|\bvessel entry\b", "confined space entry"),
    (r"\bworking at height\b|\bscaffold", "working at height"),
    (r"\bisolat", "energy isolation"),
    (r"\bdriving\b|\bvehicle\b|\bconvoy\b", "driving / transport"),
    (r"\bmaintenance\b", "maintenance"),
    (r"\bdrilling\b|\btrip(ping)? pipe\b", "drilling operations"),
    (r"\bexcavation\b", "excavation"),
]

LOCATION_PATTERNS = [
    (r"\bwellhead\b", "wellhead"),
    (r"\brig floor\b", "rig floor"),
    (r"\bmud tank\b", "mud tank"),
    (r"\bpipeline\b", "pipeline ROW"),
    (r"\bworkshop\b", "workshop"),
    (r"\bwarehouse\b", "warehouse"),
    (r"\bcellar\b", "well cellar"),
    (r"\btank farm\b|\bstorage tank\b", "tank farm"),
    (r"\belectrical panel\b|\bMCC\b", "electrical panel / MCC"),
    (r"\bflare\b", "flare area"),
    (r"\bscaffolds?\b", "scaffold platform"),
]

BARRIER_PATTERNS = [
    (r"\bno permit\b|\bpermit (expired|missing)\b", "missing / expired PTW"),
    (r"\bnot isolated\b|\bLOTO not\b|\block-out tag-out not\b", "failed energy isolation"),
    (r"\bno harness\b|\bmissing harness\b", "missing fall protection"),
    (r"\bno gas test\b", "atmosphere not verified"),
    (r"\bbypass", "safety control bypassed"),
    (r"\bmissing attendant\b", "no confined-space attendant"),
    (r"\bno fire watch\b|\bfire watch missing\b", "no fire watch"),
    (r"\bdamaged sling\b|\bSWL exceeded\b", "lifting barrier failed"),
    (r"\bno exclusion zone\b|\bline of fire\b", "line-of-fire control missing"),
    (r"\bguard removed\b|\binterlock defeated\b", "machine guarding defeated"),
]


def _first_match(patterns: list[tuple[str, str]], text: str, default: str) -> str:
    for pat, label in patterns:
        if re.search(pat, text, re.IGNORECASE):
            return label
    return default


def extract_triple(text: str, equipment: str | None = None, job_type: str | None = None) -> dict:
    activity = _first_match(ACTIVITY_PATTERNS, text, job_type or "unspecified activity")
    location = _first_match(LOCATION_PATTERNS, text, equipment or "unspecified location")
    barrier = _first_match(BARRIER_PATTERNS, text, "barrier not identified")
    return {
        "activity": activity,
        "location_asset": location,
        "barrier_failure": barrier,
    }


def cluster_key(triple: dict) -> str:
    return f"{triple['activity'].lower()}|{triple['location_asset'].lower()}|{triple['barrier_failure'].lower()}"


def assign_trend(member_dates: list[datetime]) -> str:
    if not member_dates:
        return "stable"
    now = datetime.now(timezone.utc)
    # SQLite does not preserve timezone information on round-trip, while
    # PostgreSQL commonly returns aware values. Normalize both to UTC so the
    # same clustering code works for the prototype and production database.
    normalized = [d.replace(tzinfo=timezone.utc) if d.tzinfo is None else d.astimezone(timezone.utc) for d in member_dates]
    recent = sum(1 for d in normalized if d >= now - timedelta(days=30))
    older = sum(1 for d in normalized if now - timedelta(days=60) <= d < now - timedelta(days=30))
    if recent > older + 1:
        return "growing"
    if recent + 1 < older:
        return "shrinking"
    return "stable"


def group_triples(triples: list[dict]) -> list[dict]:
    buckets: dict[str, list[dict]] = defaultdict(list)
    for item in triples:
        buckets[cluster_key(item)].append(item)
    clusters = []
    for _key, members in buckets.items():
        sample = members[0]
        dates = [m.get("reported_at") for m in members if m.get("reported_at")]
        clusters.append(
            {
                "representative_activity": sample["activity"],
                "representative_location": sample["location_asset"],
                "representative_barrier_failure": sample["barrier_failure"],
                "members": members,
                "cluster_size": len(members),
                "trend_status": assign_trend([d for d in dates if d]),
            }
        )
    clusters.sort(key=lambda c: c["cluster_size"], reverse=True)
    return clusters


def activity_counter(triples: list[dict]) -> Counter:
    return Counter(t["activity"] for t in triples)
