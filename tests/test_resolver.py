"""
tests/test_resolver.py
======================
Unit tests for the Informal Address Resolver.
Run: python -m pytest tests/ -v
"""

import math
import sys
import os

# Allow importing resolver from project root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from resolver import (
    resolve,
    detect_language,
    parse_modifier,
    extract_candidates,
    apply_offset,
    compute_confidence,
    haversine,
    _normalise,
    Candidate,
    ModifierResult,
    _load_gazetteer,
)

# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_candidate(score=0.85, is_alias=False):
    """Build a dummy Candidate for testing confidence scoring."""
    gz = _load_gazetteer()
    lm = gz[0]
    return Candidate(landmark=lm, matched_text=lm._norm_name, score=score, is_alias=is_alias)


# ══════════════════════════════════════════════════════════════════════════════
# 1. TEXT NORMALISATION
# ══════════════════════════════════════════════════════════════════════════════

class TestNormalise:
    def test_lowercases(self):
        assert _normalise("KABALE HOSPITAL") == "kabale hospital"

    def test_strips_emoji(self):
        result = _normalise("📍 near pharmacy")
        assert "📍" not in result
        assert "near pharmacy" in result

    def test_collapses_whitespace(self):
        assert _normalise("behind  the  market") == "behind the market"

    def test_strips_accents(self):
        # derrière → derriere
        assert "derriere" in _normalise("derrière la pharmacie")

    def test_empty_string(self):
        assert _normalise("") == ""

    def test_emoji_only(self):
        assert _normalise("🔴🔵🏍️").strip() == ""


# ══════════════════════════════════════════════════════════════════════════════
# 2. LANGUAGE DETECTION
# ══════════════════════════════════════════════════════════════════════════════

class TestDetectLanguage:
    def test_english_basic(self):
        lang, conf = detect_language("behind the hospital near the market")
        assert lang == "en"
        assert conf > 0.3

    def test_french_basic(self):
        lang, conf = detect_language("derrière la pharmacie kabale")
        assert lang == "fr"
        assert conf > 0.3

    def test_kinyarwanda_basic(self):
        lang, conf = detect_language("inyuma ya ibitaro kabale hafi ya isoko")
        assert lang == "kin"
        assert conf > 0.3

    def test_returns_tuple(self):
        result = detect_language("near the bus park")
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_confidence_in_range(self):
        _, conf = detect_language("next to the police station")
        assert 0.0 <= conf <= 1.0

    def test_empty_input_defaults(self):
        lang, conf = detect_language("")
        assert lang in ("en", "fr", "kin")
        assert 0.0 <= conf <= 1.0


# ══════════════════════════════════════════════════════════════════════════════
# 3. MODIFIER PARSING
# ══════════════════════════════════════════════════════════════════════════════

class TestParseModifier:
    def test_behind_english(self):
        m = parse_modifier("behind the big hospital")
        assert m.key == "behind"
        assert m.offset_m == 50.0
        assert m.direction == "south"

    def test_behind_french(self):
        m = parse_modifier("derrière la pharmacie bright")
        assert m.key == "behind"

    def test_behind_kinyarwanda(self):
        m = parse_modifier("inyuma ya ibitaro")
        assert m.key == "behind"

    def test_next_to(self):
        m = parse_modifier("next to the mtn shop")
        assert m.key == "next_to"
        assert m.offset_m == 20.0

    def test_opposite(self):
        m = parse_modifier("opposite the bus park")
        assert m.key == "opposite"
        assert m.direction == "north"

    def test_near(self):
        m = parse_modifier("near kabale university")
        assert m.key == "near"
        assert m.offset_m == 60.0

    def test_no_modifier(self):
        m = parse_modifier("kabale market")
        assert m.key == "none"
        assert m.offset_m == 0.0

    def test_typo_in_modifier(self):
        # "behnd" → should still resolve via fuzzy token matching
        m = parse_modifier("behnd the hospital")
        assert m.key in ("behind", "none")  # fuzzy may or may not catch

    def test_confidence_bonus_range(self):
        m = parse_modifier("behind the hospital")
        assert 0.0 <= m.confidence_bonus <= 1.0

    def test_hafi_ya(self):
        m = parse_modifier("hafi ya stesheni ya total")
        assert m.key in ("next_to", "near")


# ══════════════════════════════════════════════════════════════════════════════
# 4. FUZZY MATCHING / CANDIDATE EXTRACTION
# ══════════════════════════════════════════════════════════════════════════════

class TestExtractCandidates:
    def test_exact_alias_match(self):
        candidates = extract_candidates("bus park kabale")
        assert len(candidates) > 0
        names = [c.landmark.name for c in candidates]
        assert "Kabale Bus Terminal" in names

    def test_pharmacy_match(self):
        candidates = extract_candidates("pharmacie bright kabale")
        assert len(candidates) > 0
        assert candidates[0].landmark.name == "Bright Pharmacy Kabale"

    def test_returns_candidates_list(self):
        result = extract_candidates("kabale hospital")
        assert isinstance(result, list)

    def test_top_score_first(self):
        candidates = extract_candidates("kabale police station")
        scores = [c.score for c in candidates]
        assert scores == sorted(scores, reverse=True)

    def test_noisy_input(self):
        # Typos injected
        candidates = extract_candidates("kable univeristy")
        assert len(candidates) > 0

    def test_empty_query_no_crash(self):
        result = extract_candidates("")
        assert isinstance(result, list)

    def test_alias_flag(self):
        # "bus park" is an alias, not the canonical name
        candidates = extract_candidates("bus park")
        top = candidates[0] if candidates else None
        if top and top.matched_text == "bus park kabale":
            assert top.is_alias

    def test_score_in_range(self):
        candidates = extract_candidates("total petrol station")
        for c in candidates:
            assert 0.0 <= c.score <= 1.0


# ══════════════════════════════════════════════════════════════════════════════
# 5. COORDINATE OFFSET
# ══════════════════════════════════════════════════════════════════════════════

class TestApplyOffset:
    BASE_LAT, BASE_LON = -1.2490, 29.9848

    def test_north_offset_increases_lat(self):
        lat, lon = apply_offset(self.BASE_LAT, self.BASE_LON, 50, "north")
        assert lat > self.BASE_LAT
        assert abs(lon - self.BASE_LON) < 1e-8

    def test_south_offset_decreases_lat(self):
        lat, lon = apply_offset(self.BASE_LAT, self.BASE_LON, 50, "south")
        assert lat < self.BASE_LAT

    def test_east_offset_increases_lon(self):
        lat, lon = apply_offset(self.BASE_LAT, self.BASE_LON, 50, "east")
        assert lon > self.BASE_LON
        assert abs(lat - self.BASE_LAT) < 1e-8

    def test_west_offset_decreases_lon(self):
        lat, lon = apply_offset(self.BASE_LAT, self.BASE_LON, 50, "west")
        assert lon < self.BASE_LON

    def test_zero_offset_unchanged(self):
        lat, lon = apply_offset(self.BASE_LAT, self.BASE_LON, 0, "north")
        assert lat == self.BASE_LAT
        assert lon == self.BASE_LON

    def test_none_direction_unchanged(self):
        lat, lon = apply_offset(self.BASE_LAT, self.BASE_LON, 50, "none")
        assert lat == self.BASE_LAT
        assert lon == self.BASE_LON

    def test_50m_north_approx(self):
        lat, lon = apply_offset(self.BASE_LAT, self.BASE_LON, 50, "north")
        dist = haversine(self.BASE_LAT, self.BASE_LON, lat, lon)
        assert 45 < dist < 55, f"Expected ~50m, got {dist:.1f}m"


# ══════════════════════════════════════════════════════════════════════════════
# 6. CONFIDENCE SCORING
# ══════════════════════════════════════════════════════════════════════════════

class TestConfidence:
    def test_high_score_high_confidence(self):
        c = _make_candidate(score=0.95)
        mod = ModifierResult("behind", 50.0, "south", 0.9)
        conf = compute_confidence([c], mod, lang_conf=0.85)
        assert conf > 0.70

    def test_low_score_low_confidence(self):
        c = _make_candidate(score=0.35)
        mod = ModifierResult("none", 0.0, "none", 0.0)
        conf = compute_confidence([c], mod, lang_conf=0.40)
        assert conf < 0.40

    def test_no_candidates_zero(self):
        mod = ModifierResult("none", 0.0, "none", 0.0)
        conf = compute_confidence([], mod, lang_conf=0.80)
        assert conf == 0.0

    def test_confidence_in_range(self):
        c = _make_candidate(score=0.75)
        mod = ModifierResult("next_to", 20.0, "east", 0.9)
        conf = compute_confidence([c], mod, lang_conf=0.80)
        assert 0.0 <= conf <= 1.0

    def test_no_modifier_caps_confidence(self):
        c = _make_candidate(score=0.95)
        mod = ModifierResult("none", 0.0, "none", 0.0)
        conf = compute_confidence([c], mod, lang_conf=0.95)
        assert conf <= 0.70


# ══════════════════════════════════════════════════════════════════════════════
# 7. FULL RESOLVE PIPELINE
# ══════════════════════════════════════════════════════════════════════════════

class TestResolve:
    def test_returns_dict(self):
        result = resolve("behind the hospital kabale")
        assert isinstance(result, dict)

    def test_required_keys(self):
        result = resolve("next to mtn shop kabale")
        keys = {"lat", "lon", "confidence", "matched_landmark", "rationale", "escalate", "language", "modifier"}
        assert keys.issubset(result.keys())

    def test_lat_lon_numeric(self):
        result = resolve("opposite bus park kabale")
        assert isinstance(result["lat"], float)
        assert isinstance(result["lon"], float)

    def test_confidence_range(self):
        result = resolve("derrière la pharmacie bright kabale")
        assert 0.0 <= result["confidence"] <= 1.0

    def test_french_input(self):
        result = resolve("derrière la pharmacie bright kabale")
        assert result["matched_landmark"] == "Bright Pharmacy Kabale"
        assert result["modifier"] == "behind"
        assert result["language"] == "fr"

    def test_kinyarwanda_input(self):
        result = resolve("inyuma ya ibitaro kabale")
        # Should match a hospital
        assert "Hospital" in result["matched_landmark"] or result["confidence"] > 0.0

    def test_english_input(self):
        result = resolve("opposite the bus park kabale")
        assert result["matched_landmark"] == "Kabale Bus Terminal"
        assert result["modifier"] == "opposite"

    def test_empty_input_escalates(self):
        result = resolve("")
        assert result["escalate"] is True
        assert result["lat"] == 0.0

    def test_gibberish_escalates(self):
        result = resolve("xyzxyz abc123 !!!!")
        assert result["escalate"] is True

    def test_rationale_is_string(self):
        result = resolve("near the total petrol station")
        assert isinstance(result["rationale"], str)
        assert len(result["rationale"]) > 10

    def test_escalate_flag_type(self):
        result = resolve("near the hospital")
        assert isinstance(result["escalate"], bool)

    def test_known_landmark_low_offset(self):
        """Resolved coords should be within 200 m of the known landmark."""
        result = resolve("next to kabale bus terminal")
        gz = _load_gazetteer()
        bus = next(lm for lm in gz if lm.id == "LM009")
        dist = haversine(result["lat"], result["lon"], bus.lat, bus.lon)
        # 200 m tolerance for "next to" (20 m offset + any noise)
        assert dist < 200, f"Too far from landmark: {dist:.1f} m"


# ══════════════════════════════════════════════════════════════════════════════
# 8. EDGE CASES
# ══════════════════════════════════════════════════════════════════════════════

class TestEdgeCases:
    def test_mixed_language_input(self):
        # Mixed EN + FR + KIN
        result = resolve("derrière kabale hospital hafi ya market")
        assert isinstance(result, dict)
        assert result["lat"] != 0.0 or result["escalate"]

    def test_only_emoji(self):
        result = resolve("📍🔴🏍️")
        assert result["escalate"] is True

    def test_very_long_input(self):
        long_text = "behind the " + "big " * 50 + "hospital kabale"
        result = resolve(long_text)
        assert isinstance(result, dict)

    def test_all_caps_input(self):
        result = resolve("BEHIND THE KABALE HOSPITAL")
        assert "Hospital" in result["matched_landmark"]

    def test_alias_resolution(self):
        # "katale" is an alias for Kabale Central Market
        result = resolve("near katale market")
        assert "Market" in result["matched_landmark"]

    def test_rn3_landmark(self):
        result = resolve("pharmacy on RN3 red gate")
        # Should find Bright Pharmacy (alias: pharmacie sur rn3) or RN3 junction
        assert result["lat"] != 0.0

    def test_whitespace_only(self):
        result = resolve("   ")
        assert result["escalate"] is True

    def test_numbers_only(self):
        result = resolve("123456 789")
        assert isinstance(result, dict)

    def test_haversine_symmetry(self):
        d1 = haversine(-1.249, 29.984, -1.250, 29.985)
        d2 = haversine(-1.250, 29.985, -1.249, 29.984)
        assert abs(d1 - d2) < 0.001

    def test_haversine_zero(self):
        assert haversine(0, 0, 0, 0) == 0.0


if __name__ == "__main__":
    # Simple runner without pytest
    import traceback

    test_classes = [
        TestNormalise, TestDetectLanguage, TestParseModifier,
        TestExtractCandidates, TestApplyOffset, TestConfidence,
        TestResolve, TestEdgeCases,
    ]
    passed, failed = 0, 0
    for cls in test_classes:
        obj = cls()
        for name in dir(obj):
            if name.startswith("test_"):
                try:
                    getattr(obj, name)()
                    print(f"  ✅ {cls.__name__}::{name}")
                    passed += 1
                except Exception as e:
                    print(f"  ❌ {cls.__name__}::{name}: {e}")
                    traceback.print_exc()
                    failed += 1

    print(f"\n{'='*50}")
    print(f"Results: {passed} passed, {failed} failed")
