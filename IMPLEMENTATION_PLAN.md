# IMPLEMENTATION PLAN
## Purplle Tech Challenge — Store Intelligence System

---

## 1. System Overview

The system is a four-stage pipeline with a fixed, pre-specified interface at every boundary. No boundary is redesigned here.

```
Raw CCTV Clips
    │
    ▼
[Detection Pipeline]  →  structured events (event schema from spec)
    │
    ▼
[POST /events/ingest]  →  PostgreSQL
    │
    ▼
[Intelligence API]  →  /metrics  /funnel  /heatmap  /anomalies  /health
    │
    ▼
[Next.js Dashboard]  →  live metric display
```

Stack fixed by the user: YOLOv8 + ByteTrack · FastAPI · PostgreSQL · Next.js

---

## 2. Module Map

### Layer 0 — Infrastructure

| ID   | Module                        | Points Exposure |
|------|-------------------------------|-----------------|
| M-00 | Repo scaffold + docker-compose | Gate (5 pts C)  |
| M-01 | PostgreSQL schema + migrations | Gate            |

### Layer 1 — Event Contract

| ID   | Module                   | Points Exposure |
|------|--------------------------|-----------------|
| M-02 | Pydantic event models    | A-schema (10pts), B-ingest (20pts) |

### Layer 2 — Detection Pipeline (Part A, 30 pts)

| ID   | Module                         | Points Exposure              |
|------|--------------------------------|------------------------------|
| M-03 | Frame extractor                | Foundation for all A points  |
| M-04 | YOLOv8 person detector         | A-accuracy (10 pts)          |
| M-05 | ByteTrack tracker              | A-accuracy (10 pts)          |
| M-06 | Zone mapper                    | A-schema (10 pts)            |
| M-07 | Entry/exit direction classifier| A-accuracy (10 pts)          |
| M-08 | Staff classifier               | A-staff/reentry (10 pts)     |
| M-09 | Dwell accumulator              | A-schema (10 pts)            |
| M-10 | Billing queue depth counter    | A-schema, B-anomalies        |
| M-11 | Re-ID / REENTRY detector       | A-staff/reentry (10 pts)     |
| M-12 | Cross-camera deduplicator      | A-accuracy (10 pts)          |
| M-13 | Event emitter                  | All A points                 |
| M-14 | Pipeline runner (run.sh)       | Gate                         |

### Layer 3 — Intelligence API (Part B, 35 pts)

| ID   | Module                          | Points Exposure           |
|------|---------------------------------|---------------------------|
| M-15 | FastAPI app scaffold            | Foundation for all B pts  |
| M-16 | POST /events/ingest             | B-endpoints (20 pts)      |
| M-17 | Session state builder           | B-funnel (10 pts)         |
| M-18 | GET /stores/{id}/metrics        | B-endpoints (20 pts)      |
| M-19 | GET /stores/{id}/funnel         | B-funnel (10 pts)         |
| M-20 | GET /stores/{id}/heatmap        | B-endpoints (20 pts)      |
| M-21 | GET /stores/{id}/anomalies      | B-anomalies (5 pts)       |
| M-22 | GET /health                     | C-logs/health (5 pts)     |

### Layer 4 — Production Readiness (Part C, 20 pts)

| ID   | Module                        | Points Exposure       |
|------|-------------------------------|-----------------------|
| M-23 | Structured logging middleware | C-logs (5 pts)        |
| M-24 | Graceful degradation handler  | C-edge cases (10 pts) |
| M-25 | Test suite — pipeline         | C-tests (10 pts)      |
| M-26 | Test suite — API              | C-tests (10 pts)      |
| M-27 | README.md                     | Gate (5 pts)          |

### Layer 5 — AI Engineering (Part D, 15 pts)

| ID   | Module                     | Points Exposure |
|------|----------------------------|-----------------|
| M-28 | DESIGN.md                  | D (15 pts)      |
| M-29 | CHOICES.md                 | D (15 pts)      |
| M-30 | Prompt blocks in test files| D (15 pts)      |

### Layer 6 — Live Dashboard (Part E, +10 bonus pts)

| ID   | Module                          | Points Exposure |
|------|---------------------------------|-----------------|
| M-31 | Next.js app scaffold            | E (+10 pts)     |
| M-32 | Real-time metrics component     | E (+10 pts)     |
| M-33 | Heatmap grid component          | E (+10 pts)     |
| M-34 | Anomaly feed component          | E (+10 pts)     |

---

## 3. Recommended Build Order (Solo Developer)

The ordering respects hard dependencies and front-loads the acceptance gate.

```
Phase 1 — Gate First (Hours 0–4)
  M-00 → M-01 → M-02 → M-15

Phase 2 — Ingest Path (Hours 4–8)
  M-16 (bare store, no validation) → smoke test gate passes

Phase 3 — Detection Core (Hours 8–20)
  M-03 → M-04 → M-05 → M-06 → M-07 → M-08 → M-09

Phase 4 — Event Emission (Hours 20–24)
  M-10 → M-13 → M-14 → validate against sample_events.jsonl

Phase 5 — API Compute Layer (Hours 24–34)
  M-17 → M-18 → M-19 → M-20 → M-21 → M-22

Phase 6 — Hardening + Re-ID (Hours 34–40)
  M-11 → M-12 → M-16 full idempotency → M-23 → M-24

Phase 7 — Tests + Docs (Hours 40–46)
  M-25 → M-26 → M-27 → M-28 → M-29 → M-30

Phase 8 — Bonus Dashboard (Hours 46–48)
  M-31 → M-32 → M-33 → M-34
```

---

## 4. Critical Path

Every module on the critical path is a hard blocker for the acceptance gate or top scoring dimensions.

```
M-02 (schema)
  └─► M-16 (ingest) ──────────────────────────► GATE PASSES
        └─► M-17 (sessions)
              ├─► M-18 (metrics) ──────────────► B 20pts
              ├─► M-19 (funnel) ───────────────► B 10pts
              └─► M-21 (anomalies) ────────────► B 5pts

M-03 (frames)
  └─► M-04 (YOLO)
        └─► M-05 (ByteTrack)
              ├─► M-06 (zones) ──► M-09 (dwell) ──► M-13 (emit) ──► A 30pts
              └─► M-07 (direction) ──────────────────────────────────► A 10pts

M-00 + M-01 + M-27 + M-28 + M-29 ──────────────────────────────────► GATE
```

**Critical path modules:** M-00, M-01, M-02, M-03, M-04, M-05, M-06, M-07, M-13, M-15, M-16, M-17, M-18, M-27

---

## 5. Modules That Can Be Postponed to the Final Day

These modules are non-blocking for the acceptance gate and have lower or recoverable point exposure.

| Module | Reason Safe to Defer                                                |
|--------|---------------------------------------------------------------------|
| M-11   | REENTRY detection — partial credit without it; rest of A still scores |
| M-12   | Cross-camera dedup — complex; individual camera counts still score  |
| M-20   | /heatmap — 5 of 20 B-endpoint pts; gate only needs /metrics         |
| M-21   | /anomalies — only 5 pts; defer until metrics are stable             |
| M-23   | Structured logging — 5 pts C; gate does not test it                 |
| M-24   | Graceful degradation — part of edge case tests, not gate            |
| M-25   | Pipeline tests — coverage requirement, not gate                     |
| M-28   | DESIGN.md — write from working system; gate requires >250 words     |
| M-29   | CHOICES.md — same                                                   |
| M-30   | Prompt blocks — trivial to add at the end                           |
| M-31–34| Dashboard bonus — entire Part E                                     |

**Hard rule:** Do not start M-31–34 until M-18 and M-19 are confirmed working. The dashboard has zero value without a live API.

---

## 6. Realistic 48-Hour Execution Plan

All times are wall-clock from the moment the dataset arrives.

### Hour 0–2: Environment
- Clone skeleton, create docker-compose.yml with `api` and `db` services
- Bring up PostgreSQL, confirm connection
- Scaffold FastAPI app: `main.py`, router placeholders, health stub
- Write `alembic` migration for the events table (event_id, store_id, camera_id, visitor_id, event_type, timestamp, zone_id, dwell_ms, is_staff, confidence, metadata JSONB)
- **Exit condition:** `docker compose up` starts without error; `GET /health` returns 200

### Hour 2–4: Schema + Bare Ingest
- Implement Pydantic event models matching the spec schema exactly
- Implement `POST /events/ingest`: validate schema, deduplicate by event_id, bulk insert
- Return `{accepted: N, rejected: M, errors: [...]}` on partial failure
- **Exit condition:** post one event from sample_events.jsonl, get 200 back; post same event again, still 200 (idempotent)

### Hour 4–6: Frame Extractor + YOLO Baseline
- Implement frame extractor: read clip, sample at 5fps (3fps for billing clips), yield frames with timestamps derived from clip start time + frame offset
- Load YOLOv8n (nano for speed); run on first 60s of one clip
- Confirm person detections appear with bounding boxes
- **Exit condition:** detection loop runs without error; at least one detection visible per frame in-store

### Hour 6–10: ByteTrack Integration
- Integrate BoxMOT's ByteTrack wrapper; feed YOLO bounding boxes per frame
- Each tracked person gets a stable `track_id` across frames
- Log track continuity: track_id must survive at least 5 consecutive frames for a new entity
- **Exit condition:** single person walking through entry camera gets one stable track_id from entry to mid-frame

### Hour 10–13: Zone Mapper + Direction Classifier
- Parse `store_layout.json`: load zone polygons keyed by camera_id
- Map each bounding box centroid to zone_id using point-in-polygon; zones are named as in spec
- Implement entry/exit direction: define a horizontal crossing line at the entry threshold; track centroid trajectory across ≥3 frames to determine inbound vs outbound
- **Exit condition:** person entering from outside → emits ENTRY; person leaving → emits EXIT; zone transitions logged correctly

### Hour 13–16: Staff Classifier + Event Emitter
- Staff classification: heuristic using bounding box aspect ratio, color histogram of torso region compared to a staff color reference (configurable), or a simple classifier prompt via VLM for 5 sample frames
- Implement `emit.py`: translate per-frame tracker state into the 8 event types; ZONE_DWELL fires every 30s of continuous presence; BILLING_QUEUE_JOIN fires when centroid enters billing zone while queue_depth > 0
- **Exit condition:** run emit.py against one full 20-minute clip; validate every emitted event against Pydantic model; compare event count vs sample_events.jsonl counts (within 20%)

### Hour 16–18: Validate Against sample_events.jsonl
- Ingest all events from sample_events.jsonl into local API
- Run assertions.py; all 10 assertions must pass
- Fix any schema field mismatches
- **Exit condition:** assertions.py exits 0

### Hour 18–22: Session Builder + /metrics
- Implement session builder: group events by visitor_id, ordered by timestamp; a session starts with ENTRY and closes with EXIT or a 30-minute idle timeout
- POS correlation: for each session with a BILLING_QUEUE_JOIN event, look up pos_transactions within a 5-minute backward window to flag conversion
- Implement `GET /stores/{id}/metrics`: unique_visitors (customer sessions, is_staff=false), conversion_rate, avg_dwell_per_zone dict, current_queue_depth, abandonment_rate
- **Exit condition:** response matches expected structure; zero-purchase store returns 0.0 not null; empty store returns valid response with 0 counts

### Hour 22–25: /funnel + /heatmap
- Implement `GET /stores/{id}/funnel`: count sessions at each stage (Entry→Zone Visit→Billing Queue→Purchase); compute drop_off_pct at each transition; session is the unit, not raw event count
- Implement `GET /stores/{id}/heatmap`: per-zone visit_count and avg_dwell_ms, normalized 0–100 across zones; set `data_confidence: false` if session count < 20
- **Exit condition:** funnel stages sum correctly; a visitor who entered but never reached billing shows 100% drop-off at that stage

### Hour 25–28: /anomalies + /health
- Implement `GET /stores/{id}/anomalies`:
  - BILLING_QUEUE_SPIKE: queue_depth > configurable threshold (default 5) for > 3 minutes
  - CONVERSION_DROP: today's conversion_rate < (7-day rolling avg × 0.7); requires historical events in DB
  - DEAD_ZONE: a zone with zero ZONE_ENTER events in the past 30 minutes
  - Each anomaly includes severity (INFO/WARN/CRITICAL) and suggested_action string
- Implement `GET /health`: per-store last_event_timestamp; STALE_FEED if lag > 10 minutes
- **Exit condition:** inject a synthetic queue-depth event sequence; anomaly fires with correct severity

### Hour 28–32: Re-ID + Cross-Camera Dedup
- Re-ID: maintain a rolling buffer of exited track appearance descriptors (HOG or bounding box crop embedding); when a new track appears at the entry threshold, compare against buffer within a 10-minute window; if cosine similarity > threshold, emit REENTRY rather than ENTRY
- Cross-camera dedup: for the entry/floor camera overlap zone, suppress duplicate ZONE_ENTER events from the floor camera if the same visitor_id appeared in the entry camera within the last 5 seconds
- **Exit condition:** replay test sequence where a person exits and re-enters within 5 minutes; REENTRY event fires, not second ENTRY

### Hour 32–35: Structured Logging + Graceful Degradation
- Logging middleware: inject `trace_id` (UUID) per request; log JSON with trace_id, store_id (from path param), endpoint, latency_ms, event_count (ingest only), status_code
- Graceful degradation: wrap all DB calls in try/except; on connection failure return HTTP 503 with body `{"error": "SERVICE_UNAVAILABLE", "detail": "database unreachable"}`; no raw stack traces in any response body
- **Exit condition:** kill the DB container mid-request; API returns 503 with structured body

### Hour 35–39: Test Suite
- `tests/test_pipeline.py`: test event schema validation, entry/exit pair, group entry count, staff exclusion, REENTRY detection, empty clip
- `tests/test_metrics.py`: conversion rate calculation, zero-purchase store, re-entry dedup in funnel
- `tests/test_anomalies.py`: queue spike trigger, dead zone trigger, conversion drop trigger
- `tests/test_ingest.py`: idempotency (post same batch twice), partial failure on malformed event
- Add prompt blocks at top of each test file
- Run pytest --cov; target >70% statement coverage
- **Exit condition:** coverage report shows ≥70%; all edge case tests pass

### Hour 39–43: Documentation
- Write `DESIGN.md`: architecture diagram in ASCII, data flow description, 'AI-Assisted Decisions' section with 2–3 specific LLM interactions
- Write `CHOICES.md`: (1) YOLOv8 model selection with alternatives considered, (2) event schema rationale including REENTRY vs second ENTRY decision, (3) session deduplication approach
- Write `README.md`: exactly 5 commands from git clone to running pipeline and verifying API

### Hour 43–46: Full Pipeline Run + Regression
- Run `run.sh` against all 5 stores × 3 cameras (15 clips)
- Monitor event counts, check for crashes on empty-store periods and crowded billing periods
- Fix any bugs surfaced by the full run
- Re-run assertions.py on full output
- **Exit condition:** all 15 clips process without exception; total event count is non-trivial

### Hour 46–48: Dashboard (Bonus) + Final Gate Check
- Scaffold Next.js app with one page: store selector + live metrics panel
- Add SSE endpoint `GET /stores/{id}/stream` to FastAPI; push metrics snapshot every 2 seconds
- Connect Next.js EventSource to SSE endpoint; display visitor count and conversion rate updating live
- Final check: `docker compose down && docker compose up` on a clean volume; run assertions.py; confirm README instructions work verbatim
- Commit, push, verify private repo access for reviewer

---

## 7. Risk Register

| Risk | Impact | Mitigation |
|------|--------|------------|
| YOLOv8 inference too slow on CPU for 15fps clips | High — processing time blows 48h | Sample at 3–5fps from the start; use yolov8n not yolov8x |
| ByteTrack loses tracks through occlusion | Medium — affects Re-ID accuracy | Increase max_age parameter; combine with appearance descriptor |
| store_layout.json zone polygons don't align with video resolution | High — all zone events wrong | Add a visualization debug mode that renders polygons on first frame |
| POS correlation window too narrow, misses conversions | Medium — conversion rate too low | Make window configurable; default 5 min as spec says |
| Cross-camera dedup produces false merges | Medium — undercounts visitors | Conservative threshold; log merge decisions for review |
| PostgreSQL session state query slow on large event volume | Low for 48h, real in prod | Add index on (store_id, visitor_id, timestamp) from the start |
| Re-ID appearance matching fails with blurred faces | Medium — faces are blurred in dataset | Use full-body crop + torso color histogram rather than face features |
| docker compose fails on reviewer machine (GPU deps) | Critical — fails gate | Ensure CPU fallback; pin all image versions; test on CPU explicitly |
