"""Translate pipeline state into structured StoreEvent objects. T-13."""

from datetime import datetime
from typing import Optional

from app.models import EntryExitEvent, QueueEvent, ZoneEvent
from pipeline.queue_depth import QueueExitEvent
from pipeline.zone_mapper import ZoneMapper


class EventEmitter:
    """Converts per-frame pipeline signals into spec-compliant event objects.

    entry/exit  → EntryExitEvent  (id_token, store_code, camera_id, demographics)
    zone_*      → ZoneEvent       (track_id, store_id, zone metadata)
    queue_*     → QueueEvent      (track_id, store_id, all queue timing fields)
    """

    def __init__(
        self,
        store_id: str,
        store_code: str,
        camera_id: str,
        zone_mapper: Optional[ZoneMapper] = None,
    ) -> None:
        self.store_id = store_id
        self.store_code = store_code
        self.camera_id = camera_id
        self._zone_mapper = zone_mapper

    # ── Entry / Exit ─────────────────────────────────────────────────────────

    def entry_exit(
        self,
        event_type: str,           # "entry" or "exit"
        visitor_id: str,
        timestamp: datetime,
        is_staff: bool,
        gender_pred: Optional[str] = None,
        age_pred: Optional[int] = None,
        age_bucket: Optional[str] = None,
        is_face_hidden: bool = False,
        group_id: Optional[str] = None,
        group_size: Optional[int] = None,
    ) -> EntryExitEvent:
        return EntryExitEvent(
            event_type=event_type,          # type: ignore[arg-type]
            id_token=visitor_id,
            store_code=self.store_code,
            camera_id=self.camera_id,
            event_timestamp=timestamp,
            is_staff=is_staff,
            gender_pred=gender_pred,        # type: ignore[arg-type]
            age_pred=age_pred,
            age_bucket=age_bucket,
            is_face_hidden=is_face_hidden,
            group_id=group_id,
            group_size=group_size,
        )

    # ── Zone events ──────────────────────────────────────────────────────────

    def zone_event(
        self,
        event_type: str,           # "zone_entered" or "zone_exited"
        track_id: int,
        zone_id: str,
        timestamp: datetime,
    ) -> Optional[ZoneEvent]:
        meta = self._zone_meta(zone_id)
        if meta is None:
            return None
        return ZoneEvent(
            event_type=event_type,          # type: ignore[arg-type]
            track_id=track_id,
            store_id=self.store_id,
            camera_id=self.camera_id,
            zone_id=zone_id,
            zone_name=meta["zone_name"],
            zone_type=meta["zone_type"],
            is_revenue_zone="Yes" if meta["is_revenue_zone"] else "No",
            event_time=timestamp,
            zone_hotspot_x=float(meta["hotspot"][0]),
            zone_hotspot_y=float(meta["hotspot"][1]),
        )

    # ── Queue events ─────────────────────────────────────────────────────────

    def queue_event(
        self,
        exit_ev: QueueExitEvent,
        zone_id: str,
    ) -> Optional[QueueEvent]:
        meta = self._zone_meta(zone_id)
        if meta is None:
            return None
        event_type = "queue_abandoned" if exit_ev.abandoned else "queue_completed"
        return QueueEvent(
            queue_event_id=exit_ev.queue_event_id,
            event_type=event_type,          # type: ignore[arg-type]
            track_id=exit_ev.track_id,
            store_id=self.store_id,
            camera_id=self.camera_id,
            zone_id=zone_id,
            zone_name=meta["zone_name"],
            zone_type="BILLING",
            is_revenue_zone="Yes",
            queue_join_ts=exit_ev.join_ts,
            queue_served_ts=exit_ev.served_ts,
            queue_exit_ts=exit_ev.exit_ts,
            wait_seconds=exit_ev.wait_seconds,
            queue_position_at_join=exit_ev.queue_position_at_join,
            abandoned=exit_ev.abandoned,
            zone_hotspot_x=float(meta["hotspot"][0]),
            zone_hotspot_y=float(meta["hotspot"][1]),
        )

    # ── internal ─────────────────────────────────────────────────────────────

    def _zone_meta(self, zone_id: str) -> Optional[dict]:
        if self._zone_mapper is None:
            return None
        return self._zone_mapper.zone_meta(zone_id)
