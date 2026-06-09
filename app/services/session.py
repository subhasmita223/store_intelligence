"""Visitor session reconstruction from the event stream. T-17."""

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Optional

import asyncpg


@dataclass
class VisitorSession:
    visitor_id: str
    store_id: str
    session_start: datetime
    session_end: Optional[datetime]
    is_staff: bool
    reached_zone_visit: bool = False
    reached_billing: bool = False
    completed_purchase: bool = False


async def build_sessions(
    store_id: str,
    for_date: date,
    conn: asyncpg.Connection,
) -> list[VisitorSession]:
    """Reconstruct sessions from events for a store on a given date.

    Entry opens a session; first matching Exit closes it.
    30-minute idle timeout closes a session without Exit.
    Zone visits and billing presence are matched by time-window overlap
    because entry/exit use id_token while zone/queue use track_id.
    """
    rows = await conn.fetch(
        """
        SELECT event_type, id_token, track_id, event_ts,
               COALESCE(is_staff, false) AS is_staff,
               is_revenue_zone, abandoned, queue_join_ts
        FROM events
        WHERE store_id = $1 AND DATE(event_ts) = $2::date
        ORDER BY event_ts
        """,
        store_id,
        for_date,
    )

    entries = [r for r in rows if r["event_type"] == "entry"]
    exits = [r for r in rows if r["event_type"] == "exit"]
    zone_entered = [r for r in rows if r["event_type"] == "zone_entered" and r["is_revenue_zone"]]
    queue_rows = [r for r in rows if r["event_type"] in ("queue_completed", "queue_abandoned")]

    # first exit timestamp per id_token
    exit_map: dict[str, datetime] = {}
    for r in exits:
        token = r["id_token"]
        if token and (token not in exit_map or r["event_ts"] < exit_map[token]):
            exit_map[token] = r["event_ts"]

    sessions: list[VisitorSession] = []
    for entry in entries:
        token = entry["id_token"]
        start = entry["event_ts"]
        end = exit_map.get(token) if (exit_map.get(token) and exit_map[token] > start) else None
        window_end = end or (start + timedelta(minutes=30))

        reached_zone = any(start <= r["event_ts"] <= window_end for r in zone_entered)

        reached_billing = False
        completed_purchase = False
        for r in queue_rows:
            join_ts = r["queue_join_ts"] or r["event_ts"]
            if start <= join_ts <= window_end:
                reached_billing = True
                if not r["abandoned"]:
                    completed_purchase = True

        sessions.append(
            VisitorSession(
                visitor_id=token,
                store_id=store_id,
                session_start=start,
                session_end=end,
                is_staff=entry["is_staff"],
                reached_zone_visit=reached_zone,
                reached_billing=reached_billing,
                completed_purchase=completed_purchase,
            )
        )

    return sessions
