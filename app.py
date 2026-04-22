"""
app.py — HuggingFace Spaces entry point
========================================
Informal Address Resolver · AIMS KTT Hackathon T1.2

Deploy on HuggingFace Spaces (Gradio SDK).
All logic is in resolver.py — this file is pure UI.
"""

import json
import os
import sys
import time

# ── Gradio ────────────────────────────────────────────────────────────────────
import gradio as gr

# ── Resolver (local import) ───────────────────────────────────────────────────
ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from resolver import resolve, haversine, _load_gazetteer

# ── Preload gazetteer ─────────────────────────────────────────────────────────
_load_gazetteer()

# ── Example inputs (covers EN / FR / KIN and various modifiers) ───────────────
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


# ── Core resolver function ────────────────────────────────────────────────────

def run_resolver(text: str):
    """Wrap resolve() and format outputs for Gradio."""
    if not text or not text.strip():
        return (
            "—", "—", "—", "—", "—", "—",
            "⚠️ Please enter a description.",
            _map_html(None, None, None),
        )

    t0 = time.perf_counter()
    result = resolve(text)
    latency_ms = (time.perf_counter() - t0) * 1000

    lat = result["lat"]
    lon = result["lon"]
    conf = result["confidence"]
    landmark = result["matched_landmark"]
    lang = result["language"]
    modifier = result["modifier"]
    escalate = result["escalate"]
    rationale = result["rationale"]

    # Confidence badge
    if conf >= 0.7:
        conf_badge = f"🟢 {conf:.2f} (High)"
    elif conf >= 0.4:
        conf_badge = f"🟡 {conf:.2f} (Medium)"
    else:
        conf_badge = f"🔴 {conf:.2f} (Low)"

    escalate_str = "⚠️ YES — Dispatch review recommended" if escalate else "✅ No"

    status = (
        f"✅ Resolved in {latency_ms:.1f} ms"
        if not escalate
        else f"⚠️ Escalated ({latency_ms:.1f} ms)"
    )

    map_html = _map_html(lat, lon, landmark)

    return (
        f"{lat:.6f}",
        f"{lon:.6f}",
        conf_badge,
        landmark,
        f"{lang.upper()} · modifier: {modifier}",
        escalate_str,
        f"{status}\n\n{rationale}",
        map_html,
    )


def _map_html(lat, lon, landmark):
    """Generate an embedded Leaflet map centered on the resolved point."""
    if lat is None:
        return "<div style='padding:20px;text-align:center;color:#6B7280'>Enter a description to see the map.</div>"

    return f"""
<div id="map-wrap" style="width:100%;height:380px;border-radius:12px;overflow:hidden;border:1px solid #E5E7EB">
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<div id="leafmap" style="width:100%;height:380px"></div>
<script>
(function(){{
  var map = L.map('leafmap').setView([{lat}, {lon}], 16);
  L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png',{{
    attribution:'© OpenStreetMap contributors'
  }}).addTo(map);
  var icon = L.divIcon({{
    html:'<div style="background:#2563EB;border:3px solid white;border-radius:50%;width:18px;height:18px;box-shadow:0 2px 8px rgba(0,0,0,0.4)"></div>',
    iconSize:[18,18], iconAnchor:[9,9]
  }});
  L.marker([{lat},{lon}],{{icon:icon}})
    .addTo(map)
    .bindPopup('<b>{landmark}</b><br/>{lat:.5f}, {lon:.5f}')
    .openPopup();
  L.circle([{lat},{lon}],{{radius:100,color:'#2563EB',fillOpacity:0.08}}).addTo(map);
}})();
</script>
</div>
""".replace("{landmark}", str(landmark)).replace("{lat:.5f}", f"{lat:.5f}").replace("{lon:.5f}", f"{lon:.5f}")


# ── Gazetteer explorer ────────────────────────────────────────────────────────

def list_landmarks(filter_type: str):
    gz = _load_gazetteer()
    if filter_type and filter_type != "All":
        gz = [lm for lm in gz if lm.type == filter_type]
    rows = [[lm.name, lm.type, lm.district, lm.lat, lm.lon] for lm in gz]
    return rows


LM_TYPES = ["All"] + sorted({lm.type for lm in _load_gazetteer()})

# ── UI ────────────────────────────────────────────────────────────────────────

CSS = """
body { font-family: 'IBM Plex Mono', monospace; background: #0F172A; }
.gradio-container { max-width: 960px; margin: auto; }
#title-block { text-align: center; padding: 24px 0 8px; }
#title-block h1 { color: #F1F5F9; font-size: 2rem; font-weight: 700; letter-spacing: -0.5px; }
#title-block p  { color: #94A3B8; font-size: 0.95rem; }
.output-label { font-size: 0.78rem; color: #64748B; text-transform: uppercase; letter-spacing: 0.05em; }
.result-card { background: #1E293B; border-radius: 10px; padding: 12px 16px; border: 1px solid #334155; }
"""

DESCRIPTION = """
**Informal Address Resolver** · AIMS KTT Hackathon T1.2  
Converts noisy multilingual delivery descriptions (English / French / Kinyarwanda) into GPS coordinates.  
*No GPU · No API · Fully offline · < 100 ms latency*
"""

with gr.Blocks(css=CSS, title="Informal Address Resolver") as demo:
    gr.HTML("""
    <div id="title-block">
      <h1>📍 Informal Address Resolver</h1>
      <p>AIMS KTT Hackathon · T1.2 · EN / FR / Kinyarwanda · CPU-only · &lt;100ms</p>
    </div>
    """)
    gr.Markdown(DESCRIPTION)

    with gr.Tabs():
        # ── Tab 1: Resolver ────────────────────────────────────────────────────
        with gr.Tab("🔍 Resolver"):
            with gr.Row():
                with gr.Column(scale=3):
                    text_in = gr.Textbox(
                        label="Address Description",
                        placeholder="e.g.  inyuma ya big pharmacy on RN3, red gate",
                        lines=2,
                    )
                    with gr.Row():
                        btn_resolve = gr.Button("Resolve →", variant="primary")
                        btn_clear = gr.Button("Clear", variant="secondary")

                    gr.Examples(
                        examples=EXAMPLES,
                        inputs=text_in,
                        label="📋 Try these examples",
                    )

            with gr.Row():
                out_lat  = gr.Textbox(label="Latitude",  interactive=False)
                out_lon  = gr.Textbox(label="Longitude", interactive=False)
                out_conf = gr.Textbox(label="Confidence", interactive=False)

            with gr.Row():
                out_lm   = gr.Textbox(label="Matched Landmark", interactive=False)
                out_lang = gr.Textbox(label="Language · Modifier", interactive=False)
                out_esc  = gr.Textbox(label="Escalation", interactive=False)

            out_status = gr.Textbox(label="Rationale", lines=3, interactive=False)
            out_map    = gr.HTML(label="Map")

            btn_resolve.click(
                fn=run_resolver,
                inputs=[text_in],
                outputs=[out_lat, out_lon, out_conf, out_lm, out_lang, out_esc, out_status, out_map],
            )
            btn_clear.click(
                fn=lambda: [""] * 7 + [""],
                outputs=[out_lat, out_lon, out_conf, out_lm, out_lang, out_esc, out_status, out_map],
            )

        # ── Tab 2: Batch ───────────────────────────────────────────────────────
        with gr.Tab("📦 Batch Resolver"):
            gr.Markdown("Enter one address per line. Results download as CSV.")
            batch_in  = gr.Textbox(label="Descriptions (one per line)", lines=8,
                                   placeholder="behind the hospital\ninyuma ya bus park\nderrière le marché")
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
                        "⚠️" if r["escalate"] else "✅",
                    ])
                return rows

            btn_batch.click(fn=run_batch, inputs=[batch_in], outputs=[batch_out])

        # ── Tab 3: Gazetteer ───────────────────────────────────────────────────
        with gr.Tab("🗺️ Gazetteer"):
            gr.Markdown("Browse the 50 landmark database powering the resolver.")
            type_filter = gr.Dropdown(choices=LM_TYPES, value="All", label="Filter by type")
            lm_table = gr.Dataframe(
                headers=["Name", "Type", "District", "Lat", "Lon"],
                value=list_landmarks("All"),
                interactive=False,
            )
            type_filter.change(fn=list_landmarks, inputs=[type_filter], outputs=[lm_table])

        # ── Tab 4: About ───────────────────────────────────────────────────────
        with gr.Tab("ℹ️ About"):
            gr.Markdown("""
## System Architecture

```
Input Text
    │
    ▼
1. Normalise      → lowercase, strip emoji, fold accents, collapse whitespace
    │
    ▼
2. Detect Language → keyword heuristics + optional langid (EN / FR / KIN)
    │
    ▼
3. Extract Candidates → fuzzy match (rapidfuzz WRatio or difflib fallback)
   against all names + aliases in gazetteer — returns top-5 with scores
    │
    ▼
4. Parse Modifier → scan for spatial phrases (behind/inyuma ya/derrière …)
   returns: key, offset_m, direction, confidence_bonus
    │
    ▼
5. Apply Offset   → deterministic lat/lon shift (10–60 m) in resolved direction
    │
    ▼
6. Score Confidence → weighted: fuzzy(45%) + modifier(25%) + spread(15%) + lang(15%)
    │
    ▼
7. Escalation Check → confidence < 0.30 or top score < 0.45 → flag for dispatcher
    │
    ▼
Output: { lat, lon, confidence, matched_landmark, rationale, escalate, language, modifier }
```

## Constraints Met
- ✅ CPU-only, no GPU
- ✅ No external API or LLM calls at runtime  
- ✅ Fully offline
- ✅ < 100 ms per resolve() call
- ✅ Libraries: rapidfuzz, regex, pandas, geopy, langid (all optional with stdlib fallback)

## Supported Modifiers

| Phrase (EN) | French | Kinyarwanda | Offset | Direction |
|---|---|---|---|---|
| behind | derrière | inyuma ya | 50 m | south |
| next to | à côté de | hafi ya | 20 m | east |
| opposite | en face de | imbere ya | 30 m | north |
| near | près de | hafi ya | 60 m | centroid |
| above | au-dessus de | hejuru ya | 40 m | north |
| below | en bas de | munsi ya | 40 m | south |

## Offline Correction Flow (Riders)
See `correction_flow.md` in the repository for the full product design.

## Repository
- GitHub: [your-username/informal-address-resolver](https://github.com)
- HuggingFace: [spaces/your-username/informal-address-resolver](https://huggingface.co)
            """)

if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=7860)
