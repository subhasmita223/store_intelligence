"""Shared test fixtures. T-25, T-26."""

import json
import os
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.main import app

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://si_user:si_pass@db:5432/store_intelligence",
)


@pytest.fixture(autouse=True)
def _clear_events():
    """Truncate events before every test.

    Uses psycopg2 (synchronous) — no event-loop scope issues.
    """
    import psycopg2
    url = os.environ["DATABASE_URL"].replace("postgresql+asyncpg://", "postgresql://")
    conn = psycopg2.connect(url)
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("TRUNCATE TABLE events RESTART IDENTITY CASCADE")
    conn.close()
    yield


@pytest_asyncio.fixture
async def client():
    """AsyncClient with a fresh per-test asyncpg pool.

    Creates and destroys the pool inside this test's own event loop so
    asyncpg connections are never 'attached to a different loop'.
    """
    import app.db as db_module
    from app.db import close_pool, init_pool

    db_module._pool = None      # ensure we create a new pool in this loop
    await init_pool()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac

    await close_pool()
    db_module._pool = None


# ── Sample event payloads (new discriminated-union schema) ────────────────────

@pytest.fixture
def entry_event() -> dict:
    return {
        "event_type": "entry",
        "id_token": "ID_60001",
        "store_code": "store_1076",
        "camera_id": "cam1",
        "event_timestamp": "2026-03-08T18:10:05.120000",
        "is_staff": False,
        "gender_pred": "F",
        "age_pred": 28,
        "age_bucket": "25-34",
        "is_face_hidden": False,
        "group_id": None,
        "group_size": None,
    }


@pytest.fixture
def zone_event() -> dict:
    return {
        "event_type": "zone_entered",
        "track_id": 101,
        "store_id": "ST1076",
        "camera_id": "CAM2",
        "zone_id": "PURPLLE_MUM_1076_Z01",
        "zone_name": "Left Shelf",
        "zone_type": "SHELF",
        "is_revenue_zone": "Yes",
        "event_time": "2026-03-08T18:10:45.280000",
        "zone_hotspot_x": 412.6,
        "zone_hotspot_y": 238.4,
        "gender": "F",
        "age": 28,
        "age_bucket": "25-34",
    }


@pytest.fixture
def queue_event() -> dict:
    return {
        "queue_event_id": "cfd8e3c5-7aa0-4ea3-9b59-692d50da8308",
        "event_type": "queue_completed",
        "track_id": 102,
        "store_id": "ST1076",
        "camera_id": "PURPLLE_MUM_1076_CAM6",
        "zone_id": "PURPLLE_MUM_1076_Z_BILLING_01",
        "zone_name": "Billing Counter Queue",
        "zone_type": "BILLING",
        "is_revenue_zone": "Yes",
        "queue_join_ts": "2026-03-08T18:13:05.080000",
        "queue_served_ts": "2026-03-08T18:13:13.240000",
        "queue_exit_ts": "2026-03-08T18:15:31.840000",
        "wait_seconds": 8,
        "queue_position_at_join": 2,
        "abandoned": False,
        "zone_hotspot_x": 602.8,
        "zone_hotspot_y": 183.4,
        "gender": "M",
        "age": 31,
        "age_bucket": "25-34",
    }


@pytest.fixture
def all_sample_events() -> list[dict]:
    """All 13 events from sample_events.jsonl."""
    docker_path = Path("/app/data/sample_events.jsonl")
    local_path  = Path(__file__).parent.parent / "data" / "sample_events.jsonl"
    path = docker_path if docker_path.exists() else local_path
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
