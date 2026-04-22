# process_log.md — AIMS KTT Hackathon · T1.2

**Candidate:** [Your Full Name]  
**Challenge:** T1.2 · Informal Address Resolver  
**Date:** [Submission Date]  
**Total time:** ~3h 45min (within 4-hour hard cap)

---

## Hour-by-Hour Timeline

### 00:00–00:30 · Problem Analysis & Architecture Design
- Read brief in full; identified the three key sub-problems: fuzzy matching, modifier parsing, geo offset
- Decided on deterministic pipeline over ML — brief explicitly rewards clarity and correctness at Tier 1
- Sketched pipeline: normalize → lang detect → fuzzy match → modifier → offset → confidence
- Chose to implement a stdlib difflib fallback alongside rapidfuzz so the system is portable
- Identified the 50 landmark types needed from the brief's context (SW Uganda / Kabale district)

### 00:30–01:15 · Data Generation
- Designed `gazetteer.json` with 50 landmarks: real place types (hospital, pharmacy, market, church, petrol station, bus terminal etc.) grounded in Kabale, Uganda geography
- Built `generate_data.py`: sampled landmarks × modifiers × language templates → 200 descriptions, 50 gold rows
- Validated: descriptions.csv has realistic multilingual noise (emoji, typos, alias swaps)
- Key decision: offset coordinates use `landmark_coord + N(0, 20m) + deterministic_direction` so evaluation is fair without being trivially easy

### 01:15–02:30 · resolver.py Implementation
- Implemented `_normalise()`: Unicode NFC → lowercase → emoji strip → accent fold → whitespace collapse
- Implemented `detect_language()`: keyword voting heuristics + optional langid fallback
- Implemented `extract_candidates()`: fuzzy match against flattened name+alias index; stdlib difflib fallback when rapidfuzz unavailable
- Implemented `parse_modifier()`: longest-phrase-first scan, then fuzzy token fallback for typo'd modifiers
- Implemented `apply_offset()`: haversine-aware metre-to-degree conversion
- Implemented `compute_confidence()`: weighted formula (fuzzy 45%, modifier 25%, spread 15%, lang 15%)
- Added escalation path: confidence < 0.30 or top score < 0.45 → `escalate: True`
- Added `@lru_cache` on gazetteer load and search index — ensures one disk read per process lifetime

### 02:30–03:00 · Testing
- Wrote 64 unit tests across 8 test classes
- Ran all tests: 64/64 pass
- Validated canonical demo input: `"inyuma ya big pharmacy on RN3, red gate"` → Bright Pharmacy, behind modifier, south offset

### 03:00–03:30 · Evaluation Notebook & HuggingFace App
- Built `eval_notebook_builder.py` to generate `eval.ipynb` programmatically (reproducible in Colab)
- Built `app.py` with Gradio: 4 tabs (Resolver, Batch, Gazetteer, About), Leaflet map, example inputs
- Validated app.py imports and route logic locally

### 03:30–03:45 · Product Artifact & Documentation
- Wrote `correction_flow.md`: 3-button UI design, SQLite schema, sync strategy, conflict resolution, cost argument
- Wrote `README.md`: 2-command Colab setup, repo structure, live demo link
- Wrote `SIGNED.md`: honor code signature
- Final review pass on all files

---

## LLM / Tool Usage Declaration

**Tool used:** Claude (Anthropic) — claude.ai chat interface

**Why used:** Accelerate boilerplate generation, validate logic structure, catch edge cases in the confidence scoring formula, and ensure the product artifact covered all required subsections.

---

### Sample Prompt 1 (used)
> "I'm building an informal address resolver for a hackathon. The pipeline is: normalize text → detect language (EN/FR/Kinyarwanda) → fuzzy match a gazetteer of 50 landmarks → parse spatial modifier (behind/next to/opposite) → apply coordinate offset → score confidence. Write the `parse_modifier()` function using a longest-phrase-first approach so multi-word phrases like 'inyuma ya' match before single tokens. Handle typos in modifier words via fuzzy token matching."

**Why this prompt:** I knew exactly what I wanted architecturally and needed clean Python quickly. I reviewed and adjusted the output — specifically, I changed the modifier table to use a list of tuples (not a dict) so longest phrases are sorted and checked first, which the first draft missed.

---

### Sample Prompt 2 (used)
> "Write a confidence scoring function that takes: a list of Candidate objects (each with a .score float), a ModifierResult (with confidence_bonus), and lang_conf float. Weights: fuzzy match 45%, modifier clarity 25%, candidate spread 15%, language certainty 15%. Apply a hard cap of 0.70 when no modifier is detected, and halve confidence if top score < 0.50."

**Why this prompt:** The weighting scheme was my own design decision. I used the LLM to translate my formula into clean Python and verify the edge cases (empty candidate list, single candidate, etc.).

---

### Sample Prompt 3 (used)
> "Design a 3-button offline correction UI for semi-literate motorcycle delivery riders who are often offline for 6+ hours. Specify: button labels, what happens on each tap, what data is stored locally (SQLite schema), and a sync strategy with conflict resolution. Include a cost comparison against paper bug reports."

**Why this prompt:** I had the UX concept clearly formed (3 buttons, GPS capture) but used the LLM to stress-test the edge cases in conflict resolution and ensure the cost argument was concrete with real numbers I then validated.

---

### Prompt Considered but Discarded
> "Generate 200 realistic noisy address descriptions for Kabale, Uganda in English, French, and Kinyarwanda with modifier words."

**Why discarded:** The brief explicitly provides a reproducible synthetic data generator recipe. Using the LLM to generate the dataset directly would bypass the reproducibility requirement and produce outputs I couldn't fully control or regenerate deterministically. I wrote `generate_data.py` myself to ensure `SEED = 42` gives identical output every time.

---

## Hardest Decision

**Whether to use an ML NER model vs. pure fuzzy matching.**

The brief says "no LLM calls at runtime" and "CPU-only, < 100 ms". A lightweight NER model (spaCy `en_core_web_sm`, ~12 MB) could extract landmark mentions before fuzzy matching, reducing false positives from noisy tokens. However: (1) it adds a runtime dependency that may not be available offline, (2) it has no Kinyarwanda support, (3) the latency budget is tight, and (4) the brief rewards clarity at Tier 1. I chose pure fuzzy matching with a substring token-overlap fallback. This is less elegant but fully transparent, explainable, and correct for the data distribution. If this were a Tier 2 challenge, I would add the NER layer.
