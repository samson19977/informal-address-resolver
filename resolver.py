"""
resolver.py
===========
Informal Address Resolver — AIMS KTT Hackathon · T1.2
Author : Samson Niyizurugero
Licence: MIT

Architecture
------------
text → normalize → detect_language → extract_candidates (fuzzy match gazetteer)
     → parse_modifier → apply_offset → score_confidence → return result dict

All logic is deterministic / CPU-only, no external API calls, no LLM at runtime.
Average latency: < 100 ms per call on a laptop CPU.

Public API
----------
    resolve(text: str) -> dict
    resolve_batch(texts: list[str]) -> list[dict]
"""

from __future__ import annotations

import json
import math
import os
import re
import unicodedata
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Optional

# ── Optional fast-path: use rapidfuzz when available, else stdlib fallback ─────
try:
    from rapidfuzz import fuzz as _rfuzz
    from rapidfuzz import process as _rprocess

    def _ratio(a: str, b: str) -> float:
        return _rfuzz.WRatio(a, b) / 100.0

    def _extract(query: str, choices: list[str], limit: int, threshold: float) -> list[tuple[str, float, int]]:
        raw = _rprocess.extract(query, choices, scorer=_rfuzz.WRatio, limit=limit, score_cutoff=threshold * 100)
        return [(r[0], r[1] / 100.0, r[2]) for r in raw]

    _FUZZY_BACKEND = "rapidfuzz"

except ImportError:
    # ── stdlib fallback (difflib) — slightly slower but always available ───────
    import difflib

    def _ratio(a: str, b: str) -> float:
        return difflib.SequenceMatcher(None, a, b).ratio()

    def _extract(query: str, choices: list[str], limit: int, threshold: float) -> list[tuple[str, float, int]]:
        results = []
        for idx, choice in enumerate(choices):
            score = _ratio(query, choice)
            if score >= threshold:
                results.append((choice, score, idx))
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:limit]

    _FUZZY_BACKEND = "difflib"

# ── Optional langid ────────────────────────────────────────────────────────────
try:
    import langid as _langid
    _langid.set_languages(["en", "fr", "rw"])  # rw = Kinyarwanda
    _HAS_LANGID = True
except Exception:
    _HAS_LANGID = False

# ── Paths ──────────────────────────────────────────────────────────────────────
_HERE = os.path.dirname(os.path.abspath(__file__))
_GAZETTEER_PATH = os.path.join(_HERE, "data", "gazetteer.json")

# ═══════════════════════════════════════════════════════════════════════════════
# DATA TYPES
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class Landmark:
    id: str
    name: str
    aliases: list[str]
    type: str
    district: str
    lat: float
    lon: float
    # Derived: normalised searchable strings (populated at load time)
    _norm_name: str = field(default="", repr=False)
    _norm_aliases: list[str] = field(default_factory=list, repr=False)


@dataclass
class Candidate:
    landmark: Landmark
    matched_text: str       # which string was matched (name or alias)
    score: float            # 0–1 fuzzy similarity
    is_alias: bool


@dataclass
class ModifierResult:
    key: str                # e.g. "behind"
    offset_m: float         # metres to shift
    direction: str          # north/south/east/west/none
    confidence_bonus: float # 0–1 how clearly modifier was parsed


# ═══════════════════════════════════════════════════════════════════════════════
# GAZETTEER LOADING (cached)
# ═══════════════════════════════════════════════════════════════════════════════

@lru_cache(maxsize=1)
def _load_gazetteer() -> list[Landmark]:
    """Load and normalise the gazetteer exactly once."""
    with open(_GAZETTEER_PATH, "r", encoding="utf-8") as fh:
        raw = json.load(fh)
    landmarks = []
    for entry in raw:
        lm = Landmark(
            id=entry["id"],
            name=entry["name"],
            aliases=entry.get("aliases", []),
            type=entry.get("type", ""),
            district=entry.get("district", ""),
            lat=entry["lat"],
            lon=entry["lon"],
        )
        lm._norm_name = _normalise(lm.name)
        lm._norm_aliases = [_normalise(a) for a in lm.aliases]
        landmarks.append(lm)
    return landmarks


# ═══════════════════════════════════════════════════════════════════════════════
# STEP 1 — TEXT NORMALISATION
# ═══════════════════════════════════════════════════════════════════════════════

# Strip emoji by Unicode category (So = Symbol/Other, Cs = Surrogate)
_EMOJI_RE = re.compile(
    "["
    "\U0001F300-\U0001FFFF"
    "\U00002600-\U000027BF"
    "\U0000FE00-\U0000FE0F"
    "]+",
    flags=re.UNICODE,
)

# Collapse repeated punctuation / spaces
_MULTI_SPACE_RE = re.compile(r"\s+")
_PUNCT_RE = re.compile(r"[^\w\s\-'àâäéèêëîïôùûüçñ]", re.UNICODE)


def _normalise(text: str) -> str:
    """
    Lowercase, strip emoji, remove accents (for matching), collapse whitespace.
    Keeps apostrophes for French contractions.
    """
    # Unicode NFC first
    text = unicodedata.normalize("NFC", text)
    # Remove emoji
    text = _EMOJI_RE.sub(" ", text)
    # Lowercase
    text = text.lower()
    # Remove accents — fold to ASCII for cross-language matching
    nfkd = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in nfkd if unicodedata.category(c) != "Mn")
    # Strip non-word chars (except hyphen and apostrophe)
    text = _PUNCT_RE.sub(" ", text)
    # Collapse whitespace
    text = _MULTI_SPACE_RE.sub(" ", text).strip()
    return text


# ═══════════════════════════════════════════════════════════════════════════════
# STEP 2 — LANGUAGE DETECTION
# ═══════════════════════════════════════════════════════════════════════════════

# Rule-based keyword sets for fast heuristic detection
_KIN_KEYWORDS = {
    "inyuma", "hafi", "imbere", "hejuru", "iruhande", "hagati", "ibitaro",
    "isoko", "itorero", "muri", "kuri", "na", "ya", "rwa", "bwa", "kwa",
}
_FR_KEYWORDS = {
    "derriere", "pres", "cote", "face", "dessus", "arriere", "aupres",
    "hopital", "pharmacie", "eglise", "marche", "bureau", "station", "gare",
    "pres de", "a cote", "en face",
}
_EN_KEYWORDS = {
    "behind", "next", "near", "opposite", "above", "beside", "facing",
    "hospital", "pharmacy", "church", "market", "office", "station",
    "adjacent", "across", "uphill",
}


def detect_language(text: str) -> tuple[str, float]:
    """
    Returns (lang_code, confidence) where lang_code ∈ {'en','fr','kin'}.
    Uses langid when available, falls back to keyword heuristics.
    """
    norm = _normalise(text)
    tokens = set(norm.split())

    # Keyword voting
    kin_hits = len(tokens & _KIN_KEYWORDS)
    fr_hits = len(tokens & _FR_KEYWORDS)
    en_hits = len(tokens & _EN_KEYWORDS)

    if _HAS_LANGID:
        try:
            lang, conf = _langid.classify(text)
            # Map langid codes to our three
            if lang in ("rw", "rn", "sw"):
                lang = "kin"
            elif lang == "fr":
                lang = "fr"
            else:
                lang = "en"
            # If keyword voting strongly disagrees, trust keywords
            if kin_hits >= 2 and lang != "kin":
                return "kin", 0.70
            return lang, min(0.95, abs(conf))
        except Exception:
            pass

    # Pure keyword fallback
    total = kin_hits + fr_hits + en_hits
    if total == 0:
        return "en", 0.40  # default

    if kin_hits >= fr_hits and kin_hits >= en_hits:
        conf = kin_hits / (total + 2)
        return "kin", min(0.85, conf + 0.4)
    elif fr_hits >= en_hits:
        conf = fr_hits / (total + 2)
        return "fr", min(0.85, conf + 0.4)
    else:
        conf = en_hits / (total + 2)
        return "en", min(0.85, conf + 0.4)


# ═══════════════════════════════════════════════════════════════════════════════
# STEP 3 — ENTITY EXTRACTION (Landmark Matching)
# ═══════════════════════════════════════════════════════════════════════════════

# Minimum fuzzy score to consider a match (0–1)
_MIN_SCORE: float = 0.45
_TOP_K: int = 5


def _all_search_strings(gazetteer: list[Landmark]) -> list[tuple[str, Landmark, bool]]:
    """
    Flatten gazetteer into (normalised_string, landmark, is_alias) triples.
    Built once; used for every query.
    """
    strings = []
    for lm in gazetteer:
        strings.append((lm._norm_name, lm, False))
        for alias in lm._norm_aliases:
            strings.append((alias, lm, True))
    return strings


@lru_cache(maxsize=1)
def _get_search_index():
    """Cache the flattened search index."""
    gz = _load_gazetteer()
    triples = _all_search_strings(gz)
    texts = [t[0] for t in triples]
    return triples, texts


def extract_candidates(query: str, top_k: int = _TOP_K) -> list[Candidate]:
    """
    Fuzzy-match normalised query against all landmark names + aliases.
    Returns up to top_k Candidate objects sorted by descending score.
    """
    norm_q = _normalise(query)
    triples, texts = _get_search_index()

    raw_matches = _extract(norm_q, texts, limit=top_k * 2, threshold=_MIN_SCORE)

    seen_ids: set[str] = set()
    candidates: list[Candidate] = []

    for (matched_text, score, idx) in raw_matches:
        _, lm, is_alias = triples[idx]
        if lm.id in seen_ids:
            # Keep the higher-scoring match for each landmark
            continue
        seen_ids.add(lm.id)
        candidates.append(Candidate(
            landmark=lm,
            matched_text=matched_text,
            score=score,
            is_alias=is_alias,
        ))
        if len(candidates) >= top_k:
            break

    # Secondary pass: substring search for very short/noisy queries
    if not candidates:
        candidates = _substring_fallback(norm_q, triples)

    return candidates


def _substring_fallback(norm_q: str, triples: list) -> list[Candidate]:
    """
    If fuzzy matching fails, try token-overlap scoring as a last resort.
    """
    q_tokens = set(norm_q.split())
    scored: list[tuple[float, Landmark, str, bool]] = []

    seen: set[str] = set()
    for (norm_text, lm, is_alias) in triples:
        if lm.id in seen:
            continue
        t_tokens = set(norm_text.split())
        overlap = len(q_tokens & t_tokens)
        if overlap > 0:
            score = overlap / max(len(q_tokens), len(t_tokens))
            scored.append((score, lm, norm_text, is_alias))
            seen.add(lm.id)

    scored.sort(key=lambda x: x[0], reverse=True)
    return [
        Candidate(landmark=lm, matched_text=txt, score=sc, is_alias=ia)
        for sc, lm, txt, ia in scored[:_TOP_K]
    ]


# ═══════════════════════════════════════════════════════════════════════════════
# STEP 4 — SPATIAL MODIFIER PARSING
# ═══════════════════════════════════════════════════════════════════════════════

# Each entry: (normalised_keywords, offset_m, direction, confidence_bonus, key)
_MODIFIER_TABLE = [
    # ── "behind / back" ────────────────────────────────────────────────────────
    (["behind", "inyuma ya", "inyuma y", "derriere", "en arriere", "a l arriere",
      "round the back", "at the back", "back of"],
     50.0, "south", 0.9, "behind"),

    # ── "next to / beside" ────────────────────────────────────────────────────
    (["next to", "beside", "adjacent to", "hafi ya", "iruhande rwa", "a cote de",
      "juste a cote", "right next", "near side"],
     20.0, "east", 0.9, "next_to"),

    # ── "opposite / across" ───────────────────────────────────────────────────
    (["opposite", "across from", "facing", "en face de", "face a", "imbere ya",
      "ugereranye na", "directly opposite", "devant"],
     30.0, "north", 0.85, "opposite"),

    # ── "near / around" ───────────────────────────────────────────────────────
    (["near", "close to", "around", "somewhere near", "pres de", "non loin de",
      "a proximite", "hafi ya", "hagati ya", "not far"],
     60.0, "random", 0.6, "near"),

    # ── "above / uphill" ──────────────────────────────────────────────────────
    (["above", "up from", "uphill from", "au-dessus de", "en haut de",
      "hejuru ya", "up the hill"],
     40.0, "north", 0.8, "above"),

    # ── "below / downhill" ────────────────────────────────────────────────────
    (["below", "down from", "downhill", "en bas de", "sous", "munsi ya"],
     40.0, "south", 0.8, "below"),

    # ── "in front of" ─────────────────────────────────────────────────────────
    (["in front", "at the front", "devant", "imbere"],
     25.0, "south", 0.85, "in_front"),
]

_NO_MODIFIER = ModifierResult(key="none", offset_m=0.0, direction="none", confidence_bonus=0.0)


def parse_modifier(text: str) -> ModifierResult:
    """
    Scan normalised text for spatial modifier phrases.
    Returns the best matching ModifierResult (or a null result if none found).
    Handles multi-word phrases before single tokens to avoid false partial matches.
    """
    norm = _normalise(text)

    # Try longest phrases first (sorted by phrase length descending)
    all_phrases: list[tuple[str, float, str, float, str]] = []
    for keywords, offset_m, direction, conf_bonus, key in _MODIFIER_TABLE:
        for kw in keywords:
            all_phrases.append((kw, offset_m, direction, conf_bonus, key))

    all_phrases.sort(key=lambda x: len(x[0]), reverse=True)

    for (phrase, offset_m, direction, conf_bonus, key) in all_phrases:
        if phrase in norm:
            return ModifierResult(
                key=key,
                offset_m=offset_m,
                direction=direction,
                confidence_bonus=conf_bonus,
            )

    # Fuzzy fallback for modifier tokens (handles typos in modifiers)
    modifier_tokens = {
        "behind": ("behind", 50.0, "south", 0.7),
        "inyuma": ("behind", 50.0, "south", 0.7),
        "derriere": ("behind", 50.0, "south", 0.7),
        "opposite": ("opposite", 30.0, "north", 0.7),
        "facing": ("opposite", 30.0, "north", 0.7),
        "hafi": ("next_to", 20.0, "east", 0.65),
        "pres": ("near", 60.0, "random", 0.55),
        "near": ("near", 60.0, "random", 0.55),
        "above": ("above", 40.0, "north", 0.7),
        "hejuru": ("above", 40.0, "north", 0.7),
    }
    for token in norm.split():
        for kw, (mod_key, offset_m, direction, conf_bonus) in modifier_tokens.items():
            if _ratio(token, kw) >= 0.82:
                return ModifierResult(
                    key=mod_key,
                    offset_m=offset_m,
                    direction=direction,
                    confidence_bonus=conf_bonus,
                )

    return _NO_MODIFIER


# ═══════════════════════════════════════════════════════════════════════════════
# STEP 5 — GEO RESOLUTION
# ═══════════════════════════════════════════════════════════════════════════════

_EARTH_R = 111_320.0  # metres per degree latitude


def apply_offset(lat: float, lon: float, offset_m: float, direction: str) -> tuple[float, float]:
    """
    Shift (lat, lon) by offset_m in the given direction.
    'random' defaults to east (deterministic — reproducible output).
    """
    if direction == "random" or direction == "none" or offset_m == 0:
        return lat, lon

    dlat, dlon = 0.0, 0.0
    cos_lat = math.cos(math.radians(lat))

    if direction == "north":
        dlat = offset_m / _EARTH_R
    elif direction == "south":
        dlat = -offset_m / _EARTH_R
    elif direction == "east":
        dlon = offset_m / (_EARTH_R * cos_lat) if cos_lat > 0 else 0.0
    elif direction == "west":
        dlon = -offset_m / (_EARTH_R * cos_lat) if cos_lat > 0 else 0.0

    return lat + dlat, lon + dlon


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in metres between two coordinate pairs."""
    R = 6_371_000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


# ═══════════════════════════════════════════════════════════════════════════════
# STEP 6 — CONFIDENCE SCORING
# ═══════════════════════════════════════════════════════════════════════════════

def compute_confidence(
    candidates: list[Candidate],
    modifier: ModifierResult,
    lang_conf: float,
) -> float:
    """
    Weighted confidence on [0, 1].

    Weights
    -------
    fuzzy_score      : 0.45  — quality of the landmark match
    modifier_clarity : 0.25  — how clearly a spatial modifier was found
    candidate_spread : 0.15  — penalty when top-2 scores are close (ambiguous)
    language_conf    : 0.15  — certainty of language detection
    """
    if not candidates:
        return 0.0

    top = candidates[0]

    # 1. Fuzzy match quality (0–1)
    w_fuzzy = 0.45
    fuzzy_component = top.score * w_fuzzy

    # 2. Modifier clarity (0–1 from modifier table, 0 if none found)
    w_mod = 0.25
    mod_component = modifier.confidence_bonus * w_mod

    # 3. Candidate spread (low spread = high confidence)
    w_spread = 0.15
    if len(candidates) >= 2:
        delta = top.score - candidates[1].score
        spread_score = min(1.0, delta * 5)  # 0.2 gap → score 1.0
    else:
        spread_score = 1.0
    spread_component = spread_score * w_spread

    # 4. Language detection confidence
    w_lang = 0.15
    lang_component = lang_conf * w_lang

    confidence = fuzzy_component + mod_component + spread_component + lang_component

    # Hard caps
    if top.score < 0.5:
        confidence *= 0.5  # Low match quality → halve confidence
    if modifier.key == "none":
        confidence = min(confidence, 0.70)  # No modifier → cap at 0.70

    return round(min(1.0, max(0.0, confidence)), 4)


# ═══════════════════════════════════════════════════════════════════════════════
# STEP 7 — ESCALATION (Outlier / Unknown Landmark)
# ═══════════════════════════════════════════════════════════════════════════════

_ESCALATION_THRESHOLD = 0.30  # Confidence below this → flag for dispatcher


def _should_escalate(confidence: float, candidates: list[Candidate]) -> bool:
    """Return True if the resolver cannot confidently resolve this description."""
    if confidence < _ESCALATION_THRESHOLD:
        return True
    if not candidates or candidates[0].score < 0.45:
        return True
    return False


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN PUBLIC API
# ═══════════════════════════════════════════════════════════════════════════════

def resolve(text: str) -> dict:
    """
    Convert a free-text informal address into structured coordinates.

    Parameters
    ----------
    text : str
        Noisy multilingual description (EN / FR / Kinyarwanda mix).

    Returns
    -------
    dict with keys:
        lat              : float   — resolved latitude
        lon              : float   — resolved longitude
        confidence       : float   — 0–1 confidence score
        matched_landmark : str     — canonical name of matched landmark
        rationale        : str     — human-readable explanation
        escalate         : bool    — True if dispatcher review recommended
        language         : str     — detected language code
        modifier         : str     — detected spatial modifier key
    """
    # ── 1. Normalise ────────────────────────────────────────────────────────
    if not text or not text.strip():
        return _null_result("empty input")

    # ── 2. Language detection ───────────────────────────────────────────────
    lang, lang_conf = detect_language(text)

    # ── 3. Modifier parsing ─────────────────────────────────────────────────
    modifier = parse_modifier(text)

    # ── 4. Candidate extraction ─────────────────────────────────────────────
    candidates = extract_candidates(text)

    if not candidates:
        return _null_result(f"no landmark matched in: '{text[:80]}'")

    best = candidates[0]
    lm = best.landmark

    # ── 5. Coordinate resolution ────────────────────────────────────────────
    if modifier.direction == "random":
        # "near" etc. — return landmark centroid with no offset
        final_lat, final_lon = lm.lat, lm.lon
    else:
        final_lat, final_lon = apply_offset(lm.lat, lm.lon, modifier.offset_m, modifier.direction)

    # ── 6. Confidence ───────────────────────────────────────────────────────
    confidence = compute_confidence(candidates, modifier, lang_conf)

    # ── 7. Escalation check ─────────────────────────────────────────────────
    escalate = _should_escalate(confidence, candidates)

    # ── 8. Rationale ────────────────────────────────────────────────────────
    alias_note = f" (via alias '{best.matched_text}')" if best.is_alias else ""
    mod_note = (
        f"Modifier '{modifier.key}' → {modifier.offset_m:.0f} m {modifier.direction}."
        if modifier.key != "none"
        else "No spatial modifier detected; using landmark centroid."
    )
    rationale = (
        f"Matched '{lm.name}'{alias_note} with score {best.score:.2f} "
        f"[{_FUZZY_BACKEND}]. "
        f"{mod_note} "
        f"Language: {lang} (conf={lang_conf:.2f}). "
        f"Confidence: {confidence:.2f}."
    )
    if escalate:
        rationale += " ⚠️ Low confidence — flagged for dispatcher review."

    return {
        "lat": round(final_lat, 6),
        "lon": round(final_lon, 6),
        "confidence": confidence,
        "matched_landmark": lm.name,
        "rationale": rationale,
        "escalate": escalate,
        "language": lang,
        "modifier": modifier.key,
    }


def _null_result(reason: str) -> dict:
    """Return a zeroed result with escalation flag when resolution fails."""
    return {
        "lat": 0.0,
        "lon": 0.0,
        "confidence": 0.0,
        "matched_landmark": "UNKNOWN",
        "rationale": f"Resolution failed: {reason}",
        "escalate": True,
        "language": "unknown",
        "modifier": "none",
    }


def resolve_batch(texts: list[str]) -> list[dict]:
    """Resolve a list of descriptions. Returns results in same order."""
    return [resolve(t) for t in texts]


# ═══════════════════════════════════════════════════════════════════════════════
# CLI entry point
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys
    import json as _json

    query = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "inyuma ya big pharmacy on RN3, red gate"
    result = resolve(query)
    print(_json.dumps(result, indent=2, ensure_ascii=False))
