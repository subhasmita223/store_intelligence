"""Billing zone queue depth counter. T-10."""

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class QueueJoinEvent:
    track_id: int
    queue_depth: int       # people already in queue when this track joined
    timestamp: datetime


@dataclass
class QueueExitEvent:
    """Emitted when a track leaves the billing zone — used to build a QueueEvent."""
    queue_event_id: uuid.UUID
    track_id: int
    join_ts: datetime
    served_ts: Optional[datetime]  # when this person reached the counter (depth==1)
    exit_ts: datetime
    wait_seconds: int
    queue_position_at_join: int
    abandoned: bool


@dataclass
class _QueueEntry:
    join_ts: datetime
    position: int
    served_ts: Optional[datetime] = None


class QueueDepthCounter:
    """Tracks the number of non-staff tracks currently in the billing zone.

    Returns (QueueJoinEvent | None, QueueExitEvent | None) from update().
    """

    def __init__(self, billing_zone_id: str, abandon_wait_seconds: int = 60) -> None:
        self._zone_id = billing_zone_id
        self._abandon_secs = abandon_wait_seconds
        self._in_queue: dict[int, _QueueEntry] = {}

    @property
    def current_depth(self) -> int:
        return len(self._in_queue)

    def update(
        self,
        track_id: int,
        zone_id: Optional[str],
        is_staff: bool,
        timestamp: datetime,
    ) -> tuple[Optional[QueueJoinEvent], Optional[QueueExitEvent]]:
        in_billing = (zone_id == self._zone_id) and not is_staff
        in_queue = track_id in self._in_queue

        join_event: Optional[QueueJoinEvent] = None
        exit_event: Optional[QueueExitEvent] = None

        if in_billing and not in_queue:
            depth_before = self.current_depth
            join_event = QueueJoinEvent(
                track_id=track_id, queue_depth=depth_before, timestamp=timestamp
            )
            self._in_queue[track_id] = _QueueEntry(join_ts=timestamp, position=depth_before)

        elif not in_billing and in_queue:
            entry = self._in_queue.pop(track_id)
            wait_s = max(0, int((timestamp - entry.join_ts).total_seconds()))
            abandoned = wait_s > self._abandon_secs
            served_ts = None if abandoned else (entry.served_ts or timestamp)
            exit_event = QueueExitEvent(
                queue_event_id=uuid.uuid4(),
                track_id=track_id,
                join_ts=entry.join_ts,
                served_ts=served_ts,
                exit_ts=timestamp,
                wait_seconds=wait_s,
                queue_position_at_join=entry.position,
                abandoned=abandoned,
            )

        elif in_billing and in_queue:
            # Mark as "served" when this track is the only one left (reached counter)
            entry = self._in_queue[track_id]
            if entry.served_ts is None and self.current_depth == 1:
                entry.served_ts = timestamp

        return join_event, exit_event

    def reset(self) -> None:
        self._in_queue.clear()
