# DESIGN.md — Store Intelligence System

## Architecture Overview

The system has three independent pieces: a detection pipeline that reads video, a REST API that stores and serves events, and a Next.js dashboard that reads from the API. They're connected only through HTTP — the pipeline never touches the database directly.

```
Raw CCTV Clips (.mp4, 1080p)
         │
         ▼
┌─────────────────────────────────────────────────────────┐
│  Detection Pipeline  (pipeline/)                        │
│                                                         │
│  FrameExtractor  →  PersonDetector (YOLOv8n / MOG2)    │
│       │                                                 │
│       └→  ByteTracker (ByteTrack / IoU fallback)        │
│                │                                        │
│         ┌──────┴──────────────────┐                     │
│         ▼                         ▼                     │
│   ZoneMapper               DirectionClassifier          │
│   DwellAccumulator         StaffClassifier              │
│   QueueDepthCounter        ReIDTracker (stub)           │
│         │                                               │
│         └──────────→  EventEmitter                      │
└──────────────────────────┬──────────────────────────────┘
                           │  JSON batches (HTTP POST)
                           ▼
┌─────────────────────────────────────────────────────────┐
│  FastAPI  (app/)                                        │
│                                                         │
│  POST /events/ingest                                    │
│    validate (Pydantic) → dedup (event_id) → bulk insert │
│                           │                             │
│                    PostgreSQL 16                        │
│                           │                             │
│  GET /stores/{id}/metrics ─┤                            │
│  GET /stores/{id}/funnel   ├─  session builder          │
│  GET /stores/{id}/heatmap  │   + direct SQL aggregates  │
│  GET /stores/{id}/anomalies┘                            │
│  GET /health                                            │
└─────────────────────────────────────────────────────────┘
                           │  HTTP GET (polling)
                           ▼
              Next.js Dashboard (port 3000)
              MetricsPanel · HeatmapGrid · AnomalyFeed
```

---

## Data Flow — Tracing One Event End to End

Here's how a single customer entering a store produces a metric you can query from the API.

**1. Frame extraction**

`FrameExtractor` opens the entry camera clip with OpenCV, samples at 5fps, and timestamps each frame as `clip_start_utc + (frame_index / source_fps)`. The clip start is passed as a command-line argument to `process_store.py`.

**2. Person detection**

`PersonDetector` runs each frame through YOLOv8n (or MOG2 if YOLO isn't installed). If a person-class bounding box appears with confidence ≥ 0.3, it's kept. I kept the threshold at 0.3 because the spec explicitly said not to suppress low-confidence detections — false negatives in an entry zone are more costly than false positives.

**3. Tracking**

`ByteTracker` assigns a stable integer `track_id` across frames. The tracker holds lost tracks for 30 frames before deleting them, so a person who briefly steps behind a display pillar keeps the same ID.

**4. Direction classification**

`DirectionClassifier` reads the threshold line from `store_layout.json` and checks whether a track's last 3 centroid positions cross it from outside to inside (INBOUND) or inside to outside (OUTBOUND). Requiring 3 frames prevents a single noisy detection near the doorway from triggering a false entry.

**5. Event emission**

`ReIDTracker` assigns a string `visitor_id` to the track (currently a stub that always generates a new ID — full re-ID with appearance embeddings was deferred). `EventEmitter.entry_exit()` constructs an `EntryExitEvent` Pydantic object with the store code, camera ID, timestamp, and is_staff flag.

**6. Ingest**

`process_store.py` collects all events from a camera, then calls `POST /events/ingest` with batches of up to 400. The ingest service generates a deterministic `event_id` via `uuid.uuid5(NAMESPACE_URL, "{event_type}:{id_token}:{store_code}:{timestamp}")` for deduplication. Duplicate IDs are silently skipped with `ON CONFLICT (event_id) DO NOTHING`.

**7. Session reconstruction**

When `/stores/ST1076/metrics?for_date=2026-03-08` is called, the session builder queries all entry events for that date and store. For each entry, it finds the first matching exit (same `id_token`) and the effective session window. It then checks whether any zone_entered events fall within that window to determine `reached_zone_visit`, and whether any queue events fall within the window for `reached_billing` and `completed_purchase`. This time-window overlap approach is a simplification — ideally you'd track `id_token` → `track_id` across cameras, but entry events use `id_token` and zone events use `track_id`, and there's no explicit link between them.

**8. Response**

`compute_metrics()` counts distinct non-staff entry events as `unique_visitors`, divides completed_purchase sessions by total customer sessions for `conversion_rate`, and pairs zone_entered/zone_exited events by `(track_id, zone_id)` to compute `avg_dwell_per_zone`.

---

## AI-Assisted Decisions

### Decision 1: Discriminated union event schema

**The problem:** The sample events file contained three structurally different event types — entry/exit events (with `id_token`, `store_code`), zone events (with `track_id`, `store_id`, zone coordinates), and queue events (with `queue_event_id` UUID, timing fields). The question was how to model these in Pydantic.

**What the LLM suggested:** Use Pydantic v2's `Annotated[Union[EntryExitEvent, ZoneEvent, QueueEvent], Field(discriminator="event_type")]`. The discriminator would be the `event_type` string, and each sub-model would use `Literal["entry", "exit"]` etc. to constrain the allowed values.

**What I did:** Took this suggestion directly. The alternative was a single flat `StoreEvent` with all fields optional, which the original placeholder code had. The problem with the flat model is that it would accept an entry event with no `id_token` (because zone events don't have it, the field would be Optional). The discriminated union enforces that each event type has its required fields. I kept the `EventType` enum for the DB schema and query code, mapping from the wire format strings (`"entry"`, `"zone_entered"`) to enum values.

**Where I overrode it:** The LLM initially suggested keeping `dwell_ms` as a top-level field on all event types. I dropped it because the sample data didn't have it, and dwell time is computable from zone_entered/zone_exited pairs at query time rather than something the pipeline needs to pre-compute per frame.

---

### Decision 2: Single events table vs separate tables per event type

**The problem:** The three event types have very different schemas. Zone events have 10+ zone-specific fields that are irrelevant to entry events. I had to choose between a single denormalized table and three separate tables.

**What the LLM suggested:** Initially it suggested three separate tables (`entry_exit_events`, `zone_events`, `queue_events`) to avoid nullable columns and keep the schema clean.

**What I decided instead:** One `events` table with event-type-specific nullable columns, plus a `raw JSONB` column storing the original payload. My reasoning: every analytics query — session reconstruction, heatmap, funnel — needs to look across multiple event types together. With three tables, those queries would require `UNION ALL` or multiple round-trips. The nullable columns mean some rows have 10+ null fields, but the queries are simpler, indexes work cleanly on `(store_id, event_ts)`, and the raw JSONB column means I can always reprocess events if the schema changes. I used a UUID `event_id` column as the deduplication key across all types.

I added a partial index on `queue_event_id WHERE queue_event_id IS NOT NULL` since queue events already come with their own UUID and that's the natural dedup key for them.

---

### Decision 3: CORS gap discovered via debugging

**The problem:** After deploying the dashboard, the heatmap showed "No zone data" and the metrics showed "Loading… stale" even though `curl` requests from the terminal returned correct data. I spent a while assuming the API had a query bug before catching it.

**What the LLM diagnosed:** The FastAPI app had no `CORSMiddleware`. When the browser at `localhost:3000` sent requests to `localhost:8000`, the browser silently discarded the responses because there was no `Access-Control-Allow-Origin` header. The API was returning correct 200 responses — visible in the Docker logs — but the browser never let the JavaScript read them. Terminal `curl` calls worked because there's no same-origin enforcement outside the browser.

**What I changed:** Added `CORSMiddleware` to `main.py` with `allow_origins=["http://localhost:3000"]`. Five lines. The lesson here is that "it works from curl but not from the browser" almost always means CORS, and checking the API logs for request arrival is how you confirm it (requests were arriving and succeeding, responses were just being dropped client-side).

---

## Known Limitations

**Polygon calibration is manual.** `store_layout.json` contains estimated pixel coordinates for zone boundaries, drawn from the store layout PNG files. These haven't been verified against actual video frames frame-by-frame. For a production deployment, you'd want a calibration tool that overlays the polygon on a video frame and lets you drag vertices.

**Re-ID is a stub.** `ReIDTracker` currently assigns a new `visitor_id` for every track that crosses the entry threshold. Real re-entry detection requires comparing appearance embeddings (HOG or ResNet crop embeddings) against a buffer of exited visitors. This was deferred — the interface is in place, but the similarity matching isn't implemented.

**Session linking is approximate.** The session builder connects entry/exit events to zone events by time-window overlap rather than by a shared identifier. If two customers are in the store at the same time, their zone visits get cross-attributed. This is a limitation of the current pipeline, which doesn't propagate `id_token` through to zone events.

**Tests share the production database.** The test suite truncates the events table before each test via a synchronous psycopg2 connection. This means running tests while the API is serving real traffic will wipe the data.
