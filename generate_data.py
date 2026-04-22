"""
generate_data.py
Reproducible synthetic data generator for the Informal Address Resolver.
Generates descriptions.csv and gold.csv from gazetteer.json.
Run: python generate_data.py
Takes < 2 minutes on a laptop CPU.
"""

import json
import math
import random
import csv
import os

SEED = 42
random.seed(SEED)

# ── Paths ──────────────────────────────────────────────────────────────────────
HERE = os.path.dirname(os.path.abspath(__file__))
GAZETTEER_PATH = os.path.join(HERE, "data", "gazetteer.json")
DESCRIPTIONS_OUT = os.path.join(HERE, "data", "descriptions.csv")
GOLD_OUT = os.path.join(HERE, "data", "gold.csv")

# ── Modifier templates per language ───────────────────────────────────────────
MODIFIERS = {
    "behind": {
        "en": ["behind {lm}", "at the back of {lm}", "just behind {lm}", "round the back of {lm}"],
        "fr": ["derrière {lm}", "en arrière de {lm}", "à l'arrière de {lm}"],
        "kin": ["inyuma ya {lm}", "inyuma y' {lm}"],
        "offset_m": 50,
        "direction": "south",
    },
    "next_to": {
        "en": ["next to {lm}", "beside {lm}", "right next to {lm}", "adjacent to {lm}"],
        "fr": ["à côté de {lm}", "près de {lm}", "juste à côté de {lm}"],
        "kin": ["hafi ya {lm}", "iruhande rwa {lm}"],
        "offset_m": 20,
        "direction": "east",
    },
    "opposite": {
        "en": ["opposite {lm}", "across from {lm}", "facing {lm}", "directly opposite {lm}"],
        "fr": ["en face de {lm}", "face à {lm}", "devant {lm}"],
        "kin": ["imbere ya {lm}", "ugereranye na {lm}"],
        "offset_m": 30,
        "direction": "north",
    },
    "near": {
        "en": ["near {lm}", "close to {lm}", "around {lm}", "somewhere near {lm}"],
        "fr": ["près de {lm}", "non loin de {lm}", "à proximité de {lm}"],
        "kin": ["hafi ya {lm}", "hagati ya {lm}"],
        "offset_m": 60,
        "direction": "random",
    },
    "above": {
        "en": ["above {lm}", "up from {lm}", "uphill from {lm}"],
        "fr": ["au-dessus de {lm}", "en haut de {lm}"],
        "kin": ["hejuru ya {lm}"],
        "offset_m": 40,
        "direction": "north",
    },
}

# ── Noise injectors ────────────────────────────────────────────────────────────
EMOJIS = ["📍", "🏍️", "🚗", "📦", "✅", "🔴", "🔵", "⚡"]
MINIBUS_STOPS = ["stage A", "stage ya basi", "bus stop", "arret", "terminus local"]
NOISE_WORDS = ["ok", "si vous plait", "pliz", "asap", "urgent", "attention"]


def _add_typo(word: str) -> str:
    """Inject a single-character Levenshtein-1 typo."""
    if len(word) < 3:
        return word
    kind = random.choice(["swap", "delete", "insert"])
    pos = random.randint(0, len(word) - 1)
    if kind == "swap" and pos < len(word) - 1:
        lst = list(word)
        lst[pos], lst[pos + 1] = lst[pos + 1], lst[pos]
        return "".join(lst)
    elif kind == "delete":
        return word[:pos] + word[pos + 1:]
    else:
        char = random.choice("aeioulnrst")
        return word[:pos] + char + word[pos:]


def _noisy(text: str, p_typo: float = 0.3, p_emoji: float = 0.2, p_extra: float = 0.15) -> str:
    """Randomly inject noise into description text."""
    words = text.split()
    if random.random() < p_typo and words:
        idx = random.randint(0, len(words) - 1)
        words[idx] = _add_typo(words[idx])
    text = " ".join(words)
    if random.random() < p_emoji:
        text = random.choice(EMOJIS) + " " + text
    if random.random() < p_extra:
        extra = random.choice(MINIBUS_STOPS + NOISE_WORDS)
        text = text + ", " + extra
    return text


def _offset_coords(lat: float, lon: float, offset_m: float, direction: str):
    """Apply deterministic meter offset in a cardinal direction."""
    # 1 degree latitude ≈ 111,320 m; longitude varies with cos(lat)
    R = 111_320.0
    if direction == "random":
        direction = random.choice(["north", "south", "east", "west"])
    
    # Add Gaussian noise to offset (σ = 20 m) to simulate real spread
    jitter = random.gauss(0, 20)
    actual = offset_m + jitter

    dlat, dlon = 0.0, 0.0
    if direction == "north":
        dlat = actual / R
    elif direction == "south":
        dlat = -actual / R
    elif direction == "east":
        dlon = actual / (R * math.cos(math.radians(lat)))
    elif direction == "west":
        dlon = -actual / (R * math.cos(math.radians(lat)))

    return round(lat + dlat, 6), round(lon + dlon, 6)


def _pick_landmark_name(lm: dict, lang: str) -> str:
    """Pick canonical name or an alias, optionally in target language."""
    choices = [lm["name"]] + lm["aliases"]
    # Weight toward aliases for realism
    weights = [2] + [1] * len(lm["aliases"])
    return random.choices(choices, weights=weights, k=1)[0]


def _build_description(lm: dict, mod_key: str, lang: str) -> tuple:
    """Return (description_text, true_lat, true_lon, landmark_id)."""
    mod = MODIFIERS[mod_key]
    lm_name = _pick_landmark_name(lm, lang)
    
    templates = mod.get(lang, mod["en"])
    template = random.choice(templates)
    desc = template.format(lm=lm_name)
    
    # Optionally suffix with type or district for realism
    if random.random() < 0.25:
        desc += f" ({lm['type']})"
    if random.random() < 0.15:
        desc += f", {lm['district']}"

    desc = _noisy(desc)
    
    true_lat, true_lon = _offset_coords(lm["lat"], lm["lon"], mod["offset_m"], mod["direction"])
    return desc, true_lat, true_lon, lm["id"]


def generate(n_descriptions: int = 200, n_gold: int = 50):
    """Generate descriptions.csv (200 rows) and gold.csv (50 rows)."""
    with open(GAZETTEER_PATH, "r", encoding="utf-8") as f:
        gazetteer = json.load(f)

    languages = ["en", "fr", "kin"]
    mod_keys = list(MODIFIERS.keys())

    descriptions = []
    gold_rows = []

    for i in range(n_descriptions):
        lm = random.choice(gazetteer)
        lang = random.choices(languages, weights=[0.4, 0.35, 0.25], k=1)[0]
        mod_key = random.choice(mod_keys)
        desc, true_lat, true_lon, lm_id = _build_description(lm, mod_key, lang)

        did = f"D{i+1:03d}"
        descriptions.append({
            "description_id": did,
            "description_text": desc,
            "language_hint": lang,
        })

        # First 50 go into gold (25 seeded = first 25 visible; 25 held-out)
        if i < n_gold:
            gold_rows.append({
                "description_id": did,
                "true_lat": true_lat,
                "true_lon": true_lon,
                "true_landmark_id": lm_id,
                "split": "seeded" if i < 25 else "held_out",
            })

    # Write descriptions.csv
    with open(DESCRIPTIONS_OUT, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["description_id", "description_text", "language_hint"])
        writer.writeheader()
        writer.writerows(descriptions)

    # Write gold.csv
    with open(GOLD_OUT, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["description_id", "true_lat", "true_lon", "true_landmark_id", "split"])
        writer.writeheader()
        writer.writerows(gold_rows)

    print(f"✅ Generated {len(descriptions)} descriptions → {DESCRIPTIONS_OUT}")
    print(f"✅ Generated {len(gold_rows)} gold rows   → {GOLD_OUT}")


if __name__ == "__main__":
    generate()
