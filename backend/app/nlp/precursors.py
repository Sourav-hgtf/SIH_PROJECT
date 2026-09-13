"""SIF Precursor Pattern Extraction Engine.

Extracts meaningful SIF precursor patterns across 6 core dimensions:
1. Activity (Operational task taking place)
2. Location (Physical site/asset; strictly null if not stated in report)
3. Barrier Failure (Compromised, missing, or defeated safeguard)
4. Hazard / Exposure (Physical energy, toxic exposure, or kinetic hazard)
5. Relevant LSR (Canonical 12 IOGP Life-Saving Rule)
6. Evidence Phrase (Direct verbatim substrings supporting the extraction)

Architecture:
  Report Text
       ↓
  Preprocessing (PII Redaction, Normalization)
       ↓
  Concept & Entity Extraction:
    - Explicit regex/rule anchors
    - Local dense semantic cosine similarity (all-MiniLM-L6-v2)
    - Anti-hallucination validation (missing locations stay null)
    - Verbatim evidence span extraction
       ↓
  PrecursorRecord (with confidence & extraction_method)
       ↓
  Graceful fallback to legacy rule extraction if semantic engine unavailable
"""

from __future__ import annotations

import logging
import re
from dataclasses import asdict, dataclass, field
from typing import Any

import numpy as np

from app.nlp.embeddings import extract_embedding, extract_embeddings
from app.nlp.lsr import get_rule_by_id, load_canonical_lsr_rules
from app.nlp.mining import (
    ACTIVITY_PATTERNS as LEGACY_ACTIVITY_PATTERNS,
    BARRIER_PATTERNS as LEGACY_BARRIER_PATTERNS,
    LOCATION_PATTERNS as LEGACY_LOCATION_PATTERNS,
    extract_triple as legacy_extract_triple,
)
from app.nlp.preprocess import preprocess

logger = logging.getLogger(__name__)

# Extraction version identifier
EXTRACTION_VERSION = "hybrid_semantic_v1"
FALLBACK_VERSION = "rule_fallback_v1"

# Semantic similarity threshold for precursor concept matching
PRECURSOR_SEMANTIC_THRESHOLD = 0.50


@dataclass
class PrecursorRecord:
    activity: str | None
    location: str | None
    barrier_failure: str | None
    hazard_exposure: str | None
    relevant_lsr: str | None
    relevant_lsr_id: str | None
    evidence_phrase: str | None
    evidence: dict[str, str | None] = field(default_factory=dict)
    confidence: float = 0.85
    extraction_method: str = EXTRACTION_VERSION
    secondary_activities: list[str] = field(default_factory=list)
    secondary_barriers: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_legacy_triple(self) -> dict[str, str]:
        """Backward compatibility for legacy callers expecting activity/location_asset/barrier_failure."""
        return {
            "activity": self.activity or "unspecified activity",
            "location_asset": self.location or "unspecified location",
            "barrier_failure": self.barrier_failure or "barrier not identified",
        }


# ==============================================================================
# CANONICAL TAXONOMY & EXEMPLAR PHRASES
# ==============================================================================

CANONICAL_ACTIVITIES: list[dict[str, Any]] = [
    {
        "name": "Line dismantling / piping break",
        "lsr_id": "LSR04",
        "patterns": [
            r"\b(dismantl|disassembl|uncoupl|remov|disconnect|break(ing)?)\w*\s+(the\s+)?(pressur\w+|pipe|line|flange|tubing|manifold)",
            r"\bline\s+break(ing)?\b",
            r"\bflange\s+(opening|removal|unbolting)\b",
        ],
        "exemplars": [
            "dismantled the pressurized line",
            "technician uncoupled the pipe",
            "flange disassembly on live manifold",
            "line breaking and pipe removal",
            "loosened bolts on pressurized line",
        ],
    },
    {
        "name": "Hot work / welding",
        "lsr_id": "LSR05",
        "patterns": [
            r"\b(weld(ing)?|torch\s+cut(ting)?|grind(ing)?|flame\s+work|brazing)\b",
        ],
        "exemplars": [
            "welding structural joint",
            "grinding steel pipe near tank",
            "torch cutting bracket",
            "hot work on vessel shell",
        ],
    },
    {
        "name": "Mechanical lifting",
        "lsr_id": "LSR07",
        "patterns": [
            r"\b(crane|rigging|lifting|hoist(ing)?|winch(ing)?)\b",
        ],
        "exemplars": [
            "crane lifting heavy equipment",
            "rigging load on deck",
            "hoisting casing pipe",
            "winching cargo container",
        ],
    },
    {
        "name": "Confined space entry",
        "lsr_id": "LSR02",
        "patterns": [
            r"\b(confined\s+space|tank\s+entry|vessel\s+entry|entering\s+cellar|pit\s+entry)\b",
        ],
        "exemplars": [
            "entering confined space for cleaning",
            "technician entered the storage tank",
            "vessel interior inspection",
            "work inside mud tank pit",
        ],
    },
    {
        "name": "Working at height",
        "lsr_id": "LSR11",
        "patterns": [
            r"\b(working\s+at\s+height|scaffold(ing)?|elevated\s+platform|manlift|derrick\s+ladder|mast\s+climbing)\b",
        ],
        "exemplars": [
            "working at height on mast",
            "scaffolding erection at elevated level",
            "painting from elevated manlift platform",
            "climbing derrick ladder",
        ],
    },
    {
        "name": "Energy isolation",
        "lsr_id": "LSR04",
        "patterns": [
            r"\b(isolat(ing|ion)|loto|depressuriz(ing|ation)|de-energiz(ing|ation))\b",
        ],
        "exemplars": [
            "performing electrical isolation",
            "applying lockout tagout on breaker",
            "depressurizing hydraulic circuit",
            "energy isolation before servicing",
        ],
    },
    {
        "name": "Driving / transport",
        "lsr_id": "LSR03",
        "patterns": [
            r"\b(driv(ing)?|vehicle|truck|convoy|forklift\s+operat\w*|tanker\s+transport)\b",
        ],
        "exemplars": [
            "driving truck on lease road",
            "transporting equipment in convoy",
            "forklift operation in yard",
            "light vehicle journey",
        ],
    },
    {
        "name": "Drilling operations",
        "lsr_id": "LSR10",
        "patterns": [
            r"\b(drilling|trip(ping)?\s+pipe|casing\s+running|top\s+drive|making\s+connection)\b",
        ],
        "exemplars": [
            "tripping drill pipe in hole",
            "drilling operations on rig floor",
            "running casing string into wellbore",
            "making drill pipe connection",
        ],
    },
    {
        "name": "Equipment maintenance",
        "lsr_id": "LSR01",
        "patterns": [
            r"\b(mainten(ance)?|repair(ing)?|servic(ing)?|replac(ing)?\s+(seal|filter|pump|valve|bearing))\b",
        ],
        "exemplars": [
            "routine equipment maintenance on pump",
            "replacing mechanical seal on compressor",
            "servicing hydraulic power unit",
            "valve repair and gasket replacement",
        ],
    },
    {
        "name": "Excavation / trenching",
        "lsr_id": "LSR10",
        "patterns": [
            r"\b(excavat(ing|ion)|trench(ing)?|digging\s+pit|earthwork)\b",
        ],
        "exemplars": [
            "trenching for pipeline laying",
            "excavation near underground cables",
            "digging cellar pit",
        ],
    },
]

# STRICT Location dictionary - NEVER invent a location if not mentioned in text
CANONICAL_LOCATIONS: list[dict[str, Any]] = [
    {"name": "wellhead", "patterns": [r"\bwellhead\b", r"\bx-mas tree\b", r"\bchristmas tree\b"]},
    {"name": "rig floor", "patterns": [r"\brig\s+floor\b", r"\bdrill\s+floor\b", r"\brotary\s+table\b"]},
    {"name": "mud tank", "patterns": [r"\bmud\s+tank\b", r"\bshaker\s+tank\b", r"\bmud\s+pit\b"]},
    {"name": "pipeline ROW", "patterns": [r"\bpipeline(\s+row)?\b", r"\bright\s+of\s+way\b", r"\bflowline\b"]},
    {"name": "workshop", "patterns": [r"\bworkshop\b", r"\bmachine\s+shop\b", r"\bfabrication\s+yard\b"]},
    {"name": "warehouse", "patterns": [r"\bwarehouse\b", r"\bmaterials\s+store\b"]},
    {"name": "well cellar", "patterns": [r"\b(well\s+)?cellar\b", r"\bcellar\s+pit\b"]},
    {"name": "tank farm", "patterns": [r"\btank\s+farm\b", r"\bstorage\s+tank\b", r"\boil\s+tank\b", r"\bbullet\s+tank\b"]},
    {"name": "electrical panel / MCC", "patterns": [r"\belectrical\s+panel\b", r"\bMCC(\s+room)?\b", r"\bsubstation\b", r"\bswitchgear\b"]},
    {"name": "flare area", "patterns": [r"\bflare(\s+area|\s+pit|\s+stack)?\b"]},
    {"name": "scaffold platform", "patterns": [r"\bscaffold(\s+platform)?\b", r"\bstaging\b"]},
    {"name": "compressor house", "patterns": [r"\bcompressor\s+house\b", r"\bgas\s+plant\b", r"\bGCS\b"]},
]

CANONICAL_BARRIERS: list[dict[str, Any]] = [
    {
        "name": "Isolation not verified",
        "lsr_id": "LSR04",
        "patterns": [
            r"\b(without\s+(confirming|verifying|checking)\s+isolation)\b",
            r"\b(not\s+isolated|unisolated|residual\s+pressure\s+remained)\b",
            r"\b(loto\s+not\s+applied|lockout\s+not\s+applied|no\s+loto)\b",
            r"\b(unverified\s+zero\s+energy)\b",
        ],
        "exemplars": [
            "without confirming isolation",
            "LOTO not applied on hydraulic circuit",
            "residual pressure remained in line",
            "line dismantled without energy isolation",
            "lockout tagout omitted before maintenance",
        ],
    },
    {
        "name": "Missing / expired PTW",
        "lsr_id": "LSR10",
        "patterns": [
            r"\b(no\s+permit|permit\s+(expired|missing)|without\s+(valid\s+)?(ptw|permit))\b",
            r"\bunauthorized\s+work\b",
        ],
        "exemplars": [
            "work started without valid permit",
            "permit to work had expired",
            "no PTW issued for hot work",
            "commenced task without work permit",
        ],
    },
    {
        "name": "Missing fall protection",
        "lsr_id": "LSR11",
        "patterns": [
            r"\b(no\s+harness|without\s+(safety\s+)?harness|harness\s+(unhooked|unclipped|not\s+anchored))\b",
            r"\b(missing\s+fall\s+(arrest|protection)|no\s+lifeline)\b",
        ],
        "exemplars": [
            "without safety harness anchored",
            "no fall protection at elevated height",
            "technician unhooked lanyard",
            "working on open edge without lifeline",
        ],
    },
    {
        "name": "Atmosphere not verified",
        "lsr_id": "LSR02",
        "patterns": [
            r"\b(atmospheric\s+conditions?\s+(were\s+)?not\s+verified)\b",
            r"\b(no\s+gas\s+test|gas\s+testing\s+not\s+done|gas\s+test\s+omitted)\b",
            r"\b(toxic\s+gas\s+not\s+checked|oxygen\s+level\s+not\s+measured)\b",
        ],
        "exemplars": [
            "atmospheric conditions were not verified before entry",
            "gas testing omitted before entering tank",
            "no gas test performed",
            "atmosphere not checked for toxic vapors",
        ],
    },
    {
        "name": "Safety control bypassed",
        "lsr_id": "LSR01",
        "patterns": [
            r"\b(interlock\s+(defeated|jumpered)|bypass(ed)?\s+safety\s+control|safety\s+device\s+bridged)\b",
            r"\b(tampered\s+sensor|overridden\s+shutdown)\b",
        ],
        "exemplars": [
            "interlock defeated with jumper switch",
            "bypassed safety control during operation",
            "emergency shutdown system bridged",
            "overridden pressure safety interlock",
        ],
    },
    {
        "name": "No attendant / stand-by",
        "lsr_id": "LSR02",
        "patterns": [
            r"\b(no\s+attendant|missing\s+attendant|without\s+standby|unattended\s+entry)\b",
        ],
        "exemplars": [
            "confined space entered with no attendant",
            "missing standby watch outside vessel",
            "unattended tank entry",
        ],
    },
    {
        "name": "No fire watch",
        "lsr_id": "LSR05",
        "patterns": [
            r"\b(no\s+fire\s+watch|fire\s+watch\s+(missing|absent)|without\s+fire\s+watch)\b",
        ],
        "exemplars": [
            "no fire watch present during welding",
            "fire watch absent in hazardous area",
            "welding commenced without fire watch",
        ],
    },
    {
        "name": "Lifting barrier failed",
        "lsr_id": "LSR07",
        "patterns": [
            r"\b(damaged\s+sling|defective\s+shackle|swl\s+exceeded|rigging\s+failed)\b",
            r"\b(uninspected\s+lifting\s+tackle|improper\s+rigging)\b",
        ],
        "exemplars": [
            "damaged sling snapped during lift",
            "defective rigging hardware used",
            "safe working load exceeded",
            "uninspected lifting tackle",
        ],
    },
    {
        "name": "Line-of-fire control missing",
        "lsr_id": "LSR06",
        "patterns": [
            r"\b(line\s+of\s+fire|no\s+exclusion\s+zone|under\s+(suspended\s+)?load|in\s+the\s+drop\s+zone)\b",
        ],
        "exemplars": [
            "standing in the line of fire",
            "no exclusion zone around lift",
            "walking under suspended load",
            "operator positioned in pinch point path",
        ],
    },
    {
        "name": "Machine guarding defeated",
        "lsr_id": "LSR01",
        "patterns": [
            r"\b(guard\s+removed|missing\s+guard|rotating\s+parts\s+exposed|unguarded\s+coupling)\b",
        ],
        "exemplars": [
            "machine guard removed while running",
            "rotating coupling left unguarded",
            "safety mesh missing from conveyor",
        ],
    },
    {
        "name": "PPE not worn / inadequate",
        "lsr_id": "LSR12",
        "patterns": [
            r"\b(without\s+(face\s+shield|safety\s+glasses|ppe|respirator)|ppe\s+not\s+worn|missing\s+ppe)\b",
        ],
        "exemplars": [
            "worker without face shield during grinding",
            "proper PPE not worn in hazardous zone",
            "chemical respirator missing",
        ],
    },
]

CANONICAL_HAZARDS: list[dict[str, Any]] = [
    {
        "name": "Stored / pressurized energy",
        "lsr_id": "LSR04",
        "patterns": [
            r"\b(pressur\w+\s+(line|gas|liquid|fluid|circuit|vessel)|residual\s+pressure|hydraulic\s+pressure|compressed\s+air)\b",
            r"\bpressur(ized|e)\b",
        ],
        "exemplars": [
            "stored pressurized energy in hydraulic line",
            "pressurized gas trapped in piping",
            "residual pressure under valve",
            "high pressure fluid injection hazard",
        ],
    },
    {
        "name": "Hazardous toxic gas (H2S / VOC)",
        "lsr_id": "LSR02",
        "patterns": [
            r"\b(h2s|hydrogen\s+sulfide|sour\s+gas|toxic\s+(gas|vapor|fumes)|hydrocarbon\s+vapor)\b",
        ],
        "exemplars": [
            "toxic hydrogen sulfide gas release",
            "sour gas vapors in cellar",
            "hazardous hydrocarbon vapor concentration",
            "toxic atmosphere in confined space",
        ],
    },
    {
        "name": "High voltage electrical energy",
        "lsr_id": "LSR04",
        "patterns": [
            r"\b(high\s+voltage|electrical\s+arc(\s+flash)?|live\s+(cable|conductor|switchgear|busbar)|electric\s+shock)\b",
        ],
        "exemplars": [
            "high voltage electrical energy in MCC",
            "live electrical conductor exposed",
            "electrical arc flash hazard",
            "energized busbar shock risk",
        ],
    },
    {
        "name": "Suspended mechanical load",
        "lsr_id": "LSR07",
        "patterns": [
            r"\b(suspended\s+load|overhead\s+crane|falling\s+object|dropped\s+object|drop\s+hazard)\b",
        ],
        "exemplars": [
            "suspended load overhead",
            "heavy machinery suspended by crane",
            "potential dropped object from derrick",
            "falling steel pipe hazard",
        ],
    },
    {
        "name": "Fall from height",
        "lsr_id": "LSR11",
        "patterns": [
            r"\b(fall\s+from\s+height|fall\s+hazard|elevated\s+work|open\s+edge|floor\s+opening)\b",
        ],
        "exemplars": [
            "fall from height exposure",
            "open edge fall hazard on mast",
            "unguarded floor opening drop hazard",
            "working above 2 meters height exposure",
        ],
    },
    {
        "name": "Thermal / fire / explosion",
        "lsr_id": "LSR05",
        "patterns": [
            r"\b(fire|explosion|ignit\w+|flash\s+fire|flammable\s+mixture|hot\s+surface)\b",
        ],
        "exemplars": [
            "flash fire in flammable atmosphere",
            "hydrocarbon ignition risk",
            "hot surface burn hazard",
            "explosive gas air mixture",
        ],
    },
    {
        "name": "Kinetic / moving machinery",
        "lsr_id": "LSR06",
        "patterns": [
            r"\b(rotating\s+(shaft|equipment)|nip\s+point|moving\s+machinery|pinch\s+point|crush\w*)\b",
        ],
        "exemplars": [
            "kinetic energy from rotating equipment",
            "pinch point crush hazard",
            "exposed rotating drive shaft",
            "moving vehicle collision exposure",
        ],
    },
]


# ==============================================================================
# EMBEDDING CACHE FOR PRECURSOR CONCEPTS
# ==============================================================================

_PRECURSOR_CONCEPT_EMBEDDINGS: dict[str, dict[str, Any]] | None = None


def _init_precursor_concept_embeddings() -> dict[str, dict[str, Any]]:
    """Caches dense 384-d normalized embeddings for canonical precursor concepts."""
    global _PRECURSOR_CONCEPT_EMBEDDINGS
    if _PRECURSOR_CONCEPT_EMBEDDINGS is not None:
        return _PRECURSOR_CONCEPT_EMBEDDINGS

    cache: dict[str, dict[str, Any]] = {
        "activities": {},
        "barriers": {},
        "hazards": {},
    }

    try:
        # Pre-compute activity exemplar embeddings
        for act in CANONICAL_ACTIVITIES:
            vecs = extract_embeddings(act["exemplars"])
            cache["activities"][act["name"]] = {
                "config": act,
                "vecs": vecs,
            }

        # Pre-compute barrier exemplar embeddings
        for bar in CANONICAL_BARRIERS:
            vecs = extract_embeddings(bar["exemplars"])
            cache["barriers"][bar["name"]] = {
                "config": bar,
                "vecs": vecs,
            }

        # Pre-compute hazard exemplar embeddings
        for haz in CANONICAL_HAZARDS:
            vecs = extract_embeddings(haz["exemplars"])
            cache["hazards"][haz["name"]] = {
                "config": haz,
                "vecs": vecs,
            }

        _PRECURSOR_CONCEPT_EMBEDDINGS = cache
    except Exception as e:
        logger.warning(f"Could not initialize precursor concept embeddings: {e}")
        _PRECURSOR_CONCEPT_EMBEDDINGS = cache

    return _PRECURSOR_CONCEPT_EMBEDDINGS


# ==============================================================================
# EXTRACTION HELPER FUNCTIONS
# ==============================================================================

def _split_sentences(text: str) -> list[str]:
    """Splits text into cleaned sentences preserving original structure."""
    raw_sents = re.split(r"(?<=[.!?])\s+|\n+", text)
    return [s.strip() for s in raw_sents if s.strip()]


def _extract_evidence_span(text: str, match_pattern: str | None = None, key_phrase: str | None = None) -> str | None:
    """Returns the exact sentence or clause from text that contains the evidence."""
    if match_pattern:
        m = re.search(match_pattern, text, re.IGNORECASE)
        if m:
            start = max(0, text.rfind(".", 0, m.start()) + 1)
            end = text.find(".", m.end())
            if end == -1:
                end = len(text)
            else:
                end = end + 1
            return text[start:end].strip()

    if key_phrase:
        # Match as substring
        idx = text.lower().find(key_phrase.lower())
        if idx >= 0:
            start = max(0, text.rfind(".", 0, idx) + 1)
            end = text.find(".", idx + len(key_phrase))
            if end == -1:
                end = len(text)
            else:
                end = end + 1
            return text[start:end].strip()

    return None


def _find_exact_phrase_in_text(text: str, phrase: str) -> str | None:
    """Finds exact substring in text case-insensitively, returning the raw casing."""
    idx = text.lower().find(phrase.lower())
    if idx >= 0:
        return text[idx : idx + len(phrase)]
    return None


def extract_location(text: str, equipment: str | None = None) -> tuple[str | None, str | None]:
    """Extracts location or asset strictly if mentioned in text or equipment metadata.
    
    CRITICAL ANTI-HALLUCINATION RULE:
    If no location is stated in report text or explicit equipment metadata,
    return (None, None). Do NOT invent a location.
    """
    for loc_item in CANONICAL_LOCATIONS:
        for pat in loc_item["patterns"]:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                return loc_item["name"], m.group(0)

    # If equipment is provided and matches known locations
    if equipment and equipment.strip().lower() not in {"general", "unspecified", "none", "n/a", "unknown"}:
        for loc_item in CANONICAL_LOCATIONS:
            for pat in loc_item["patterns"]:
                if re.search(pat, equipment, re.IGNORECASE):
                    return loc_item["name"], equipment.strip()

    return None, None


def extract_precursor(
    text: str,
    equipment: str | None = None,
    job_type: str | None = None,
    fallback_to_rules: bool = True,
) -> PrecursorRecord:
    """Extracts full 6-dimensional precursor record from incident report text.
    
    Dimensions:
      1. Activity
      2. Location (Strictly None if not mentioned)
      3. Barrier failure
      4. Hazard / Exposure
      5. Relevant LSR
      6. Evidence phrases
    """
    if not text or not text.strip():
        return PrecursorRecord(
            activity=None,
            location=None,
            barrier_failure=None,
            hazard_exposure=None,
            relevant_lsr=None,
            relevant_lsr_id=None,
            evidence_phrase=None,
            confidence=0.0,
            extraction_method="empty_text",
        )

    # 1. First, check rule patterns for deterministic high-confidence extraction
    matched_activities: list[tuple[str, str, str | None, str | None]] = []  # (name, lsr_id, sent_evidence, clause)
    for act in CANONICAL_ACTIVITIES:
        for pat in act["patterns"]:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                clause = m.group(0)
                ev = _extract_evidence_span(text, match_pattern=pat) or clause
                matched_activities.append((act["name"], act["lsr_id"], ev, clause))
                break

    matched_barriers: list[tuple[str, str, str | None, str | None]] = []  # (name, lsr_id, sent_evidence, clause)
    for bar in CANONICAL_BARRIERS:
        for pat in bar["patterns"]:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                clause = m.group(0)
                ev = _extract_evidence_span(text, match_pattern=pat) or clause
                matched_barriers.append((bar["name"], bar["lsr_id"], ev, clause))
                break

    matched_hazards: list[tuple[str, str, str | None, str | None]] = []  # (name, lsr_id, sent_evidence, clause)
    for haz in CANONICAL_HAZARDS:
        for pat in haz["patterns"]:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                clause = m.group(0)
                ev = _extract_evidence_span(text, match_pattern=pat) or clause
                matched_hazards.append((haz["name"], haz["lsr_id"], ev, clause))
                break

    # 2. Strict location detection (anti-hallucination)
    location_val, location_ev = extract_location(text, equipment=equipment)

    # 3. If rules did not match activity, barrier, or hazard, apply semantic concept extraction
    concept_cache = _init_precursor_concept_embeddings()
    sentences = _split_sentences(text)

    # Sentence embeddings
    sent_vecs = None
    if sentences:
        try:
            sent_vecs = extract_embeddings(sentences)
        except Exception as e:
            logger.warning(f"Could not compute sentence embeddings for precursor extraction: {e}")
            sent_vecs = None

    # Semantic Activity matching if not matched by rules
    if not matched_activities and sent_vecs is not None and len(sent_vecs) > 0 and concept_cache.get("activities"):
        best_act = None
        best_act_sim = 0.0
        best_act_sent = None
        for act_name, data in concept_cache["activities"].items():
            sims = np.dot(sent_vecs, data["vecs"].T)  # (n_sents, n_exemplars)
            max_sim = float(np.max(sims))
            if max_sim > best_act_sim:
                best_act_sim = max_sim
                best_act = act_name
                best_act_lsr = data["config"]["lsr_id"]
                best_s_idx = int(np.unravel_index(np.argmax(sims), sims.shape)[0])
                best_act_sent = sentences[best_s_idx]

        if best_act and best_act_sim >= PRECURSOR_SEMANTIC_THRESHOLD:
            matched_activities.append((best_act, best_act_lsr, best_act_sent, best_act_sent))

    # Semantic Barrier matching if not matched by rules
    if not matched_barriers and sent_vecs is not None and len(sent_vecs) > 0 and concept_cache.get("barriers"):
        best_bar = None
        best_bar_sim = 0.0
        best_bar_sent = None
        for bar_name, data in concept_cache["barriers"].items():
            sims = np.dot(sent_vecs, data["vecs"].T)
            max_sim = float(np.max(sims))
            if max_sim > best_bar_sim:
                best_bar_sim = max_sim
                best_bar = bar_name
                best_bar_lsr = data["config"]["lsr_id"]
                best_s_idx = int(np.unravel_index(np.argmax(sims), sims.shape)[0])
                best_bar_sent = sentences[best_s_idx]

        if best_bar and best_bar_sim >= PRECURSOR_SEMANTIC_THRESHOLD:
            matched_barriers.append((best_bar, best_bar_lsr, best_bar_sent, best_bar_sent))

    # Semantic Hazard matching if not matched by rules
    if not matched_hazards and sent_vecs is not None and len(sent_vecs) > 0 and concept_cache.get("hazards"):
        best_haz = None
        best_haz_sim = 0.0
        best_haz_sent = None
        for haz_name, data in concept_cache["hazards"].items():
            sims = np.dot(sent_vecs, data["vecs"].T)
            max_sim = float(np.max(sims))
            if max_sim > best_haz_sim:
                best_haz_sim = max_sim
                best_haz = haz_name
                best_haz_lsr = data["config"]["lsr_id"]
                best_s_idx = int(np.unravel_index(np.argmax(sims), sims.shape)[0])
                best_haz_sent = sentences[best_s_idx]

        if best_haz and best_haz_sim >= PRECURSOR_SEMANTIC_THRESHOLD:
            matched_hazards.append((best_haz, best_haz_lsr, best_haz_sent, best_haz_sent))

    # 4. Fallback to metadata job_type or legacy rules if still missing
    primary_activity: str | None = None
    activity_ev: str | None = None
    activity_clause: str | None = None
    activity_lsr_id: str | None = None

    if matched_activities:
        primary_activity, activity_lsr_id, activity_ev, activity_clause = matched_activities[0]
    elif job_type and job_type.strip().lower() not in {"general", "unspecified", "none", "n/a", "unknown"}:
        primary_activity = job_type.strip()
        activity_ev = f"Job metadata: {job_type}"
        activity_clause = activity_ev

    primary_barrier: str | None = None
    barrier_ev: str | None = None
    barrier_clause: str | None = None
    barrier_lsr_id: str | None = None

    if matched_barriers:
        primary_barrier, barrier_lsr_id, barrier_ev, barrier_clause = matched_barriers[0]

    primary_hazard: str | None = None
    hazard_ev: str | None = None
    hazard_clause: str | None = None
    hazard_lsr_id: str | None = None

    if matched_hazards:
        primary_hazard, hazard_lsr_id, hazard_ev, hazard_clause = matched_hazards[0]

    # Fallback to legacy extraction if everything is missing and fallback enabled
    is_fallback = False
    if not primary_activity and not primary_barrier and fallback_to_rules:
        legacy = legacy_extract_triple(text, equipment=equipment, job_type=job_type)
        if legacy["activity"] != "unspecified activity":
            primary_activity = legacy["activity"]
            activity_ev = text[:60]
            activity_clause = activity_ev
            is_fallback = True
        if legacy["barrier_failure"] != "barrier not identified":
            primary_barrier = legacy["barrier_failure"]
            barrier_ev = text[:60]
            barrier_clause = barrier_ev
            is_fallback = True

    # 5. Resolve Relevant Life-Saving Rule (LSR)
    resolved_lsr_id = barrier_lsr_id or activity_lsr_id or hazard_lsr_id
    resolved_lsr_name = None
    if resolved_lsr_id:
        rule_cfg = get_rule_by_id(resolved_lsr_id)
        if rule_cfg:
            resolved_lsr_name = rule_cfg.name

    # 6. Build evidence dictionary and primary evidence phrase
    evidence_dict: dict[str, str | None] = {
        "activity": activity_clause or activity_ev,
        "location": location_ev,
        "barrier_failure": barrier_clause or barrier_ev,
        "hazard_exposure": hazard_clause or hazard_ev,
    }

    # Combined evidence phrase prioritizing the concise barrier clause or hazard/activity
    key_evidence = barrier_clause or barrier_ev or hazard_clause or hazard_ev or activity_clause or activity_ev or (text[:120] if text else None)

    # 7. Confidence estimation based on dimensions identified
    dim_count = sum(1 for v in [primary_activity, location_val, primary_barrier, primary_hazard] if v is not None)
    if is_fallback:
        conf = 0.65
        method = FALLBACK_VERSION
    elif dim_count >= 3:
        conf = 0.92
        method = EXTRACTION_VERSION
    elif dim_count >= 2:
        conf = 0.85
        method = EXTRACTION_VERSION
    elif dim_count == 1:
        conf = 0.70
        method = EXTRACTION_VERSION
    else:
        conf = 0.40
        method = EXTRACTION_VERSION

    return PrecursorRecord(
        activity=primary_activity,
        location=location_val,
        barrier_failure=primary_barrier,
        hazard_exposure=primary_hazard,
        relevant_lsr=resolved_lsr_name,
        relevant_lsr_id=resolved_lsr_id,
        evidence_phrase=key_evidence,
        evidence=evidence_dict,
        confidence=conf,
        extraction_method=method,
        secondary_activities=[a[0] for a in matched_activities[1:]],
        secondary_barriers=[b[0] for b in matched_barriers[1:]],
    )
