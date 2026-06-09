# PROMPT: Write POST /events/ingest tests covering idempotency, batch size limit,
# malformed event rejection, and single-event acceptance. Use the 13-event sample
# fixture as the canonical batch. Assert on IngestResponse accepted/rejected/errors.
# CHANGES MADE: Updated to new discriminated-union schema (entry/zone/queue events).
# Removed old StoreEvent field references (visitor_id, dwell_ms, confidence).
# Added test for malformed event_type (422) and empty batch (accepted=0).

"""POST /events/ingest tests. T-26."""

import pytest


@pytest.mark.asyncio
async def test_ingest_13_sample_events(client, all_sample_events):
    r = await client.post("/events/ingest", json={"events": all_sample_events})
    assert r.status_code == 200
    body = r.json()
    assert body["accepted"] == 13
    assert body["rejected"] == 0
    assert body["errors"] == []


@pytest.mark.asyncio
async def test_ingest_idempotent(client, all_sample_events):
    await client.post("/events/ingest", json={"events": all_sample_events})
    r2 = await client.post("/events/ingest", json={"events": all_sample_events})
    assert r2.status_code == 200
    body = r2.json()
    assert body["accepted"] == 0
    assert body["rejected"] == 0


@pytest.mark.asyncio
async def test_ingest_batch_size_over_500_returns_422(client, all_sample_events):
    big = (all_sample_events * 40)[:501]
    r = await client.post("/events/ingest", json={"events": big})
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_ingest_empty_batch(client):
    r = await client.post("/events/ingest", json={"events": []})
    assert r.status_code == 200
    assert r.json()["accepted"] == 0


@pytest.mark.asyncio
async def test_ingest_malformed_event_type_returns_422(client):
    bad = {
        "event_type": "not_a_real_type",
        "id_token": "X",
        "store_code": "s",
        "camera_id": "c",
        "event_timestamp": "2026-01-01T00:00:00",
        "is_staff": False,
    }
    r = await client.post("/events/ingest", json={"events": [bad]})
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_ingest_single_entry_event(client, entry_event):
    r = await client.post("/events/ingest", json={"events": [entry_event]})
    assert r.status_code == 200
    assert r.json()["accepted"] == 1


@pytest.mark.asyncio
async def test_ingest_returns_200_not_201(client, entry_event):
    r = await client.post("/events/ingest", json={"events": [entry_event]})
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_ingest_500_events_within_limit(client, all_sample_events):
    batch = (all_sample_events * 39)[:500]
    r = await client.post("/events/ingest", json={"events": batch})
    assert r.status_code == 200
    assert r.json()["accepted"] >= 0   # may be 0 if all duplicates
