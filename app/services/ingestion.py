"""Event ingest and deduplication service. T-16."""

import re
import uuid
from typing import Sequence

import asyncpg

from app.models import EntryExitEvent, IngestError, IngestResponse, QueueEvent, StoreEvent, ZoneEvent

_NAMESPACE = uuid.NAMESPACE_URL

# Column order must stay in sync with the events table definition in 001_initial_schema.py
_COLUMNS = (
    "event_id", "event_type", "store_id", "camera_id", "event_ts",
    "id_token", "is_staff", "gender_pred", "age_pred", "age_bucket",
    "is_face_hidden", "group_id", "group_size",
    "track_id", "zone_id", "zone_name", "zone_type", "is_revenue_zone",
    "zone_hotspot_x", "zone_hotspot_y", "gender", "age",
    "queue_event_id", "queue_join_ts", "queue_served_ts", "queue_exit_ts",
    "wait_seconds", "queue_position_at_join", "abandoned",
    "raw",
)

_INSERT_SQL = (
    f"INSERT INTO events ({', '.join(_COLUMNS)}) "
    f"VALUES ({', '.join(f'${i + 1}' for i in range(len(_COLUMNS)))})"
    " ON CONFLICT (event_id) DO NOTHING"
)


def _canonical_store(raw: str) -> str:
    m = re.search(r"(\d+)", raw)
    return f"ST{m.group(1)}" if m else raw


def _to_row(ev: StoreEvent) -> tuple:
    if isinstance(ev, EntryExitEvent):
        eid = uuid.uuid5(
            _NAMESPACE,
            f"{ev.event_type}:{ev.id_token}:{ev.store_code}:{ev.event_timestamp.isoformat()}",
        )
        return (
            eid, ev.event_type, _canonical_store(ev.store_code), ev.camera_id, ev.event_timestamp,
            ev.id_token, ev.is_staff, ev.gender_pred, ev.age_pred, ev.age_bucket,
            ev.is_face_hidden, ev.group_id, ev.group_size,
            None, None, None, None, None, None, None, None, None,
            None, None, None, None, None, None, None,
            ev.model_dump(mode="json"),
        )
    if isinstance(ev, ZoneEvent):
        eid = uuid.uuid5(
            _NAMESPACE,
            f"{ev.event_type}:{ev.track_id}:{ev.store_id}:{ev.camera_id}:{ev.zone_id}:{ev.event_time.isoformat()}",
        )
        return (
            eid, ev.event_type, ev.store_id, ev.camera_id, ev.event_time,
            None, None, None, None, ev.age_bucket,
            None, None, None,
            ev.track_id, ev.zone_id, ev.zone_name, ev.zone_type, ev.is_revenue_zone == "Yes",
            ev.zone_hotspot_x, ev.zone_hotspot_y, ev.gender, ev.age,
            None, None, None, None, None, None, None,
            ev.model_dump(mode="json"),
        )
    # QueueEvent — use its own UUID as the dedup key
    ev_q: QueueEvent = ev  # type: ignore[assignment]
    return (
        ev_q.queue_event_id, ev_q.event_type, ev_q.store_id, ev_q.camera_id, ev_q.queue_join_ts,
        None, None, None, None, ev_q.age_bucket,
        None, None, None,
        ev_q.track_id, ev_q.zone_id, ev_q.zone_name, ev_q.zone_type, ev_q.is_revenue_zone == "Yes",
        ev_q.zone_hotspot_x, ev_q.zone_hotspot_y, ev_q.gender, ev_q.age,
        ev_q.queue_event_id, ev_q.queue_join_ts, ev_q.queue_served_ts, ev_q.queue_exit_ts,
        ev_q.wait_seconds, ev_q.queue_position_at_join, ev_q.abandoned,
        ev_q.model_dump(mode="json"),
    )


async def ingest_batch(
    events: Sequence[StoreEvent],
    conn: asyncpg.Connection,
) -> IngestResponse:
    rows = [_to_row(ev) for ev in events]
    event_ids = [r[0] for r in rows]

    existing = {
        row["event_id"]
        for row in await conn.fetch(
            "SELECT event_id FROM events WHERE event_id = ANY($1::uuid[])", event_ids
        )
    }

    new_rows = [r for r in rows if r[0] not in existing]

    if new_rows:
        try:
            await conn.executemany(_INSERT_SQL, new_rows)
        except asyncpg.PostgresError as exc:
            return IngestResponse(
                accepted=0,
                rejected=len(events),
                errors=[IngestError(index=-1, message=str(exc))],
            )

    return IngestResponse(accepted=len(new_rows), rejected=0, errors=[])
