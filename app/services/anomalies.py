"""Operational anomaly detection. T-21."""

from typing import Any

import asyncpg


async def detect_anomalies(
    store_id: str,
    conn: asyncpg.Connection,
) -> list[dict[str, Any]]:
    anomalies: list[dict[str, Any]] = []

    # ── BILLING_QUEUE_SPIKE ────────────────────────────────────────────────────
    # Fire when recent queue position > threshold for the last 10 minutes.
    recent_queue = await conn.fetch(
        """
        SELECT queue_position_at_join
        FROM events
        WHERE store_id = $1
          AND event_type IN ('queue_completed', 'queue_abandoned')
          AND queue_join_ts >= NOW() - INTERVAL '10 minutes'
        """,
        store_id,
    )
    if recent_queue:
        max_depth = max(r["queue_position_at_join"] for r in recent_queue)
        if max_depth > 8:
            anomalies.append(
                {
                    "type": "BILLING_QUEUE_SPIKE",
                    "severity": "CRITICAL",
                    "detail": f"Queue depth {max_depth} in the last 10 minutes",
                    "suggested_action": "Open an additional billing counter immediately",
                }
            )
        elif max_depth > 5:
            anomalies.append(
                {
                    "type": "BILLING_QUEUE_SPIKE",
                    "severity": "WARN",
                    "detail": f"Queue depth {max_depth} in the last 10 minutes",
                    "suggested_action": "Consider opening an additional billing counter",
                }
            )

    # ── CONVERSION_DROP ───────────────────────────────────────────────────────
    today_row = await conn.fetchrow(
        """
        SELECT
            COUNT(DISTINCT CASE WHEN event_type = 'entry'
                                 AND NOT COALESCE(is_staff, false) THEN id_token END) AS visitors,
            COUNT(CASE WHEN event_type = 'queue_completed'
                        AND NOT COALESCE(abandoned, true) THEN 1 END)               AS purchases
        FROM events
        WHERE store_id = $1 AND DATE(event_ts) = CURRENT_DATE
        """,
        store_id,
    )
    hist_row = await conn.fetchrow(
        """
        SELECT
            COUNT(DISTINCT CASE WHEN event_type = 'entry'
                                 AND NOT COALESCE(is_staff, false) THEN id_token END) AS visitors,
            COUNT(CASE WHEN event_type = 'queue_completed'
                        AND NOT COALESCE(abandoned, true) THEN 1 END)               AS purchases
        FROM events
        WHERE store_id = $1
          AND DATE(event_ts) BETWEEN CURRENT_DATE - 7 AND CURRENT_DATE - 1
        """,
        store_id,
    )

    hist_v = int(hist_row["visitors"] or 0)
    if hist_v == 0:
        anomalies.append(
            {
                "type": "CONVERSION_DROP",
                "severity": "INFO",
                "detail": "Fewer than 7 days of historical data available",
                "suggested_action": "Monitor conversion rate as data accumulates",
            }
        )
    else:
        today_v = int(today_row["visitors"] or 0)
        today_rate = int(today_row["purchases"] or 0) / today_v if today_v else 0.0
        hist_rate = int(hist_row["purchases"] or 0) / hist_v
        if today_v > 0 and today_rate < hist_rate * 0.7:
            anomalies.append(
                {
                    "type": "CONVERSION_DROP",
                    "severity": "WARN",
                    "detail": f"Today {today_rate:.1%} vs 7-day avg {hist_rate:.1%}",
                    "suggested_action": "Review product placement and staff engagement",
                }
            )

    # ── DEAD_ZONE ─────────────────────────────────────────────────────────────
    dead_zones = await conn.fetch(
        """
        SELECT zone_id, zone_name, MAX(event_ts) AS last_visit
        FROM events
        WHERE store_id = $1 AND event_type = 'zone_entered'
        GROUP BY zone_id, zone_name
        HAVING MAX(event_ts) < NOW() - INTERVAL '30 minutes'
        """,
        store_id,
    )
    for z in dead_zones:
        anomalies.append(
            {
                "type": "DEAD_ZONE",
                "severity": "INFO",
                "detail": f"No visitors in '{z['zone_name']}' for 30+ minutes",
                "suggested_action": f"Check product availability and visibility in {z['zone_name']}",
            }
        )

    return anomalies
