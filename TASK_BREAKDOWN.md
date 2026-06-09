# TASK BREAKDOWN
## Purplle Tech Challenge — Store Intelligence System

Tasks are grouped by layer and ordered by scoring weight descending within each group.
Effort is wall-clock hours for a solo developer working at principal-engineer pace.

---

## Layer 0 — Infrastructure

---

### T-00: Repo Scaffold + Docker Compose

**Objective**
Create the repository skeleton and bring up the full service graph so every subsequent task has a running target from the start.

**Inputs**
- Suggested layout from spec (`/pipeline`, `/app`, `/tests`, `/docs`)
- Stack: FastAPI, PostgreSQL, Next.js

**Outputs**
- `docker-compose.yml` with services: `api` (FastAPI), `db` (PostgreSQL 16), `dashboard` (Next.js)
- `pipeline/` directory with placeholder files
- `app/` directory with placeholder files
- `.env.example` with `DATABASE_URL`, `LOG_LEVEL`, `STAFF_COLOR_HEX`

**Dependencies**
- None

**Estimated Effort**
1 hour

**Acceptance Criteria**
- `docker compose up` starts without error on a clean machine
- `docker compose ps` shows all services healthy
- `GET http://localhost:8000/health` returns HTTP 200 (stub response is acceptable at this stage)
- No hardcoded credentials; all secrets via environment variables

---

### T-01: PostgreSQL Schema + Migrations

**Objective**
Define the authoritative data model. All API compute queries depend on this schema being correct and indexed from the start.

**Inputs**
- Event schema from spec (all fields)
- API endpoints and the queries they require (metrics, funnel, heatmap, anomalies)

**Outputs**
- `alembic/` migration directory
- `events` table: event_id UUID PK, store_id, camera_id, visitor_id, event_type ENUM, timestamp TIMESTAMPTZ, zone_id, dwell_ms BIGINT, is_staff BOOLEAN, confidence FLOAT, metadata JSONB
- `pos_transactions` table: transaction_id, store_id, timestamp, basket_value_inr NUMERIC
- Indexes: `(store_id, timestamp)`, `(store_id, visitor_id, timestamp)`, `(event_type, store_id)`, `event_id` UNIQUE
- `alembic upgrade head` runs cleanly in the `db` container

**Dependencies**
- T-00

**Estimated Effort**
1.5 hours

**Acceptance Criteria**
- `alembic upgrade head` completes without error from a fresh database
- `\d events` in psql shows all columns with correct types
- All three indexes present
- `alembic downgrade -1` cleanly reverses the migration

---

## Layer 1 — Event Contract

---

### T-02: Pydantic Event Models

**Objective**
Implement the single authoritative Pydantic model for the event schema. All pipeline emission and API ingestion use this model; a mismatch here propagates everywhere.

**Inputs**
- Event schema definition from spec (event_id, store_id, camera_id, visitor_id, event_type, timestamp, zone_id, dwell_ms, is_staff, confidence, metadata)
- Event type catalogue: ENTRY, EXIT, ZONE_ENTER, ZONE_EXIT, ZONE_DWELL, BILLING_QUEUE_JOIN, BILLING_QUEUE_ABANDON, REENTRY

**Outputs**
- `app/models.py`:
  - `EventType` Enum with all 8 values
  - `EventMetadata` model: queue_depth (Optional[int]), sku_zone (Optional[str]), session_seq (int)
  - `StoreEvent` model: all top-level fields, validators for UUID format on event_id, ISO-8601 UTC on timestamp, confidence in [0.0, 1.0]
  - `IngestBatch` model: list of StoreEvent, max 500 items
  - `IngestResponse` model: accepted, rejected, errors list

**Dependencies**
- T-01

**Estimated Effort**
1 hour

**Acceptance Criteria**
- Every field from the spec schema is present with the correct type
- A valid event from `sample_events.jsonl` deserializes without error
- A malformed event (missing visitor_id, non-UUID event_id) raises a ValidationError with a field-specific message
- `zone_id` is nullable (null for ENTRY/EXIT events)
- `dwell_ms` is 0 for instantaneous events, not null

---

## Layer 2 — Detection Pipeline

---

### T-04: YOLOv8 Person Detector

**Objective**
Detect all persons in each video frame. This is the source of truth for visitor counts; accuracy here directly determines 10 of 30 Part A points.

**Inputs**
- Video frame (numpy array, 1080p)
- YOLOv8 model weights (yolov8n.pt for speed; yolov8m.pt if time permits)
- Confidence threshold parameter (default 0.3 — spec says do not suppress low-confidence detections)

**Outputs**
- Per-frame list of detections: bounding box (x1, y1, x2, y2), confidence, class_id (person = 0)
- All detections above threshold passed through; confidence value preserved in output

**Dependencies**
- T-03

**Estimated Effort**
2 hours

**Acceptance Criteria**
- Processes one 1080p frame in < 200ms on CPU (yolov8n)
- Returns zero detections on a genuinely empty frame
- Returns ≥ 1 detection when a single visible person is present
- Low-confidence detections (0.3–0.5) are included in output, not silently dropped
- Detection results are deterministic given the same frame and weights

---

### T-03: Frame Extractor

**Objective**
Decode video clips into frames with accurate wall-clock timestamps. Every event timestamp in the system derives from the clip start time plus the frame offset.

**Inputs**
- Video file path
- Clip start timestamp (from filename or config)
- Sample rate parameter (default 5fps for entry/floor; 3fps for billing)

**Outputs**
- Iterator of `(frame: np.ndarray, timestamp: datetime)` tuples
- `timestamp` = clip_start_utc + timedelta(seconds=frame_index / original_fps)

**Dependencies**
- T-00

**Estimated Effort**
1.5 hours

**Acceptance Criteria**
- First frame timestamp equals the configured clip start time
- Frame at index N has timestamp = start + N/fps seconds (accurate to 10ms)
- Sampling at 5fps from a 15fps clip yields 3× fewer frames
- Does not load the entire clip into memory; streams frame by frame
- Handles end-of-file cleanly without exception

---

### T-05: ByteTrack Multi-Object Tracker

**Objective**
Assign stable track IDs to each detected person across frames. Track continuity is the foundation for session identity, zone transitions, and re-entry detection.

**Inputs**
- Per-frame list of YOLOv8 bounding boxes and confidences (from T-04)
- ByteTrack hyperparameters: track_thresh=0.5, track_buffer=30, match_thresh=0.8

**Outputs**
- Per-frame list of tracked objects: track_id (int, stable across frames), bounding box, confidence, age (frames since first seen)
- Track ID is assigned once and does not change while the track is active
- Lost tracks held for `track_buffer` frames before deletion

**Dependencies**
- T-04

**Estimated Effort**
2 hours

**Acceptance Criteria**
- A single person walking across the full frame retains the same track_id from entry to exit
- Two people crossing paths do not swap track IDs
- A person who disappears for 3 frames (partial occlusion) reacquires the same track_id
- Tracks created for a single frame and never seen again are discarded (ghost detection filter)
- Tracker state resets cleanly between clips

---

### T-06: Zone Mapper

**Objective**
Map each tracked person's bounding box to a named zone for each camera. Zone transitions are the source of ZONE_ENTER, ZONE_EXIT, and ZONE_DWELL events.

**Inputs**
- `store_layout.json`: per-camera zone definitions with polygon vertices in pixel coordinates
- Per-frame tracked bounding boxes from T-05
- Camera ID (determines which zone set to load)

**Outputs**
- Per-track current zone_id (string matching zone names in store_layout.json, or null if between zones)
- Zone transition log: list of `(track_id, from_zone, to_zone, timestamp)` tuples emitted when zone changes

**Dependencies**
- T-05

**Estimated Effort**
2 hours

**Acceptance Criteria**
- Centroid of bounding box used for point-in-polygon test (not full box)
- A person simultaneously in overlapping zones is assigned to the more specific (smaller area) zone
- A person between defined zones returns zone_id = null; no spurious ZONE_ENTER events
- Zone polygon coordinates load correctly from store_layout.json for all 5 stores
- Returns correct zone for all 4 corners of a defined polygon (boundary included)

---

### T-07: Entry/Exit Direction Classifier

**Objective**
Determine whether a person crossing the entry threshold is entering (inbound) or exiting (outbound). This is the primary source of 10 of 30 Part A points.

**Inputs**
- Entry threshold line coordinates from store_layout.json (camera_id = entry camera)
- Track trajectory: centroid positions over the last N frames from T-05
- Minimum trajectory length: 3 frames

**Outputs**
- Direction: `INBOUND` or `OUTBOUND` per track crossing event
- Crossing timestamp: frame timestamp when centroid crossed the threshold line

**Dependencies**
- T-05, T-06

**Estimated Effort**
2.5 hours

**Acceptance Criteria**
- INBOUND: centroid trajectory moves from outside-store side to inside-store side across the threshold line
- OUTBOUND: centroid trajectory moves from inside to outside
- Requires ≥ 3 frames of trajectory before firing; does not fire on single-frame detections
- Two people entering simultaneously produce two independent direction events
- Does not double-fire if a person pauses near the threshold

---

### T-08: Staff Classifier

**Objective**
Classify each tracked person as staff or customer. Staff events must be flagged `is_staff=true` and excluded from customer-facing metrics.

**Inputs**
- Per-frame bounding box crops from T-05
- Staff appearance reference: configurable upper-body color range (HSV) from `.env` or `store_layout.json`
- Optional: VLM prompt for sample frames to establish color reference

**Outputs**
- Per-track `is_staff` boolean, persisted for the lifetime of the track
- Classification is sticky: once a track is classified as staff, it remains staff

**Dependencies**
- T-05

**Estimated Effort**
2 hours

**Acceptance Criteria**
- A track wearing the configured staff color is classified `is_staff=true` in ≥ 80% of frames
- `is_staff` classification is assigned at the track level, not per-frame (no flipping)
- A customer in non-staff colors is classified `is_staff=false`
- The classifier is configurable without code changes (color range in env or config file)
- Downstream: events with `is_staff=true` are emitted but excluded from `/metrics` unique_visitors

---

### T-09: Dwell Accumulator

**Objective**
Track continuous time-in-zone per track to emit ZONE_DWELL events at 30-second intervals and compute dwell_ms for all zone events.

**Inputs**
- Zone transition log from T-06 (track_id, zone_id, enter_timestamp, exit_timestamp)

**Outputs**
- ZONE_DWELL events: emitted for each 30-second interval of continuous zone presence; dwell_ms = cumulative ms in that zone interval
- dwell_ms populated on ZONE_ENTER (0), ZONE_EXIT (total ms in zone), ZONE_DWELL (ms since last dwell event)

**Dependencies**
- T-06

**Estimated Effort**
1 hour

**Acceptance Criteria**
- A track in a zone for 90 seconds produces 3 ZONE_DWELL events (at 30s, 60s, 90s)
- A track in a zone for 29 seconds produces 0 ZONE_DWELL events
- Zone exit interrupts the dwell counter; re-entry starts a new counter
- dwell_ms on ZONE_EXIT equals (exit_timestamp − enter_timestamp) in milliseconds

---

### T-10: Billing Queue Depth Counter

**Objective**
Track the number of people simultaneously present in the billing zone to populate queue_depth in BILLING_QUEUE_JOIN events and feed the BILLING_QUEUE_SPIKE anomaly.

**Inputs**
- Zone assignment stream from T-06 (billing zone tracks)
- Billing zone name from store_layout.json

**Outputs**
- Current queue_depth integer: number of tracks in billing zone at each frame
- BILLING_QUEUE_JOIN event trigger: when a track enters billing zone and current queue_depth > 0

**Dependencies**
- T-06, T-09

**Estimated Effort**
1.5 hours

**Acceptance Criteria**
- queue_depth = 0 when billing zone is empty
- queue_depth increments on each new BILLING_QUEUE_JOIN
- queue_depth decrements on each ZONE_EXIT from billing zone
- A single person entering an empty billing zone gets queue_depth=0 on their JOIN event (they are the first, not joining a queue)
- Counter does not include staff tracks

---

### T-11: Re-ID / REENTRY Detector

**Objective**
Detect when a previously exited person re-enters the store. The same physical person re-entering must produce a REENTRY event, not a second ENTRY — re-entry inflation is explicitly called out in the spec as a known vendor problem.

**Inputs**
- Appearance descriptor buffer: HOG or ResNet-based crop embedding for each exited track, retained for 10 minutes post-exit
- New track appearance descriptor at the entry threshold
- Exit buffer expiry: 10 minutes (configurable)

**Outputs**
- visitor_id: for a re-entering person, the same visitor_id as their prior session
- REENTRY event instead of ENTRY event for matched re-entry
- New visitor_id for a genuinely new visitor

**Dependencies**
- T-07, T-08

**Estimated Effort**
3 hours

**Acceptance Criteria**
- A person exiting and re-entering within 5 minutes produces one ENTRY + one REENTRY, not two ENTRY events
- Two different people entering consecutively from the same direction do not get merged visitor_ids
- A person re-entering after 11 minutes (past buffer expiry) gets a new ENTRY, not REENTRY
- The buffer is bounded: does not grow unbounded over a 20-minute clip
- is_staff tracks are excluded from the re-ID buffer

---

### T-12: Cross-Camera Deduplicator

**Objective**
Prevent the same physical person from being counted twice when the entry camera and floor camera fields of view overlap. This is the "camera angle overlap" edge case from the spec.

**Inputs**
- Event stream from both entry camera and floor camera for the same store
- Overlap zone definition: area visible in both cameras (from store_layout.json)
- Temporal window: 5 seconds

**Outputs**
- Deduplicated event stream: ZONE_ENTER events from the floor camera suppressed if the same visitor_id already appeared in the entry camera within the temporal window in the overlap zone

**Dependencies**
- T-07, T-11

**Estimated Effort**
2.5 hours

**Acceptance Criteria**
- A person visible in both cameras within 5 seconds produces one ENTRY event, not two
- People visible in only one camera are unaffected
- Dedup does not suppress floor camera events for a different person entering around the same time
- Suppressed events are logged (for audit), not silently discarded

---

### T-13: Event Emitter

**Objective**
Translate the per-frame pipeline state (tracks, zone assignments, direction, staff flags, dwell counters, queue depth) into the exact event schema defined in the spec. This is the final integration point for all detection modules.

**Inputs**
- Track state from T-05 (track_id, bounding box, confidence)
- Zone assignment from T-06 (current zone, transitions)
- Direction from T-07 (INBOUND/OUTBOUND)
- Staff flag from T-08
- Dwell events from T-09
- Queue depth from T-10
- visitor_id from T-11 (new or re-identified)
- Clip metadata: store_id, camera_id, clip_start_utc

**Outputs**
- Stream of `StoreEvent` objects (T-02 model)
- event_id: UUID v4, generated at emission time
- timestamp: clip_start_utc + frame_offset
- session_seq: ordinal counter per visitor_id, incremented per event emitted for that visitor

**Dependencies**
- T-02, T-06, T-07, T-08, T-09, T-10, T-11

**Estimated Effort**
1.5 hours

**Acceptance Criteria**
- Every emitted event validates against the Pydantic StoreEvent model
- event_ids are globally unique across all clips
- ENTRY/EXIT events have zone_id=null
- ZONE_DWELL events have dwell_ms > 0
- session_seq is monotonically increasing per visitor_id within a session
- BILLING_QUEUE_JOIN events have metadata.queue_depth as a non-null integer
- Emitter handles the empty-store case (no tracks) without exception

---

### T-14: Pipeline Runner (run.sh)

**Objective**
Provide a single command that processes all clips for a store and emits events. This is the README-documented command; it must work verbatim on a reviewer's machine.

**Inputs**
- Directory of video clips
- `store_layout.json`
- `pos_transactions.csv`
- API base URL (for posting events)

**Outputs**
- All events from all clips posted to `POST /events/ingest`
- Progress output to stdout (clip name, events emitted, API response)
- Exit code 0 on success, non-zero on any clip failure

**Dependencies**
- T-13, T-16

**Estimated Effort**
1 hour

**Acceptance Criteria**
- `bash pipeline/run.sh ./data/store1 http://localhost:8000` processes all 3 clips for that store
- Output includes event counts per clip
- Failure on one clip does not abort processing of the others
- Script is re-runnable (idempotent, due to T-16)

---

## Layer 3 — Intelligence API

---

### T-15: FastAPI App Scaffold

**Objective**
Set up the FastAPI application with routing, database connection pooling, lifespan management, and the overall request/response structure all endpoints share.

**Inputs**
- PostgreSQL connection string from environment
- Router modules: ingest, metrics, funnel, heatmap, anomalies, health

**Outputs**
- `app/main.py`: FastAPI app, lifespan context (DB pool open/close), router registration
- `app/db.py`: asyncpg connection pool, `get_db()` dependency
- Startup log: confirms DB connection, logs pool size

**Dependencies**
- T-01

**Estimated Effort**
1.5 hours

**Acceptance Criteria**
- App starts in < 3 seconds
- DB connection failure at startup logs a warning but does not crash the process
- `GET /health` returns 200 (stub) immediately after startup
- Routers are importable without circular dependency errors

---

### T-16: POST /events/ingest

**Objective**
Ingest batches of events from the detection pipeline. This endpoint must be idempotent by event_id, handle partial failures gracefully, and be the acceptance gate endpoint that scoring depends on.

**Inputs**
- `IngestBatch` (T-02): list of up to 500 `StoreEvent` objects
- PostgreSQL events table (T-01)

**Outputs**
- `IngestResponse`: `{accepted: int, rejected: int, errors: [{event_id, field, message}]}`
- HTTP 200 even on partial failure
- HTTP 422 only if the top-level batch structure is invalid (not individual events)

**Dependencies**
- T-02, T-15

**Estimated Effort**
2 hours

**Acceptance Criteria**
- Posting the same batch twice returns `accepted=N, rejected=0` both times (idempotent via ON CONFLICT DO NOTHING on event_id)
- A batch with 499 valid events and 1 invalid event returns accepted=499, rejected=1, with error detail for the invalid event
- Bulk insert completes in < 500ms for 500 events
- `pos_transactions` ingestion: a separate `POST /pos/ingest` endpoint or loaded at startup from CSV (document the choice)
- HTTP 503 returned (not 500) when database is unreachable

---

### T-17: Session State Builder

**Objective**
Reconstruct visitor sessions from the event stream for use by /funnel and /metrics. Session logic is the most complex query in the system; getting it wrong affects 10 of 35 Part B points.

**Inputs**
- Events table filtered by store_id and date range
- Session boundary rules: ENTRY opens, EXIT closes; 30-minute idle timeout closes if no EXIT

**Outputs**
- `sessions` view or materialized query result: visitor_id, session_start, session_end, is_staff, reached_zone_visit (bool), reached_billing (bool), completed_purchase (bool)
- POS correlation: a session with a BILLING_QUEUE_JOIN event within 5 minutes before a pos_transaction timestamp at the same store is marked `completed_purchase=true`
- REENTRY events do not create new sessions; they extend the existing session for that visitor_id

**Dependencies**
- T-01, T-16

**Estimated Effort**
2.5 hours

**Acceptance Criteria**
- A visitor who enters and exits produces exactly one session
- A visitor who re-enters produces one session with REENTRY noted, not two sessions
- Staff sessions are present in the raw data but excluded from customer session counts
- A session without an EXIT event is closed after 30 minutes of idle
- POS correlation is time-window based only; no customer identity matching

---

### T-18: GET /stores/{id}/metrics

**Objective**
Return real-time store KPIs. This is the primary scoring endpoint and the one tested by the acceptance gate.

**Inputs**
- `store_id` path parameter
- Session data from T-17 (today's sessions only)
- pos_transactions for today

**Outputs**
```json
{
  "store_id": "...",
  "date": "...",
  "unique_visitors": 142,
  "conversion_rate": 0.38,
  "avg_dwell_per_zone": {"SKINCARE": 45200, "HAIRCARE": 31000},
  "current_queue_depth": 3,
  "abandonment_rate": 0.12
}
```

**Dependencies**
- T-17

**Estimated Effort**
2 hours

**Acceptance Criteria**
- `unique_visitors` counts distinct visitor_ids with `is_staff=false` in customer sessions today
- `conversion_rate` = sessions with `completed_purchase=true` / total customer sessions; returns 0.0 not null when no purchases
- `avg_dwell_per_zone` returns an empty dict (not null) when no dwell events exist
- `current_queue_depth` reflects the most recent billing queue depth event
- Returns valid response for a store with zero visitors today (all counts 0, rates 0.0)
- Response time < 200ms for up to 10,000 events

---

### T-19: GET /stores/{id}/funnel

**Objective**
Return the 4-stage conversion funnel. Session deduplication is explicitly scored; re-entrants must not inflate the Entry stage count.

**Inputs**
- Session data from T-17

**Outputs**
```json
{
  "store_id": "...",
  "stages": [
    {"stage": "ENTRY", "count": 142, "drop_off_pct": 0.0},
    {"stage": "ZONE_VISIT", "count": 118, "drop_off_pct": 16.9},
    {"stage": "BILLING_QUEUE", "count": 64, "drop_off_pct": 45.8},
    {"stage": "PURCHASE", "count": 54, "drop_off_pct": 15.6}
  ]
}
```

**Dependencies**
- T-17

**Estimated Effort**
2 hours

**Acceptance Criteria**
- Stage counts are monotonically non-increasing (ENTRY ≥ ZONE_VISIT ≥ BILLING_QUEUE ≥ PURCHASE)
- `drop_off_pct` at ENTRY is always 0.0
- A visitor who re-enters is counted once at the ENTRY stage
- A visitor who visited a zone but not billing appears in ZONE_VISIT but not BILLING_QUEUE
- All stages return 0 counts for an empty store (no null values)

---

### T-20: GET /stores/{id}/heatmap

**Objective**
Return zone-level engagement data normalized for frontend grid rendering.

**Inputs**
- Events with type ZONE_ENTER and ZONE_DWELL for the store, filtered to `is_staff=false`
- Zone list from store_layout.json

**Outputs**
```json
{
  "store_id": "...",
  "data_confidence": true,
  "zones": [
    {"zone_id": "SKINCARE", "visit_count": 98, "avg_dwell_ms": 45200, "score": 87},
    {"zone_id": "HAIRCARE", "visit_count": 34, "avg_dwell_ms": 18000, "score": 31}
  ]
}
```

**Dependencies**
- T-17

**Estimated Effort**
1.5 hours

**Acceptance Criteria**
- `score` is normalized 0–100 across all zones in the response (max zone = 100)
- `data_confidence: false` when total unique customer sessions in the window < 20
- All zones from store_layout.json appear in the response, even those with zero visits (score=0)
- Staff visits excluded from counts
- avg_dwell_ms is 0 (not null) for a zone with visits but no dwell events

---

### T-21: GET /stores/{id}/anomalies

**Objective**
Detect and surface active operational anomalies. Severity classification and `suggested_action` string are required per spec.

**Inputs**
- Current queue depth from events table
- Historical conversion rates (7-day rolling average from events)
- Zone visit timestamps for dead zone detection (last 30 minutes)

**Outputs**
```json
{
  "store_id": "...",
  "anomalies": [
    {
      "type": "BILLING_QUEUE_SPIKE",
      "severity": "WARN",
      "detail": "Queue depth 7 for 4 minutes",
      "suggested_action": "Open additional billing counter"
    }
  ]
}
```

**Dependencies**
- T-17, T-18

**Estimated Effort**
2 hours

**Acceptance Criteria**
- BILLING_QUEUE_SPIKE fires when queue_depth > 5 for > 3 continuous minutes; severity=WARN at depth 5–8, CRITICAL at >8
- CONVERSION_DROP fires when today's conversion_rate < (7-day avg × 0.7); severity=WARN; returns INFO when < 7 days of history exist
- DEAD_ZONE fires for each zone with zero ZONE_ENTER events in the past 30 minutes during open hours; severity=INFO
- Each anomaly includes a non-empty `suggested_action` string
- Returns empty `anomalies: []` (not null) when no anomalies are active
- Anomalies are computed at query time, not cached from a background job

---

### T-22: GET /health

**Objective**
Provide an accurate service health endpoint for on-call use. Inaccurate health data is worse than no health data.

**Inputs**
- Database connection state
- Latest event timestamp per store from events table

**Outputs**
```json
{
  "status": "OK",
  "database": "connected",
  "stores": {
    "STORE_BLR_002": {
      "last_event_at": "2026-03-03T14:41:55Z",
      "feed_status": "OK"
    },
    "STORE_BLR_003": {
      "last_event_at": "2026-03-03T14:29:00Z",
      "feed_status": "STALE_FEED"
    }
  }
}
```

**Dependencies**
- T-15

**Estimated Effort**
1 hour

**Acceptance Criteria**
- `feed_status: STALE_FEED` when the most recent event for a store is > 10 minutes old
- `database: "unreachable"` and HTTP 503 when DB connection fails
- Response time < 100ms regardless of event volume
- A store that has never received events appears with `last_event_at: null` and `feed_status: NO_DATA`

---

## Layer 4 — Production Readiness

---

### T-23: Structured Logging Middleware

**Objective**
Emit a single structured JSON log line per request. Required fields are specified in the spec; this is evaluated under Part C structured logs.

**Inputs**
- Every inbound HTTP request
- Request context: path, method, path params

**Outputs**
Per-request log line (JSON):
```json
{
  "trace_id": "uuid",
  "store_id": "STORE_BLR_002",
  "endpoint": "/stores/{id}/metrics",
  "method": "GET",
  "latency_ms": 42,
  "event_count": null,
  "status_code": 200
}
```

**Dependencies**
- T-15

**Estimated Effort**
1 hour

**Acceptance Criteria**
- Every request produces exactly one log line
- `event_count` is populated (not null) only for `POST /events/ingest`, with the accepted count
- `trace_id` is unique per request and present in both the log line and the response header (`X-Trace-Id`)
- `store_id` extracted from path parameter; null for endpoints without it
- Log output is to stdout (captured by Docker)

---

### T-24: Graceful Degradation Handler

**Objective**
Prevent raw exceptions and stack traces from reaching API consumers. This is a production-readiness gate item.

**Inputs**
- All unhandled exceptions from route handlers
- Database connection errors (asyncpg.PostgresConnectionError)

**Outputs**
- HTTP 503 with body `{"error": "SERVICE_UNAVAILABLE", "detail": "..."}` on DB failure
- HTTP 422 with field-level errors on validation failure (Pydantic already handles this)
- HTTP 500 with body `{"error": "INTERNAL_ERROR", "trace_id": "..."}` on unexpected errors; no stack trace in body

**Dependencies**
- T-15, T-23

**Estimated Effort**
1 hour

**Acceptance Criteria**
- Stopping the DB container while the API is running: next request returns 503 with structured body
- No response body contains a Python stack trace or internal file path
- `trace_id` in error responses matches the `X-Trace-Id` response header
- Validation errors from malformed events return HTTP 422 with per-field messages, not 500

---

### T-25: Test Suite — Detection Pipeline

**Objective**
Cover detection pipeline logic with automated tests. Spec requires >70% statement coverage and specific edge case handling.

**Inputs**
- `sample_events.jsonl` as fixture data
- Mocked video frames (synthetic numpy arrays with known patterns)

**Outputs**
- `tests/test_pipeline.py` with prompt block header
- Test cases: schema validation, entry/exit pair, group entry (3 people → 3 ENTRY events), staff exclusion (is_staff=true excluded from customer counts), REENTRY vs second ENTRY, empty clip (no events, no crash), confidence passthrough (low-conf event included not suppressed)

**Dependencies**
- T-13, T-11

**Estimated Effort**
2.5 hours

**Acceptance Criteria**
- All 7 test cases pass
- Prompt block at top of file: `# PROMPT: ...` / `# CHANGES MADE: ...`
- No test mocks the database
- Tests run in < 30 seconds (no actual video processing)
- `pytest tests/test_pipeline.py` exits 0

---

### T-26: Test Suite — API

**Objective**
Cover API endpoints with automated tests against a real (test) database. Idempotency and edge cases are explicitly required by the spec.

**Inputs**
- Test PostgreSQL database (spun up via docker-compose test profile)
- Fixture event payloads for each edge case

**Outputs**
- `tests/test_ingest.py`: idempotency test, partial failure test, batch size limit (501 events → 422)
- `tests/test_metrics.py`: normal case, zero-purchase store, all-staff clip (unique_visitors=0), empty store
- `tests/test_funnel.py`: re-entry not double-counted, stages monotonically non-increasing
- `tests/test_anomalies.py`: queue spike trigger, dead zone trigger, conversion drop trigger

**Dependencies**
- T-16, T-17, T-18, T-19, T-20, T-21, T-22

**Estimated Effort**
2.5 hours

**Acceptance Criteria**
- All test files have prompt block headers
- `pytest tests/ --cov=app --cov-report=term` shows ≥ 70% statement coverage
- Idempotency test: post same 10-event batch twice; both return `accepted=10, rejected=0`
- All-staff clip test: `unique_visitors=0`, `conversion_rate=0.0`
- Tests use a dedicated test database, not the production DB

---

### T-27: README.md

**Objective**
Provide setup instructions that work in exactly 5 commands on a clean machine. This is the acceptance gate documentation requirement.

**Inputs**
- Final docker-compose.yml
- Pipeline run command from T-14
- API base URL

**Outputs**
- `README.md` with sections:
  1. Prerequisites (Docker, Docker Compose; no other dependencies)
  2. Setup (5 commands: clone, place dataset, compose up, run pipeline, verify)
  3. Running detection pipeline: exact command with parameters
  4. Verifying the API: `curl` command for `/health` and `/stores/{id}/metrics`
  5. Running tests: `docker compose run api pytest`
  6. Dashboard URL (if Part E completed)

**Dependencies**
- T-00, T-14, T-15

**Estimated Effort**
1.5 hours

**Acceptance Criteria**
- A team member who did not write the system can follow the README and reach a working API in < 15 minutes
- The 5 setup commands are numbered and copy-pasteable
- No step requires anything beyond Docker and Docker Compose
- The README accurately documents where detection pipeline output goes (file or direct API post)

---

## Layer 5 — AI Engineering

---

### T-28: DESIGN.md

**Objective**
Document the architecture and provide the AI-Assisted Decisions section required by Part D. Generic AI-generated text is penalised; specific decisions with personal reasoning are rewarded.

**Inputs**
- Completed system architecture
- 2–3 specific decisions where an LLM shaped the design

**Outputs**
- `docs/DESIGN.md`:
  - ASCII architecture diagram
  - Data flow description (frame → event → DB → API response)
  - AI-Assisted Decisions section: 3 decisions, each with: the LLM's suggestion, whether you agreed or overrode it, and why

**Dependencies**
- All implementation tasks

**Estimated Effort**
2 hours

**Acceptance Criteria**
- > 250 words (acceptance gate requirement)
- AI-Assisted Decisions section names specific modules (not generic "I used AI")
- At least one decision where the LLM suggestion was overridden with documented reasoning
- No section reads as generic AI-generated filler

---

### T-29: CHOICES.md

**Objective**
Document the three required architectural decisions with full reasoning. The follow-up video questions will be generated directly from this document.

**Inputs**
- Decision 1: YOLOv8 model selection (alternatives: YOLOv9, RT-DETR, MediaPipe)
- Decision 2: Event schema design (specifically: REENTRY vs second ENTRY, BILLING_QUEUE_ABANDON correlation approach)
- Decision 3: One API architecture choice (e.g., session computation: on-the-fly query vs materialized view; or synchronous ingest vs queue-based)

**Outputs**
- `docs/CHOICES.md`:
  - Three decision sections, each: options considered, what AI suggested, what was chosen, why

**Dependencies**
- All implementation tasks

**Estimated Effort**
2 hours

**Acceptance Criteria**
- > 250 words (acceptance gate requirement)
- Each decision explicitly states: options considered, AI's suggestion, final choice, reasoning
- The reasoning is specific to the dataset and constraints (not generic trade-off boilerplate)
- If a VLM was used for zone classification or staff detection, the prompt is quoted verbatim

---

### T-30: Prompt Blocks in Test Files

**Objective**
Add the required prompt block headers to all test files. This is a mechanical task but is explicitly evaluated under Part D.

**Inputs**
- Completed test files from T-25 and T-26
- The AI prompts actually used to generate the test scaffolding

**Outputs**
- Header comment block at the top of each test file:
```python
# PROMPT: <exact prompt used to generate this test file>
# CHANGES MADE: <what was added, removed, or corrected after AI generation>
```

**Dependencies**
- T-25, T-26

**Estimated Effort**
0.5 hours

**Acceptance Criteria**
- Every file in `tests/` has a prompt block
- CHANGES MADE section is non-empty (identifies at least one specific correction)
- Prompts are the actual prompts used, not reconstructed summaries

---

## Layer 6 — Live Dashboard (Bonus, +10 pts)

---

### T-31: Next.js App Scaffold

**Objective**
Create the Next.js application with routing, API client, and the store selector needed by the dashboard components.

**Inputs**
- Next.js 14 (App Router)
- FastAPI base URL (from environment)

**Outputs**
- `dashboard/` Next.js project
- Store selector component (dropdown of store IDs)
- API client module (`fetch` wrapper for all Intelligence API endpoints)
- `dashboard` service added to docker-compose.yml

**Dependencies**
- T-15

**Estimated Effort**
1.5 hours

**Acceptance Criteria**
- `docker compose up` starts the dashboard on port 3000
- Store selector loads store IDs from a config or the /health endpoint
- API client handles 503 gracefully (shows "API unavailable" state, not a crashed page)

---

### T-32: Real-Time Metrics Component

**Objective**
Show at least one metric updating live as events flow in. This is the core Part E requirement.

**Inputs**
- SSE endpoint `GET /stores/{id}/stream` added to FastAPI (pushes metrics snapshot every 2 seconds)
- StoreMetrics response from T-18

**Outputs**
- Metrics panel: unique_visitors counter, conversion_rate gauge, current_queue_depth indicator
- Live update via EventSource connected to SSE endpoint
- Visual indicator when the feed is live vs stale

**Dependencies**
- T-31, T-18

**Estimated Effort**
2 hours

**Acceptance Criteria**
- visitor count increments in real time as the detection pipeline posts ENTRY events
- Stale feed (no update for > 10 seconds) shows a visual indicator
- Reconnects automatically after an API restart without a page refresh

---

### T-33: Heatmap Grid Component

**Objective**
Render the zone heatmap as a color-coded grid, providing the visual proof that the /heatmap endpoint produces useful data.

**Inputs**
- /heatmap response from T-20 (zone_id, score 0–100)
- store_layout.json zone names (for labels)

**Outputs**
- Color-coded grid: each cell represents a zone; color interpolates green→red by score
- Tooltip on hover: zone_id, visit_count, avg_dwell_ms
- `data_confidence: false` banner when low-data warning is active

**Dependencies**
- T-31, T-20

**Estimated Effort**
1.5 hours

**Acceptance Criteria**
- All zones from /heatmap appear in the grid
- Color scale is visually distinguishable (not all the same shade)
- Grid renders without error when all scores are 0

---

### T-34: Anomaly Feed Component

**Objective**
Show active anomalies with severity indicators to complete the live dashboard proof of end-to-end connectivity.

**Inputs**
- /anomalies response from T-21

**Outputs**
- Anomaly list: severity badge (color-coded INFO/WARN/CRITICAL), anomaly type, detail string, suggested_action
- Auto-refreshes every 30 seconds
- Empty state: "No active anomalies" message (not blank)

**Dependencies**
- T-31, T-21

**Estimated Effort**
1 hour

**Acceptance Criteria**
- CRITICAL anomalies are visually prominent (red badge)
- Empty anomaly list shows a non-blank "all clear" state
- Component does not crash when /anomalies returns an empty array

---

## Scoring vs Effort Summary

| Part | Points | Total Effort (hours) | Hours per Point |
|------|--------|----------------------|-----------------|
| A — Detection | 30 | 20 | 0.67 |
| B — API | 35 | 12.5 | 0.36 |
| C — Production | 20 | 9.5 | 0.48 |
| D — AI Docs | 15 | 4.5 | 0.30 |
| E — Dashboard | +10 | 6 | 0.60 |
| **Infrastructure** | gate | 3 | — |
| **Total** | **110** | **~55.5** | — |

**Highest points-per-hour:** Part D (write docs last, based on completed system) and Part B (API layer builds on a working schema and DB).

**Lowest points-per-hour:** Cross-camera dedup (T-12) and Re-ID (T-11) are the hardest tasks in Part A and affect only a subset of the 30 points. Timebox both to 3 hours combined if running behind schedule.
