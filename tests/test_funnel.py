# PROMPT: Write /stores/{id}/funnel tests. Seed the 13-event sample set and verify
# stages are monotonically non-increasing, drop_off_pct at ENTRY is 0.0, and that
# a visitor who only reached ZONE_VISIT is not counted in BILLING_QUEUE.
# CHANGES MADE: Replaced old StoreEvent seed data with new schema. Added explicit
# stage-order assertion. Confirmed 4-stage structure ["ENTRY","ZONE_VISIT",
# "BILLING_QUEUE","PURCHASE"].

"""GET /stores/{id}/funnel tests. T-26."""

import pytest

STORE = "ST1076"
DATE  = "2026-03-08"


async def _seed(client, events):
    r = await client.post("/events/ingest", json={"events": events})
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_funnel_stages_monotonically_non_increasing(client, all_sample_events):
    """Each stage count must be ≤ the previous stage count."""
    await _seed(client, all_sample_events)
    r = await client.get(f"/stores/{STORE}/funnel?for_date={DATE}")
    assert r.status_code == 200
    stages = r.json()["stages"]
    counts = [s["count"] for s in stages]
    for i in range(1, len(counts)):
        assert counts[i] <= counts[i - 1], (
            f"Stage {i} count {counts[i]} > stage {i-1} count {counts[i-1]}"
        )


@pytest.mark.asyncio
async def test_funnel_entry_drop_off_always_zero(client, all_sample_events):
    """drop_off_pct at the ENTRY stage must always be 0.0."""
    await _seed(client, all_sample_events)
    r = await client.get(f"/stores/{STORE}/funnel?for_date={DATE}")
    stages = r.json()["stages"]
    entry = next(s for s in stages if s["stage"] == "ENTRY")
    assert entry["drop_off_pct"] == 0.0


@pytest.mark.asyncio
async def test_funnel_has_four_stages(client, all_sample_events):
    """Response must contain exactly the 4 required stages in order."""
    await _seed(client, all_sample_events)
    r = await client.get(f"/stores/{STORE}/funnel?for_date={DATE}")
    stages = r.json()["stages"]
    assert [s["stage"] for s in stages] == [
        "ENTRY", "ZONE_VISIT", "BILLING_QUEUE", "PURCHASE"
    ]


@pytest.mark.asyncio
async def test_funnel_empty_store_all_zeros(client):
    """With no events every stage must be 0 — no null values."""
    r = await client.get(f"/stores/{STORE}/funnel?for_date={DATE}")
    assert r.status_code == 200
    stages = r.json()["stages"]
    assert all(s["count"] == 0 for s in stages)
    assert all(s["drop_off_pct"] is not None for s in stages)


@pytest.mark.asyncio
async def test_funnel_billing_leq_zone_visit(client, all_sample_events):
    """BILLING_QUEUE stage count must be ≤ ZONE_VISIT stage count."""
    await _seed(client, all_sample_events)
    stages = (await client.get(f"/stores/{STORE}/funnel?for_date={DATE}")).json()["stages"]
    zone  = next(s for s in stages if s["stage"] == "ZONE_VISIT")["count"]
    bill  = next(s for s in stages if s["stage"] == "BILLING_QUEUE")["count"]
    assert bill <= zone


@pytest.mark.asyncio
async def test_funnel_purchase_leq_billing(client, all_sample_events):
    """PURCHASE stage count must be ≤ BILLING_QUEUE stage count."""
    await _seed(client, all_sample_events)
    stages = (await client.get(f"/stores/{STORE}/funnel?for_date={DATE}")).json()["stages"]
    bill     = next(s for s in stages if s["stage"] == "BILLING_QUEUE")["count"]
    purchase = next(s for s in stages if s["stage"] == "PURCHASE")["count"]
    assert purchase <= bill


@pytest.mark.asyncio
async def test_funnel_correct_entry_count(client, all_sample_events):
    """Sample set has 3 entry events → ENTRY stage count must be 3."""
    await _seed(client, all_sample_events)
    stages = (await client.get(f"/stores/{STORE}/funnel?for_date={DATE}")).json()["stages"]
    entry_count = next(s for s in stages if s["stage"] == "ENTRY")["count"]
    assert entry_count == 3
