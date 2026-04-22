---
title: Informal Address Resolver
emoji: 📍
colorFrom: blue
colorTo: indigo
sdk: gradio
sdk_version: "5.29.0"
app_file: app.py
pinned: false
license: mit
tags:
  - nlp
  - geospatial
  - fuzzy-matching
  - address-resolution
  - multilingual
  - offline
  - logistics
---

#  Informal Address Resolver

**T1.2 · LogiTech · Text Processing · Geospatial**

Converts noisy multilingual delivery address descriptions into GPS coordinates — fully offline, CPU-only, < 100 ms per query.

---


##  Repository Structure

```
informal-address-resolver/
│
├── resolver.py            ← Core resolver (pure-function API)
├── app.py                 ← HuggingFace Spaces Gradio app
├── generate_data.py       ← Reproducible synthetic data generator
├── eval_notebook_builder.py ← Builds eval.ipynb
│
├── data/
│   ├── gazetteer.json     ← 50 landmarks (Kabale, SW Uganda)
│   ├── descriptions.csv   ← 200 synthetic noisy descriptions
│   └── gold.csv           ← 50 ground-truth rows for evaluation
│
├── notebooks/
│   └── eval.ipynb         ← Evaluation: metrics + error analysis
│
├── tests/
│   └── test_resolver.py   ← 64 unit tests (pytest)
│
├── correction_flow.md     ← Product & Business artifact
├── process_log.md         ← Hour-by-hour timeline + LLM usage
├── SIGNED.md              ← Honor code
├── requirements.txt
└── LICENSE
```

---

##  Public API

```python
from resolver import resolve

result = resolve("derrière la pharmacie bright kabale")
# {
#   "lat": -1.252049,
#   "lon": 29.984900,
#   "confidence": 0.7013,
#   "matched_landmark": "Bright Pharmacy Kabale",
#   "rationale": "Matched 'Bright Pharmacy Kabale' via alias 'pharmacie de kabale' ...",
#   "escalate": false,
#   "language": "fr",
#   "modifier": "behind"
# }
```

### Supported Languages
| Code | Language | Example modifier |
|---|---|---|
| `en` | English | behind, next to, opposite, near, above |
| `fr` | French | derrière, à côté de, en face de, près de |
| `kin` | Kinyarwanda | inyuma ya, hafi ya, imbere ya, hejuru ya |

### Spatial Modifiers → Offsets
| Modifier | Offset | Direction |
|---|---|---|
| behind / inyuma ya / derrière | 50 m | south |
| next to / hafi ya / à côté de | 20 m | east |
| opposite / imbere ya / en face de | 30 m | north |
| near / hafi ya / près de | 60 m | centroid |
| above / hejuru ya / au-dessus de | 40 m | north |

---

##  Evaluation Results

Run `python eval_notebook_builder.py && jupyter nbconvert --to notebook --execute notebooks/eval.ipynb` to reproduce.

| Metric | Value |
|---|---|
| Mean Haversine Error | ~65 m |
| % within 100 m | ~72% |
| % within 300 m | ~94% |
| Mean Latency | < 15 ms |
| % under 100 ms SLA | 100% |

---

##  System Design

```
text → normalise → detect_language → extract_candidates (fuzzy match)
     → parse_modifier → apply_offset → score_confidence → return dict
```

**Key decisions:**
- **Fuzzy backend**: rapidfuzz WRatio when available; difflib SequenceMatcher as stdlib fallback — same API, same tests pass either way
- **Modifier matching**: longest-phrase-first to prevent partial matches; fuzzy token fallback handles typo'd modifier words
- **Confidence**: weighted formula (fuzzy 45% + modifier 25% + spread 15% + lang 15%); capped at 0.70 when no modifier found
- **Escalation**: `confidence < 0.30` or `top_score < 0.45` → `escalate: True` → flags for dispatcher
- **No ML at runtime**: all logic deterministic; reproducible output for same input

---

##  Running Tests

```bash
python -m pytest tests/ -v
# or without pytest:
python tests/test_resolver.py
```

64 tests · 0 failures.

---

##  License

MIT — see `LICENSE` file.

---

## 🔗 Links

- **HuggingFace Space**: [spaces/NSamson1/informal-address-resolver](https://huggingface.co/spaces/NSamson1/informal-address-resolver)
- **GitHub**: [github.com/NSamson1/informal-address-resolver](https://github.com/NSamson1/informal-address-resolver)
