# 🏍️ Correction Flow — Offline Rider Address Correction System

**AIMS KTT Hackathon · T1.2 · Product & Business Artifact**

---

## 1. Problem Context

Motorcycle delivery riders in Kabale and surrounding districts operate in conditions that make digital error reporting nearly impossible:

- **Connectivity**: 2G/3G, frequently dropping to no signal in valleys and hilly terrain
- **Literacy**: Variable — many riders are comfortable with smartphones but not fluent readers
- **Time pressure**: A rider mid-delivery cannot stop to type a paragraph
- **Power**: Phones may be at <20% battery during a shift

The resolver will occasionally return a wrong pin. The system must allow riders to **flag and correct errors silently, offline, in under 10 seconds**, without requiring typing.

---

## 2. Input Modality — 3-Button Correction UI

### Why 3 buttons?
- Works with one thumb, phone in hand
- No literacy required
- Works at any battery level
- Takes < 8 seconds end-to-end

### The Three Buttons

```
┌─────────────────────────────────────────────┐
│  📍 Delivered here?                         │
│                                             │
│  [ ✅ YES — Pin correct ]                  │
│  [ ❌ NO — Wrong location ]                │
│  [ ❓ I don't know ]                       │
└─────────────────────────────────────────────┘
```

If the rider taps **❌ NO — Wrong location**:

```
┌─────────────────────────────────────────────┐
│  Show me where you ARE:                     │
│                                             │
│  [ 📍 Use my GPS now ]   ← tap to capture  │
│  [ 📷 Photo of gate ]   ← optional         │
│  [ ⬅ Cancel ]                              │
└─────────────────────────────────────────────┘
```

The rider taps **📍 Use my GPS now** — the device captures current GPS coordinates and stamps the correction record. Done. The whole flow takes **5–8 seconds**.

### Optional Photo Assist
If the rider taps **📷 Photo of gate**, the device camera opens. The photo is compressed to < 80 KB (JPEG, 640×480) and queued alongside the GPS correction. This gives dispatchers a visual anchor to update the gazetteer.

---

## 3. Data Stored on Device (SQLite)

Each correction is written to a local SQLite database (`corrections.db`):

```sql
CREATE TABLE corrections (
    id           TEXT PRIMARY KEY,   -- UUID generated on device
    description_id TEXT,             -- original delivery description ID
    description_text TEXT,           -- full address text
    resolver_lat  REAL,              -- what the resolver returned
    resolver_lon  REAL,
    rider_lat     REAL,              -- GPS captured by rider
    rider_lon     REAL,
    photo_path    TEXT,              -- local path to compressed photo (nullable)
    confidence    REAL,              -- resolver confidence at time of error
    rider_id      TEXT,              -- anonymised rider identifier
    device_id     TEXT,              -- device fingerprint
    created_at    TEXT,              -- ISO-8601 timestamp
    synced        INTEGER DEFAULT 0  -- 0 = pending, 1 = uploaded
);
```

**Storage estimate per record**: ~400 bytes (no photo) · ~80 KB (with photo)

---

## 4. Offline Queue & Sync Strategy

### Queue Behaviour
- All records written immediately to SQLite with `synced = 0`
- Corrections accumulate silently — no data is lost if offline for hours or days
- On app foreground: check connectivity → if online → trigger sync

### Sync Trigger (in priority order)
1. App comes to foreground and network is available
2. Phone connects to WiFi
3. Manual "Sync now" button in settings

### Sync Protocol
```
Client → Server: POST /api/corrections/batch
Body: JSON array of unsynced records (batched, max 50 per request)
Headers: Authorization: Bearer <rider_token>

Server → Client: { accepted: [ids], rejected: [ids], errors: {id: reason} }

Client: marks accepted IDs as synced=1
        keeps rejected IDs in queue for retry
        logs errors silently
```

### Conflict Resolution Strategy

| Scenario | Resolution |
|---|---|
| Two riders flag same address same day | **Confidence-weighted merge**: the correction from the rider with higher GPS accuracy (HDOP < 3) wins. If tied, latest timestamp wins. |
| Rider submits correction > 7 days old | Flag for **manual dispatcher review** — GPS drift may have occurred |
| Correction moves pin > 500 m from resolver output | Flag as **outlier** — likely a rider GPS error or wrong delivery |
| Same description_id corrected 3+ times | **Auto-promote** to gazetteer review queue — suggests the landmark is misplaced in the database |

### Backend Deduplication
Server applies a spatial dedupe window: if two corrections for the same `description_id` land within 20 m of each other within 24 hours, only the higher-GPS-accuracy one is committed to the landmark update queue.

---

## 5. Data Volume Estimate per Rider per Month

| Component | Per delivery | Deliveries/day | Days/month | Monthly total |
|---|---|---|---|---|
| Correction record (no photo) | 400 B | 30 | 22 | ~264 KB |
| Photo (when taken, ~15% rate) | 80 KB | 4.5 photos | 22 | ~7.9 MB |
| Sync overhead (HTTP headers) | 2 KB/batch | 1 batch/day | 22 | ~44 KB |
| **Total** | | | | **~8.2 MB/month** |

At typical Uganda data costs (~UGX 10/MB on MTN), this is **< UGX 100/month per rider** (~$0.03 USD). Entirely negligible.

---

## 6. Cold Start — New District with 0 Gazetteer Entries

When deploying in a new district with no landmarks:

1. **Seed from OpenStreetMap**: Run a one-time OSM Overpass query for the district bounding box, extracting `amenity=*` nodes (hospitals, pharmacies, schools, markets). This takes < 2 minutes and typically yields 20–100 landmarks.

2. **Rider bootstrap**: Equip the first 5 riders with a "landmark tagging mode". When they reach a known location, they tap "Tag this place" → photo + GPS + voice label. After 2 weeks, the district has a ground-truth-calibrated gazetteer.

3. **Provisional resolver**: Until the gazetteer reaches 10 entries, the resolver returns `confidence < 0.3` for all queries and escalates everything to dispatcher voice confirmation. This is honest uncertainty, not silence.

---

## 7. Why This Is Cheaper Than Paper Bug Reports

Paper-based address correction in logistics contexts typically costs **$1.50–$4.00 per correction** when you account for: rider stopping time (~5 min = cost of fuel + wage), dispatcher re-entry time (~3 min), error rate in transcription (~12%), and postage/form printing. For an operation handling 500 corrections/month, that's **$750–$2,000/month**.

This system costs **< $0.10 per correction** — the marginal compute of a SQLite write + a batch HTTP POST. The accuracy is higher because GPS coordinates are machine-captured (no handwriting mis-reads), the latency from "rider flags error" to "backend updated" is **hours instead of days**, and every correction feeds directly into an improving gazetteer with zero human re-entry. At 500 corrections/month, the paper system costs ~100× more per correction and produces worse data. The break-even point against any smartphone-based setup is within the first month of deployment.

---

## 8. System Diagram

```
Rider Device (offline)                   Backend (cloud)
═══════════════════════                  ══════════════════
                                         
  Delivery App                           Correction API
  ┌──────────────┐                       ┌────────────────┐
  │ resolve()    │                       │ POST /batch    │
  │ ↓            │  ── WiFi/3G ─────→   │ Dedup + merge  │
  │ Show pin     │                       │ Gazetteer queue│
  │ ↓            │                       └────────────────┘
  │ 3-button UI  │
  │ ↓            │
  │ GPS capture  │
  │ ↓            │
  │ SQLite queue │
  └──────────────┘
```

---

*Artifact prepared for AIMS KTT Hackathon T1.2 — Informal Address Resolver*
