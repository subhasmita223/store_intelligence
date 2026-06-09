# CHOICES.md — Three Architectural Decisions

---

## Decision 1: Detection Model — YOLOv8n with a MOG2 Fallback

### Options I looked at

- **YOLOv8n** (nano): fastest, ~3ms per frame on GPU, reasonable accuracy
- **YOLOv8m** (medium): better recall for partially occluded people, 3× slower
- **YOLOv8x** (extra-large): highest accuracy, impractical on CPU-only hardware
- **RT-DETR**: transformer-based, reportedly better at crowded scenes but much heavier
- **MediaPipe BlazePose**: person detection + pose estimation, too fine-grained for footfall counting
- **OpenCV MOG2** (background subtraction): no ML weights required, works with OpenCV alone

### What AI suggested

I asked the llms  for a recommendation for the project . It told me  YOLOv8n for the detection backbone because it hits the spec's < 200ms per 1080p frame target on CPU, handles groups of people without the overhead of a transformer architecture, and the ultralytics wrapper is best for this type of project. For stores with dense crowds, it flagged that YOLOv8m would improve recall at zone boundaries but probably wasn't necessary for a typical beauty retail floor with 2–5 people visible at a time. It didn't suggest a fallback path.

### What I chose and why

YOLOv8n as the primary detector, with a MOG2 background subtraction fallback I added myself.

The fallback came from a practical problem: `ultralytics` requires PyTorch (~700MB), and I split the requirements into `requirements-api.txt` (API only, no ML dependencies) and `requirements.txt` (full pipeline). This keeps the API Docker image lean. If someone runs the pipeline outside Docker without PyTorch installed, MOG2 kicks in rather than crashing.

MOG2 doesn't produce bounding boxes as cleanly as YOLO — it segments blobs of motion, so it can merge two close-together people into one blob, or split one person into multiple fragments. I added minimum/maximum area filters (6,000–100,000 pixels) and a height/width ratio check to filter out horizontal noise blobs. In testing against the Store 1 zone camera, MOG2 produced ~94% frame coverage (at least one detection per frame) compared to ~9% with OpenCV's HOG detector, which I tried first and abandoned.

I chose YOLOv8n over YOLOv8m because the bottleneck for this project isn't detection accuracy — it's that zone polygon boundaries are manually estimated and probably off by 10–30 pixels. Getting detection right to the person level but then mis-assigning them to a zone because the polygon is miscalibrated doesn't gain anything. Better to nail the zone calibration first, then upgrade the detector if accuracy matters.

---

## Decision 2: Event Schema — Discriminated Union Instead of a Flat Model

### The problem

The sample events file had three structurally incompatible event shapes:

- **Entry/exit events**: `id_token` (string), `store_code`, `event_timestamp`, demographic fields
- **Zone events**: `track_id` (integer), `store_id`, zone metadata, hotspot coordinates
- **Queue events**: `queue_event_id` (UUID), all queue timing fields, billing zone fields

The original placeholder code had a single flat `StoreEvent` with fields like `visitor_id`, `confidence`, `dwell_ms` — none of which appeared in the actual sample data.

### Options I considered

1. **Flat model with all fields Optional**: One `StoreEvent` class. Every field is nullable. Simple to understand, but you can ingest an entry event with no `id_token` (the core identifier) and it would pass validation.

2. **Separate model per event type, validated at the router**: Three classes, the router picks which one to parse based on a pre-read `event_type` field. Gets messy — you're doing the dispatch manually.

3. **Pydantic v2 discriminated union**: `Annotated[Union[EntryExitEvent, ZoneEvent, QueueEvent], Field(discriminator="event_type")]`. Pydantic reads the `event_type` field first, dispatches to the correct model, and validates required fields per type.

### What AI suggested

The AI suggested option 3 (discriminated union) because it uses `Literal["entry", "exit"]` on each sub-model to constrain allowed values, and required fields for each type are actually required — not just "probably there" as they'd be with Optional fields. The batch endpoint (`IngestBatch`) just takes `list[StoreEvent]` and Pydantic handles the dispatch transparently.

### What I chose and why

Option 3, as suggested. I verified it against the 13 events in `sample_events.jsonl` — all parsed correctly, zero rejected. The one thing I adjusted: the original suggestion used separate `EventType` enums per sub-model, but I kept a single top-level `EventType` enum with the full set of event type strings for use in the database layer and query filters. The Pydantic models use `Literal` types; the DB queries use the enum.

The cleaner validation matters here because the ingest endpoint is the acceptance-gate endpoint — it needs to be strict about what it accepts, not lenient. A flat model with all-optional fields would accept junk data silently.

One thing the AI got wrong: it initially suggested keeping `dwell_ms` and `confidence` as top-level fields on all event types. I dropped those because they don't appear in the sample data. Dwell time is computed at query time from zone_entered/zone_exited pairs, and confidence isn't meaningful for queue or entry events (there's no detection confidence in those payloads).

---

## Decision 3: Session Computation On-the-Fly vs Materialized

### The background

The funnel, metrics, and heatmap endpoints all need "sessions" — reconstructed visitor journeys linking an entry event to zone visits and queue events. The question was whether to compute these at query time or maintain a precomputed sessions table.

### Options I considered

1. **On-the-fly at query time**: Each request to `/metrics` or `/funnel` runs the session query live. Simple, always consistent with the latest data. Gets slower as event volume grows.

2. **Materialized sessions table updated on ingest**: A background trigger or hook adds/updates a sessions row whenever a new event arrives. Dashboard queries are fast. But now you have two sources of truth — the events table and the sessions table — and they can drift.

3. **Background job refreshing sessions every N seconds**: A scheduled task runs the session query every 30 seconds and writes results to a materialized view. Decouples ingest speed from query speed but adds latency — if someone just walked in, their entry won't appear in metrics for up to 30 seconds.

### What AI suggested

The AI recommended option 1 (on-the-fly) for this scale. The reasoning: at 2,000 events across two stores, the query runs in under 20ms. Even at 10× that volume, with indexes on `(store_id, event_ts)` and `id_token`, PostgreSQL will still complete the session reconstruction in well under 200ms. Materializing sessions adds complexity (handling updates, handling event corrections, ensuring consistency) for no real latency benefit at this scale.

It also pointed out that option 2 has a subtle correctness problem: if a late-arriving zone event (due to a pipeline retry or clock skew) needs to be attributed to an existing session, the materialized row needs to be retroactively updated. Option 1 handles this automatically — each query sees the current state.

### What I chose and why

Option 1. I agreed with the reasoning. The actual implementation fetches all events for a store+date in a single `SELECT` with an `ORDER BY event_ts` — one round-trip to the DB. The Python side then groups entries into sessions and checks time-window overlap for zone/queue attribution. The query itself is O(events per day), not O(total events), so it scales linearly with daily traffic, not historical data volume.

The honest limitation of the current implementation: the session builder links zone events to entry sessions by time-window overlap rather than by a shared identifier. Zone events use `track_id` (integer, camera-local) and entry events use `id_token` (string, person-level). The pipeline doesn't currently propagate `id_token` from the entry camera to zone cameras. This means in a store with two customers present simultaneously, their zone visits could be cross-attributed to the wrong sessions. It's a known approximation, documented in DESIGN.md.

If I were doing this properly, the `EventEmitter` would resolve `track_id` → `visitor_id` across all cameras using the ReID tracker, and both entry and zone events would carry the same `visitor_id`. The session builder would then join on that field rather than using time windows. That's the right design; the current implementation is a working approximation that's accurate enough for single-person test data and small stores.
