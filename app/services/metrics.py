"""Real-time store KPI computation. T-18."""

from collections import defaultdict
from datetime import date
from typing import Any

import asyncpg

from app.services.session import build_sessions


async def compute_metrics(
    store_id: str,
    for_date: date,
    conn: asyncpg.Connection,
) -> dict[str, Any]:
    sessions = await build_sessions(store_id, for_date, conn)
    customer = [s for s in sessions if not s.is_staff]

    unique_visitors = len(customer)
    purchases = sum(1 for s in customer if s.completed_purchase)
    conversion_rate = round(purchases / unique_visitors, 4) if unique_visitors else 0.0

    # dwell per zone: pair zone_entered with its next zone_exited for the same track+zone
    zone_rows = await conn.fetch(
        """
        SELECT track_id, zone_id, zone_name, event_type, event_ts
        FROM events
        WHERE store_id = $1
          AND event_type IN ('zone_entered', 'zone_exited')
          AND DATE(event_ts) = $2::date
        ORDER BY track_id, zone_id, event_ts
        """,
        store_id,
        for_date,
    )
    enters: dict[tuple, tuple] = {}
    zone_dwells: dict[str, list[float]] = defaultdict(list)
    for r in zone_rows:
        key = (r["track_id"], r["zone_id"])
        if r["event_type"] == "zone_entered":
            enters[key] = (r["event_ts"], r["zone_name"])
        elif r["event_type"] == "zone_exited" and key in enters:
            enter_ts, zone_name = enters.pop(key)
            zone_dwells[zone_name].append((r["event_ts"] - enter_ts).total_seconds() * 1000)

    avg_dwell_per_zone = {z: int(sum(ms) / len(ms)) for z, ms in zone_dwells.items()}

    # people currently in the billing queue (join_ts ≤ now < exit_ts)
    current_depth = await conn.fetchval(
        """
        SELECT COUNT(*) FROM events
        WHERE store_id = $1
          AND event_type IN ('queue_completed', 'queue_abandoned')
          AND queue_join_ts <= NOW()
          AND (queue_exit_ts IS NULL OR queue_exit_ts > NOW())
        """,
        store_id,
    ) or 0

    queue_total = await conn.fetchval(
        """
        SELECT COUNT(*) FROM events
        WHERE store_id = $1
          AND event_type IN ('queue_completed', 'queue_abandoned')
          AND DATE(event_ts) = $2::date
        """,
        store_id,
        for_date,
    ) or 0

    queue_abandoned = await conn.fetchval(
        """
        SELECT COUNT(*) FROM events
        WHERE store_id = $1
          AND event_type = 'queue_abandoned'
          AND DATE(event_ts) = $2::date
        """,
        store_id,
        for_date,
    ) or 0

    abandonment_rate = round(int(queue_abandoned) / int(queue_total), 4) if queue_total else 0.0

    return {
        "store_id": store_id,
        "date": str(for_date),
        "unique_visitors": unique_visitors,
        "conversion_rate": conversion_rate,
        "avg_dwell_per_zone": avg_dwell_per_zone,
        "current_queue_depth": int(current_depth),
        "abandonment_rate": abandonment_rate,
    }
