"""Zone heatmap computation. T-20."""

from collections import defaultdict
from datetime import date
from typing import Any

import asyncpg


async def compute_heatmap(
    store_id: str,
    for_date: date,
    conn: asyncpg.Connection,
) -> dict[str, Any]:
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

    enters: dict[tuple, Any] = {}
    visit_counts: dict[str, int] = defaultdict(int)
    dwell_ms_lists: dict[str, list[float]] = defaultdict(list)
    zone_name_map: dict[str, str] = {}

    for r in zone_rows:
        zone_name_map[r["zone_id"]] = r["zone_name"]
        key = (r["track_id"], r["zone_id"])
        if r["event_type"] == "zone_entered":
            visit_counts[r["zone_id"]] += 1
            enters[key] = r["event_ts"]
        elif r["event_type"] == "zone_exited" and key in enters:
            enter_ts = enters.pop(key)
            dwell_ms_lists[r["zone_id"]].append(
                (r["event_ts"] - enter_ts).total_seconds() * 1000
            )

    total_sessions = int(
        await conn.fetchval(
            """
            SELECT COUNT(DISTINCT id_token) FROM events
            WHERE store_id = $1
              AND event_type = 'entry'
              AND NOT COALESCE(is_staff, false)
              AND DATE(event_ts) = $2::date
            """,
            store_id,
            for_date,
        ) or 0
    )

    zones = []
    for zone_id, zone_name in zone_name_map.items():
        vc = visit_counts[zone_id]
        dwells = dwell_ms_lists[zone_id]
        avg_dwell = int(sum(dwells) / len(dwells)) if dwells else 0
        zones.append(
            {"zone_id": zone_id, "zone_name": zone_name, "visit_count": vc, "avg_dwell_ms": avg_dwell}
        )

    max_vc = max((z["visit_count"] for z in zones), default=1) or 1
    for z in zones:
        z["score"] = round(z["visit_count"] / max_vc * 100)

    return {
        "store_id": store_id,
        "data_confidence": total_sessions >= 20,
        "zones": zones,
    }
