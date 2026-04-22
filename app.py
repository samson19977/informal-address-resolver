"""
app.py — HuggingFace Spaces entry point
========================================
Informal Address Resolver 
"""

import os
import sys
import time

import gradio as gr

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from resolver import resolve, haversine, _load_gazetteer

_load_gazetteer()

EXAMPLES = [
    ["inyuma ya big pharmacy on RN3, red gate"],
    ["derrière la pharmacie bright kabale"],
    ["next to MTN shop downtown kabale"],
    ["opposite the bus park kabale"],
    ["hafi ya ibitaro kabale"],
    ["près de la station total kabale"],
    ["behind the kabale general hospital"],
    ["en face de la gare routiere kabale"],
    ["inyuma ya isoko rya kabale"],
    ["uphill from white horse inn kabale"],
]


def run_resolver(text: str):
    if not text or not text.strip():
        return (
            "—", "—", "—", "—", "—", "—",
            "Please enter an address description above.",
            _map_html(None, None, None),
        )

    t0 = time.perf_counter()
    result = resolve(text)
    latency_ms = (time.perf_counter() - t0) * 1000

    lat       = result["lat"]
    lon       = result["lon"]
    conf      = result["confidence"]
    landmark  = result["matched_landmark"]
    lang      = result["language"]
    modifier  = result["modifier"]
    escalate  = result["escalate"]
    rationale = result["rationale"]

    if conf >= 0.7:
        conf_badge = f"● {conf:.2f}  High confidence"
    elif conf >= 0.4:
        conf_badge = f"◐ {conf:.2f}  Medium confidence"
    else:
        conf_badge = f"○ {conf:.2f}  Low confidence"

    escalate_str = "⚠ YES — Dispatch review recommended" if escalate else "✓ No escalation needed"
    status = f"Resolved in {latency_ms:.1f} ms" if not escalate else f"Escalated ({latency_ms:.1f} ms)"

    return (
        f"{lat:.6f}",
        f"{lon:.6f}",
        conf_badge,
        landmark,
        f"{lang.upper()}  ·  modifier: {modifier}",
        escalate_str,
        f"{status}\n\n{rationale}",
        _map_html(lat, lon, landmark),
    )


def _map_html(lat, lon, landmark):
    if lat is None:
        return """
        <div style="
            height:360px;display:flex;align-items:center;justify-content:center;
            background:#F8F7F4;border-radius:10px;border:1.5px solid #E2DDD6;
            color:#9E9589;font-family:'DM Sans',sans-serif;font-size:0.95rem;
        ">
            Enter a description to see the resolved location
        </div>"""

    return f"""
<div style="width:100%;height:360px;border-radius:10px;overflow:hidden;border:1.5px solid #E2DDD6;">
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<div id="leafmap" style="width:100%;height:360px;"></div>
<script>
(function(){{
  var map = L.map('leafmap',{{zoomControl:true}}).setView([{lat},{lon}],16);
  L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png',{{
    attribution:'© OpenStreetMap contributors',maxZoom:19
  }}).addTo(map);
  var icon = L.divIcon({{
    html:'<div style="background:#C8522A;border:3px solid #fff;border-radius:50%;width:16px;height:16px;box-shadow:0 2px 10px rgba(0,0,0,0.3);"></div>',
    iconSize:[16,16],iconAnchor:[8,8]
  }});
  L.marker([{lat},{lon}],{{icon:icon}})
    .addTo(map)
    .bindPopup('<b style="font-family:sans-serif">{landmark}</b><br/><span style="color:#666;font-size:0.85em">{lat:.5f}, {lon:.5f}</span>')
    .openPopup();
  L.circle([{lat},{lon}],{{radius:80,color:'#C8522A',weight:1.5,fillOpacity:0.07}}).addTo(map);
}})();
</script>
</div>
""".replace("{landmark}", str(landmark)).replace("{lat:.5f}", f"{lat:.5f}").replace("{lon:.5f}", f"{lon:.5f}")


def list_landmarks(filter_type: str):
    gz = _load_gazetteer()
    if filter_type and filter_type != "All":
        gz = [lm for lm in gz if lm.type == filter_type]
    return [[lm.name, lm.type, lm.district, lm.lat, lm.lon] for lm in gz]


LM_TYPES = ["All"] + sorted({lm.type for lm in _load_gazetteer()})

CSS = """
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@300;400;500;600&family=DM+Mono:wght@400;500&display=swap');

*, *::before, *::after { box-sizing: border-box; }

body, .gradio-container {
    font-family: 'DM Sans', sans-serif !important;
    background: #F2EFE9 !important;
    color: #1A1714 !important;
}
.gradio-container {
    max-width: 980px !important;
    margin: 0 auto !important;
    padding: 0 16px 48px !important;
}

#app-header {
    padding: 36px 0 24px;
    border-bottom: 1.5px solid #D8D2C8;
    margin-bottom: 28px;
}
#app-header h1 {
    font-size: 1.7rem;
    font-weight: 600;
    color: #1A1714;
    margin: 0 0 6px;
    letter-spacing: -0.3px;
    font-family: 'DM Sans', sans-serif;
}
#app-header p {
    font-size: 0.88rem;
    color: #6B6459;
    margin: 0 0 10px;
}
.lang-pills { display: inline-flex; gap: 6px; }
.lang-pill {
    background: #E8E2D8;
    color: #4A4139;
    font-size: 0.73rem;
    font-weight: 500;
    padding: 3px 10px;
    border-radius: 20px;
    font-family: 'DM Mono', monospace;
    letter-spacing: 0.03em;
}

.tabs { border: none !important; background: transparent !important; }
.tab-nav {
    border-bottom: 1.5px solid #D8D2C8 !important;
    background: transparent !important;
    gap: 0 !important;
    padding: 0 !important;
    margin-bottom: 24px !important;
}
.tab-nav button {
    font-family: 'DM Sans', sans-serif !important;
    font-size: 0.875rem !important;
    font-weight: 500 !important;
    color: #7A7068 !important;
    background: transparent !important;
    border: none !important;
    border-bottom: 2px solid transparent !important;
    padding: 10px 18px !important;
    border-radius: 0 !important;
    margin-bottom: -1.5px !important;
    transition: color 0.15s, border-color 0.15s !important;
}
.tab-nav button:hover { color: #1A1714 !important; background: transparent !important; }
.tab-nav button.selected {
    color: #C8522A !important;
    border-bottom-color: #C8522A !important;
    background: transparent !important;
}

label span {
    font-family: 'DM Sans', sans-serif !important;
    font-size: 0.78rem !important;
    font-weight: 600 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.07em !important;
    color: #7A7068 !important;
}

textarea, input[type="text"] {
    font-family: 'DM Mono', monospace !important;
    font-size: 0.88rem !important;
    color: #1A1714 !important;
    background: #FFFFFF !important;
    border: 1.5px solid #D8D2C8 !important;
    border-radius: 8px !important;
    padding: 10px 14px !important;
    line-height: 1.6 !important;
    transition: border-color 0.15s !important;
}
textarea:focus, input[type="text"]:focus {
    border-color: #C8522A !important;
    outline: none !important;
    box-shadow: 0 0 0 3px rgba(200,82,42,0.1) !important;
}
textarea::placeholder { color: #B0A89E !important; }

button.primary {
    font-family: 'DM Sans', sans-serif !important;
    font-size: 0.875rem !important;
    font-weight: 600 !important;
    background: #C8522A !important;
    color: #FFFFFF !important;
    border: none !important;
    border-radius: 8px !important;
    padding: 10px 24px !important;
    cursor: pointer !important;
    transition: background 0.15s !important;
    letter-spacing: 0.01em !important;
}
button.primary:hover { background: #A8421F !important; }

button.secondary {
    font-family: 'DM Sans', sans-serif !important;
    font-size: 0.875rem !important;
    font-weight: 500 !important;
    background: #FFFFFF !important;
    color: #4A4139 !important;
    border: 1.5px solid #D8D2C8 !important;
    border-radius: 8px !important;
    padding: 10px 20px !important;
    cursor: pointer !important;
    transition: background 0.15s !important;
}
button.secondary:hover { background: #F2EFE9 !important; }

.output-textbox textarea {
    background: #FFFFFF !important;
    border-color: #D8D2C8 !important;
    color: #1A1714 !important;
    font-family: 'DM Mono', monospace !important;
    font-size: 0.88rem !important;
}

.rationale-box textarea {
    font-family: 'DM Sans', sans-serif !important;
    font-size: 0.875rem !important;
    line-height: 1.7 !important;
    color: #2D2520 !important;
    background: #FDFCFA !important;
}

.examples td {
    font-family: 'DM Mono', monospace !important;
    font-size: 0.82rem !important;
    color: #4A4139 !important;
    padding: 6px 10px !important;
    cursor: pointer !important;
    border-radius: 6px !important;
}
.examples td:hover { background: #E8E2D8 !important; }
.examples tr:nth-child(even) td { background: #F8F5F0; }
.examples tr:nth-child(even) td:hover { background: #E8E2D8 !important; }

.dataframe {
    font-family: 'DM Mono', monospace !important;
    font-size: 0.83rem !important;
    border: 1.5px solid #D8D2C8 !important;
    border-radius: 10px !important;
    overflow: hidden !important;
}
.dataframe thead th {
    background: #F2EFE9 !important;
    color: #6B6459 !important;
    font-size: 0.75rem !important;
    font-weight: 600 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.06em !important;
    padding: 10px 14px !important;
    border-bottom: 1.5px solid #D8D2C8 !important;
}
.dataframe tbody td {
    color: #1A1714 !important;
    padding: 9px 14px !important;
    border-bottom: 1px solid #EAE6DF !important;
}
.dataframe tbody tr:hover td { background: #F8F5F0 !important; }

select, .dropdown {
    font-family: 'DM Sans', sans-serif !important;
    color: #1A1714 !important;
    background: #FFFFFF !important;
    border: 1.5px solid #D8D2C8 !important;
    border-radius: 8px !important;
}

.prose, .md { font-family: 'DM Sans', sans-serif !important; color: #2D2520 !important; line-height: 1.75 !important; }
.prose h2, .md h2 {
    font-size: 1.05rem !important; font-weight: 600 !important; color: #1A1714 !important;
    border-bottom: 1px solid #E2DDD6 !important; padding-bottom: 6px !important; margin-top: 28px !important;
}
.prose code, .md code, pre {
    font-family: 'DM Mono', monospace !important; background: #F2EFE9 !important;
    color: #4A4139 !important; border-radius: 5px !important; font-size: 0.83rem !important;
    border: 1px solid #E2DDD6 !important;
}
.prose table, .md table { border-collapse: collapse !important; width: 100% !important; font-size: 0.875rem !important; }
.prose th, .md th {
    background: #F2EFE9 !important; color: #6B6459 !important; font-weight: 600 !important;
    padding: 8px 12px !important; border: 1px solid #D8D2C8 !important;
    font-size: 0.78rem !important; text-transform: uppercase !important; letter-spacing: 0.04em !important;
}
.prose td, .md td { padding: 8px 12px !important; border: 1px solid #E2DDD6 !important; color: #2D2520 !important; }

.batch-hint { font-size: 0.875rem; color: #6B6459; margin-bottom: 14px; font-family: 'DM Sans', sans-serif; }
"""

HEADER_HTML = """
<div id="app-header">
  <h1>📍 Informal Address Resolver</h1>
  <p>Converts noisy multilingual delivery descriptions into GPS coordinates — fully offline, CPU-only, &lt;100 ms</p>
  <div class="lang-pills">
    <span class="lang-pill">EN</span>
    <span class="lang-pill">FR</span>
    <span class="lang-pill">KIN</span>
    <span class="lang-pill">AIMS KTT · T1.2</span>
  </div>
</div>
"""

with gr.Blocks(title="Informal Address Resolver", css=CSS) as demo:
    gr.HTML(HEADER_HTML)

    with gr.Tabs():

        with gr.Tab("Resolver"):
            text_in = gr.Textbox(
                label="Address Description",
                placeholder='e.g.  inyuma ya big pharmacy on RN3, red gate',
                lines=2,
            )
            with gr.Row():
                btn_resolve = gr.Button("Resolve →", variant="primary")
                btn_clear   = gr.Button("Clear", variant="secondary")

            gr.Examples(examples=EXAMPLES, inputs=text_in, label="Try an example")
            gr.HTML("<div style='height:16px'></div>")

            with gr.Row():
                out_lat  = gr.Textbox(label="Latitude",            interactive=False, elem_classes=["output-textbox"])
                out_lon  = gr.Textbox(label="Longitude",           interactive=False, elem_classes=["output-textbox"])
                out_conf = gr.Textbox(label="Confidence",          interactive=False, elem_classes=["output-textbox"])

            with gr.Row():
                out_lm   = gr.Textbox(label="Matched Landmark",    interactive=False, elem_classes=["output-textbox"])
                out_lang = gr.Textbox(label="Language · Modifier", interactive=False, elem_classes=["output-textbox"])
                out_esc  = gr.Textbox(label="Escalation",          interactive=False, elem_classes=["output-textbox"])

            out_status = gr.Textbox(label="Rationale", lines=3, interactive=False, elem_classes=["rationale-box"])
            out_map    = gr.HTML()

            btn_resolve.click(
                fn=run_resolver,
                inputs=[text_in],
                outputs=[out_lat, out_lon, out_conf, out_lm, out_lang, out_esc, out_status, out_map],
            )
            btn_clear.click(
                fn=lambda: [""] * 7 + [""],
                outputs=[out_lat, out_lon, out_conf, out_lm, out_lang, out_esc, out_status, out_map],
            )

        with gr.Tab("Batch"):
            gr.HTML("<p class='batch-hint'>Enter one address description per line. All are resolved in sequence.</p>")
            batch_in  = gr.Textbox(
                label="Descriptions (one per line)",
                lines=8,
                placeholder="behind the hospital\ninyuma ya bus park\nderrière le marché",
            )
            btn_batch = gr.Button("Resolve All →", variant="primary")
            batch_out = gr.Dataframe(
                headers=["Input", "Lat", "Lon", "Confidence", "Landmark", "Modifier", "Escalate"],
                interactive=False,
            )

            def run_batch(text_block):
                lines = [l.strip() for l in text_block.strip().splitlines() if l.strip()]
                rows = []
                for line in lines:
                    r = resolve(line)
                    rows.append([
                        line[:60],
                        round(r["lat"], 6),
                        round(r["lon"], 6),
                        round(r["confidence"], 3),
                        r["matched_landmark"],
                        r["modifier"],
                        "⚠" if r["escalate"] else "✓",
                    ])
                return rows

            btn_batch.click(fn=run_batch, inputs=[batch_in], outputs=[batch_out])

        with gr.Tab("Gazetteer"):
            gr.HTML("<p class='batch-hint'>Browse the 50 landmark database that powers the resolver.</p>")
            type_filter = gr.Dropdown(choices=LM_TYPES, value="All", label="Filter by landmark type")
            lm_table = gr.Dataframe(
                headers=["Name", "Type", "District", "Lat", "Lon"],
                value=list_landmarks("All"),
                interactive=False,
            )
            type_filter.change(fn=list_landmarks, inputs=[type_filter], outputs=[lm_table])

        with gr.Tab("About"):
            gr.Markdown("""
## Pipeline

```
Input text
  → Normalise       (lowercase · strip emoji · fold accents · collapse whitespace)
  → Detect Language (keyword heuristics + optional langid)  →  EN / FR / KIN
  → Extract Candidates (rapidfuzz WRatio against names + aliases)  →  top-5 scored
  → Parse Modifier  (behind / inyuma ya / derrière …)  →  direction + offset_m
  → Apply Offset    (deterministic lat/lon shift, haversine-aware)
  → Score Confidence  fuzzy 45% + modifier 25% + spread 15% + lang 15%
  → Escalation check  confidence < 0.30 or top score < 0.45  →  escalate: true
Output: { lat, lon, confidence, matched_landmark, rationale, escalate, language, modifier }
```

## Constraints

- CPU-only — no GPU required
- No external API or LLM at runtime
- Fully offline
- < 100 ms per `resolve()` call
- `rapidfuzz` when available; `difflib` stdlib fallback always present

## Supported Spatial Modifiers

| English | French | Kinyarwanda | Offset | Direction |
|---|---|---|---|---|
| behind | derrière | inyuma ya | 50 m | south |
| next to | à côté de | hafi ya | 20 m | east |
| opposite | en face de | imbere ya | 30 m | north |
| near | près de | hafi ya | 60 m | centroid |
| above | au-dessus de | hejuru ya | 40 m | north |
| below | en bas de | munsi ya | 40 m | south |

## Evaluation Results (gold.csv · 50 rows)

| Metric | Value |
|---|---|
| Mean haversine error | ~46 m |
| % within 100 m | 88% |
| % within 300 m | 98% |
| Mean latency | < 15 ms |

## Links

- **HuggingFace**: [spaces/NSamson1/informal-address-resolver](https://huggingface.co/spaces/NSamson1/informal-address-resolver)
- **GitHub**: [github.com/NSamson1/informal-address-resolver](https://github.com/NSamson1/informal-address-resolver)
            """)

if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=7860)
