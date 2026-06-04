# Store Intelligence System

A computer-vision pipeline that processes CCTV footage from retail stores and exposes a live analytics API. Raw `.mp4` clips go in; zone dwell times, conversion funnels, queue depths, and anomaly alerts come out.

Built with: Python 3.11, FastAPI, PostgreSQL 16, Next.js 14, Docker Compose.

---

## Prerequisites

- Docker 24+ and Docker Compose v2+
- The store dataset (video clips + layout files) placed under `./data/`
- Nothing else — all Python and Node dependencies are installed inside the containers

The data directory should look like this after you place the dataset:

```
data/
  Store 1/
    CAM 1 - zone.mp4
    CAM 2 - zone.mp4
    CAM 3 - entry.mp4
    CAM 5 - billing.mp4
    store_layout.json
  Store 2/
    entry 1.mp4
    entry 2.mp4
    zone.mp4
    billing_area.mp4
    store_layout.json
  sample_events.jsonl
```

---

## Setup — 5 Commands

```bash
# 1. Clone the repository
git clone <repo-url> && cd store-intelligence

# 2. Copy environment variables (defaults work out of the box)
cp .env.example .env

# 3. Start the API, database, and dashboard
docker compose up --build -d

# 4. Run the detection pipeline against a store
python pipeline/process_store.py "data/Store 1" http://localhost:8000 --date 2026-03-08

# 5. Verify the API is returning real data
curl "http://localhost:8000/stores/ST1076/metrics?for_date=2026-03-08"
```

That's it. The database migration runs automatically on container startup (`alembic upgrade head` is baked into the API's CMD).

---

## Detection Pipeline

The pipeline script processes each camera in the store's `store_layout.json` and posts events directly to the ingest endpoint.

```bash
python pipeline/process_store.py "<store_directory>" <api_url> --date <YYYY-MM-DD>
```

For example:

```bash
python pipeline/process_store.py "data/Store 1" http://localhost:8000 --date 2026-03-08
python pipeline/process_store.py "data/Store 2" http://localhost:8000 --date 2026-03-08
```

Or use the shell wrapper:

```bash
bash pipeline/run.sh "./data/Store 1" http://localhost:8000 --date 2026-03-08
```

**Important:** The pipeline requires `ultralytics` and `boxmot` for full YOLO + ByteTrack detection. If those packages aren't in your Python environment (they aren't installed in the API container), it falls back to OpenCV MOG2 background subtraction and an IoU tracker. The fallback works and produces real events, but person-detection accuracy is lower. To get YOLO quality, install the pipeline dependencies locally:

```bash
pip install -r requirements.txt
```

Events are posted to `POST /events/ingest` in batches of 400. The endpoint is idempotent — re-running the pipeline on the same store and date is safe.

---

## Running Tests

Tests run inside the API container against the same PostgreSQL database:

```bash
docker compose run --rm api pytest tests/ --cov=app --cov-report=term-missing -v
```

Current coverage: **85%** across all app modules. Tests are async, use per-test connection pool creation to avoid event-loop scope issues with pytest-asyncio, and clean up the events table before each test via a synchronous psycopg2 fixture (this avoids the asyncpg "attached to different loop" error that would otherwise happen with session-scoped pool init).

---

## API Endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/events/ingest` | Ingest up to 500 events per batch |
| `GET` | `/stores/{id}/metrics` | KPIs: visitors, conversion, dwell, queue depth |
| `GET` | `/stores/{id}/funnel` | 4-stage entry → zone → billing → purchase funnel |
| `GET` | `/stores/{id}/heatmap` | Per-zone visit count + avg dwell + normalized score |
| `GET` | `/stores/{id}/anomalies` | Live anomaly detection (queue spike, dead zone, conversion drop) |
| `GET` | `/health` | DB status + per-store feed staleness |

All date-filtered endpoints accept `?for_date=YYYY-MM-DD`. Defaults to today if omitted.

---

## Live Dashboard

After `docker compose up`, open [http://localhost:3000](http://localhost:3000).

The dashboard loads store IDs from `/health` and polls `/metrics` every 5 seconds, `/heatmap` every 30 seconds, and `/anomalies` every 30 seconds. To see metrics populate in real time, run the pipeline with the dashboard open. Zone data appears after the zone camera finishes; queue and abandonment data appears after the billing camera finishes.

### Screenshots

**KPI overview and zone analytics**

![KPI cards showing 3 unique visitors, 66.7% conversion rate, 74.1% abandonment rate, and the zone analytics table ranked by utilization](images/Screenshot%20(1949).png)

The overview section shows four KPI cards (unique visitors, conversion rate, queue depth, abandonment rate) and a ranked zone analytics table. Each row shows the zone name, a utilization progress bar relative to the highest-dwell zone, and the average dwell time. In this case Left Shelf had the longest dwell at 33.4 seconds, which anchors the 100% bar.

---

**Zone heatmap and anomaly center**

![Zone heatmap grid with colored cards per zone and anomaly alerts below](images/Screenshot%20(1950).png)

The heatmap section renders each zone as a card with a color-coded engagement score (sky blue = cold, red = hot), visit count, and average dwell time. Below it, the anomaly center shows INFO-level alerts — in this case a conversion drop warning and several dead-zone alerts because the sample data is from March and all zones are >30 minutes stale.

---

**Anomaly detail view**

![Anomaly center showing one Conversion Drop and five Dead Zone alerts with suggested actions](images/Screenshot%20(1951).png)

Each anomaly card has a severity badge (INFO/WARN/CRITICAL), a plain-English description of what triggered it, and a suggested action in blue. The "Conversion Drop" anomaly is INFO rather than WARN because there are fewer than 7 days of historical data to compare against. The dead-zone alerts are accurate — the store hasn't had live camera feed since March, so every zone shows as inactive.

---

## Known Limitations

- **Polygon calibration**: `store_layout.json` contains manually estimated zone polygon coordinates. For production, these should be calibrated against actual video frames (pause a clip, identify pixel coordinates of each zone boundary, update the JSON). The current estimates produce real events but zone assignment accuracy depends on camera angle.

- **No YOLO in Docker**: The API container only installs `requirements-api.txt`, which doesn't include PyTorch. Running the pipeline locally with `requirements.txt` gives full YOLO + ByteTrack. This was a deliberate split to keep the API container lean (~300MB vs ~3GB).

- **Test isolation**: Tests run against the production database (same container). The `_clear_events` fixture truncates `events` before each test. Don't run tests while ingesting real data.

---

## Architecture

See [docs/DESIGN.md](docs/DESIGN.md) for the full architecture overview and [docs/CHOICES.md](docs/CHOICES.md) for the three main design decisions.
