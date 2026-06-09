# PROMPT: Write /stores/{id}/metrics tests. Seed events via the ingest endpoint,
# then assert correct unique_visitors, conversion_rate, avg_dwell_per_zone,
# current_queue_depth, and abandonment_rate. Cover normal case, all-staff store,
# and empty store (all zeros).
# CHANGES MADE: Adapted seeding to new event schema (entry events via store_code,
# zone events via track_id). Used for_date=2026-03-08 to match sample fixtures.
# Removed old metadata.queue_depth field references.

"""GET /stores/{id}/metrics tests. T-26."""

import pytest

STORE = "ST1076"
DATE  = "2026-03-08"


async def _seed(client, events):
    r = await client.post("/events/ingest", json={"events": events})
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_metrics_correct_counts(client, all_sample_events):
    """3 entries, 2 queue_completed, 1 queue_abandoned → correct aggregates."""
    await _seed(client, all_sample_events)
    r = await client.get(f"/stores/{STORE}/metrics?for_date={DATE}")
    assert r.status_code == 200
    body = r.json()

    assert body["unique_visitors"] == 3
    assert body["conversion_rate"] == pytest.approx(2 / 3, abs=0.001)
    assert "Left Shelf" in body["avg_dwell_per_zone"]
    assert body["avg_dwell_per_zone"]["Left Shelf"] == pytest.approx(33440, abs=100)
    assert body["current_queue_depth"] == 0   # historical data, not live
    assert body["abandonment_rate"] == pytest.approx(1 / 3, abs=0.001)


@pytest.mark.asyncio
async def test_metrics_all_staff_zero_visitors(client):
    """When all entry events have is_staff=True, unique_visitors must be 0."""
    staff_events = [
        {
            "event_type": "entry",
            "id_token": f"STAFF_{i:03d}",
            "store_code": "store_1076",
            "camera_id": "cam1",
            "event_timestamp": f"2026-03-08T09:0{i}:00.000000",
            "is_staff": True,
            "is_face_hidden": False,
        }
        for i in range(3)
    ]
    await _seed(client, staff_events)
    r = await client.get(f"/stores/{STORE}/metrics?for_date={DATE}")
    assert r.status_code == 200
    body = r.json()
    assert body["unique_visitors"] == 0
    assert body["conversion_rate"] == 0.0


@pytest.mark.asyncio
async def test_metrics_empty_store_all_zeros(client):
    """No events at all → every metric is 0 or empty, no null values."""
    r = await client.get(f"/stores/{STORE}/metrics?for_date={DATE}")
    assert r.status_code == 200
    body = r.json()
    assert body["unique_visitors"]     == 0
    assert body["conversion_rate"]     == 0.0
    assert body["abandonment_rate"]    == 0.0
    assert body["current_queue_depth"] == 0
    assert body["avg_dwell_per_zone"]  == {}   # empty dict, not null


@pytest.mark.asyncio
async def test_metrics_response_has_required_fields(client):
    """Response must contain all required fields even for an empty store."""
    r = await client.get(f"/stores/{STORE}/metrics?for_date={DATE}")
    assert r.status_code == 200
    body = r.json()
    for field in ("store_id", "date", "unique_visitors", "conversion_rate",
                  "avg_dwell_per_zone", "current_queue_depth", "abandonment_rate"):
        assert field in body, f"Missing field: {field}"


@pytest.mark.asyncio
async def test_metrics_dwell_per_zone_not_null(client, all_sample_events):
    """avg_dwell_per_zone must be a dict (not null) when zone events exist."""
    await _seed(client, all_sample_events)
    r = await client.get(f"/stores/{STORE}/metrics?for_date={DATE}")
    body = r.json()
    assert isinstance(body["avg_dwell_per_zone"], dict)
    assert len(body["avg_dwell_per_zone"]) > 0
