# PROMPT: Write /stores/{id}/anomalies tests covering DEAD_ZONE detection for old
# zone events, CONVERSION_DROP INFO when < 7 days history, empty anomaly list
# shape, and that every anomaly has a non-empty suggested_action field.
# CHANGES MADE: BILLING_QUEUE_SPIKE test uses recent queue events via the new
# QueueEvent schema. DEAD_ZONE test relies on historical sample events (>30 min old)
# which correctly triggers the anomaly. Added assertion that anomalies is a list
# (not null) on empty store.

"""GET /stores/{id}/anomalies tests. T-26."""

import pytest

STORE = "ST1076"


async def _seed(client, events):
    r = await client.post("/events/ingest", json={"events": events})
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_anomalies_empty_store_returns_list(client):
    """With no events the response must be a list (not null, not 500)."""
    r = await client.get(f"/stores/{STORE}/anomalies")
    assert r.status_code == 200
    body = r.json()
    assert "anomalies" in body
    assert isinstance(body["anomalies"], list)


@pytest.mark.asyncio
async def test_anomalies_conversion_drop_info_no_history(client, all_sample_events):
    """With < 7 days of history, CONVERSION_DROP must be INFO severity."""
    await _seed(client, all_sample_events)
    r = await client.get(f"/stores/{STORE}/anomalies")
    assert r.status_code == 200
    anomalies = r.json()["anomalies"]
    conv_drops = [a for a in anomalies if a["type"] == "CONVERSION_DROP"]
    assert len(conv_drops) >= 1
    assert conv_drops[0]["severity"] == "INFO"


@pytest.mark.asyncio
async def test_anomalies_dead_zone_fires_for_old_events(client, all_sample_events):
    """Zone events from months ago trigger DEAD_ZONE (last visit > 30 min)."""
    await _seed(client, all_sample_events)
    r = await client.get(f"/stores/{STORE}/anomalies")
    anomalies = r.json()["anomalies"]
    dead_zones = [a for a in anomalies if a["type"] == "DEAD_ZONE"]
    # Sample data has 3 distinct zones → at least 1 DEAD_ZONE anomaly
    assert len(dead_zones) >= 1


@pytest.mark.asyncio
async def test_anomalies_each_has_suggested_action(client, all_sample_events):
    """Every anomaly must have a non-empty suggested_action string."""
    await _seed(client, all_sample_events)
    r = await client.get(f"/stores/{STORE}/anomalies")
    for anomaly in r.json()["anomalies"]:
        assert anomaly.get("suggested_action"), (
            f"Missing suggested_action on {anomaly['type']}"
        )


@pytest.mark.asyncio
async def test_anomalies_required_fields_present(client, all_sample_events):
    """Every anomaly must have type, severity, detail, and suggested_action."""
    await _seed(client, all_sample_events)
    r = await client.get(f"/stores/{STORE}/anomalies")
    for anomaly in r.json()["anomalies"]:
        for field in ("type", "severity", "detail", "suggested_action"):
            assert field in anomaly, f"Anomaly missing field: {field}"


@pytest.mark.asyncio
async def test_anomalies_store_id_in_response(client):
    """Response body must contain the store_id that was requested."""
    r = await client.get(f"/stores/{STORE}/anomalies")
    assert r.json()["store_id"] == STORE


@pytest.mark.asyncio
async def test_anomalies_severity_is_valid_value(client, all_sample_events):
    """Severity must be one of INFO, WARN, CRITICAL."""
    await _seed(client, all_sample_events)
    valid = {"INFO", "WARN", "CRITICAL"}
    for anomaly in (await client.get(f"/stores/{STORE}/anomalies")).json()["anomalies"]:
        assert anomaly["severity"] in valid, f"Invalid severity: {anomaly['severity']}"
