from datetime import datetime, timedelta, timezone
from random import Random

from sqlalchemy.orm import Session

from app.auth import hash_password
from app.models import Site, User
from app.services import ingest_and_process, log_ingestion_run, rebuild_clusters

SITES = [
    ("Duliajan GCS", "Assam"),
    ("Digboi Refinery Area", "Assam"),
    ("Moran Field", "Assam"),
    ("Jorhat Asset", "Assam"),
    ("Baghjan Field", "Assam"),
]

USERS = [
    ("analyst", "analyst123", "analyst", "hse.analyst@oilindia.example"),
    ("manager", "manager123", "site_manager", "site.manager@oilindia.example"),
    ("leadership", "leader123", "leadership", "hsse.lead@oilindia.example"),
    ("admin", "admin123", "admin", "admin@oilindia.example"),
]


def _dt(days_ago: int, hour: int = 10) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=days_ago, hours=24 - hour)


TEMPLATES = [
    {
        "type": "near_miss",
        "dept": "Well Services",
        "shift": "Day",
        "equip": "Wellhead",
        "job": "Well intervention",
        "text": (
            "Near miss at wellhead: crew began work without energy isolation. "
            "LOTO not applied on the hydraulic circuit and residual pressure remained. "
            "Amit Sharma (EMP-44102, +91 9876543210) was standing in the line of fire "
            "when a hose whipped. PTW was expired."
        ),
    },
    {
        "type": "ua_uc",
        "dept": "Maintenance",
        "shift": "Night",
        "equip": "Electrical panel",
        "job": "Electrical isolation",
        "text": (
            "Unsafe act: electrician opened live electrical panel at MCC without isolation certificate. "
            "Interlock defeated with a jumpered switch. High voltage present. "
            "Reported by Rina Das EMPID 88021."
        ),
    },
    {
        "type": "incident",
        "dept": "Drilling",
        "shift": "Day",
        "equip": "Crane",
        "job": "Mechanical lifting",
        "text": (
            "Dropped object near miss during crane lift on rig floor. Damaged sling, SWL exceeded. "
            "Two workers standing under the suspended load. No exclusion zone, tag line not used."
        ),
    },
    {
        "type": "ua_uc",
        "dept": "Production",
        "shift": "Day",
        "equip": "Storage tank",
        "job": "Confined space entry",
        "text": (
            "CSE into storage tank without gas test. Missing attendant. Confined space atmosphere not tested. "
            "H2S possible from residual hydrocarbon. No SCBA staged."
        ),
    },
    {
        "type": "near_miss",
        "dept": "Maintenance",
        "shift": "Day",
        "equip": "Scaffold",
        "job": "Working at height",
        "text": (
            "Working at height on incomplete scaffold platform. No harness worn, missing toe board, "
            "edge protection missing. Worker almost fall from 8m platform at tank farm."
        ),
    },
    {
        "type": "ua_uc",
        "dept": "Production",
        "shift": "Evening",
        "equip": "Pipeline",
        "job": "Hot work",
        "text": (
            "Hot work grinding near hydrocarbon line. Welding without permit, fire watch missing, "
            "gas test not done. Sparks in close proximity to flange leak."
        ),
    },
    {
        "type": "near_miss",
        "dept": "Logistics",
        "shift": "Night",
        "equip": "Crew bus",
        "job": "Driving",
        "text": (
            "Driver speeding on night convoy, no seat belt, mobile phone while driving. "
            "Journey management not followed. Near collision at field gate."
        ),
    },
    {
        "type": "ua_uc",
        "dept": "Maintenance",
        "shift": "Day",
        "equip": "Pump",
        "job": "Maintenance",
        "text": (
            "Temporary modification on ESD bypass left in place. MOC not raised. "
            "Safety control disabled on rotating equipment guard removed."
        ),
    },
    {
        "type": "ua_uc",
        "dept": "HSE",
        "shift": "Day",
        "equip": "Workshop",
        "job": "Housekeeping",
        "text": (
            "Poor housekeeping in workshop. Slippery floor near wash bay and trip hazard from hoses. "
            "Hard hat not worn in designated area. No high energy work underway."
        ),
    },
    {
        "type": "ua_uc",
        "dept": "Drilling",
        "shift": "Day",
        "equip": "Rig floor",
        "job": "PPE observation",
        "text": (
            "Missing gloves and safety boots observation during TBT. PPE reminder issued. "
            "No live equipment interaction at the time."
        ),
    },
    {
        "type": "near_miss",
        "dept": "Well Services",
        "shift": "Night",
        "equip": "Mud tank",
        "job": "Drilling operations",
        "text": (
            "Worker entered mud tank cellar without PTW. Confined space, no gas test, "
            "workers nearby in the drop zone of a hoist."
        ),
    },
    {
        "type": "incident",
        "dept": "Production",
        "shift": "Day",
        "equip": "Wellhead",
        "job": "Energy isolation",
        "text": (
            "Pressurized wellhead isolation failed. Blind missing, residual pressure released. "
            "Crew in line of fire during unbolting. Isolation certificate incomplete."
        ),
    },
]


def seed_if_empty(db: Session) -> None:
    from app.config import settings
    if not settings.demo_mode or settings.app_env.lower() == "production":
        return

    if db.query(User).count() > 0:
        return


    sites: list[Site] = []
    for name, region in SITES:
        site = Site(name=name, region=region)
        db.add(site)
        sites.append(site)
    db.flush()

    duliajan = sites[0].id
    for username, password, role, email in USERS:
        scope = [duliajan] if role in ("analyst", "site_manager") else []
        db.add(
            User(
                username=username,
                password_hash=hash_password(password),
                role=role,
                site_scope=scope,
                email=email,
            )
        )

    rng = Random(7)
    count = 0
    for i in range(72):
        tmpl = TEMPLATES[i % len(TEMPLATES)]
        site = sites[i % len(sites)]
        # Analyst/manager scoped site gets more volume so their dashboards are rich
        if i % 3 == 0:
            site = sites[0]
        jitter = rng.choice(
            [
                "",
                " JSA was not refreshed.",
                " SIMOPS conflict with adjacent crew.",
                " Fatigue reported after 14-hour shift.",
            ]
        )
        ingest_and_process(
            db,
            source_report_id=f"HSSE-{1000 + i}",
            report_type=tmpl["type"],
            site_id=site.id,
            raw_text=tmpl["text"] + jitter,
            reported_at=_dt(days_ago=rng.randint(1, 80), hour=rng.randint(6, 20)),
            department=tmpl["dept"],
            shift=tmpl["shift"],
            equipment_type=tmpl["equip"],
            job_type=tmpl["job"],
        )
        count += 1

    rebuild_clusters(db)
    log_ingestion_run(db, source="synthetic_seed.json", record_count=count)
    db.commit()
