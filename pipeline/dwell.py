"""Dwell time accumulator — emit DwellEvent every 30s of continuous zone presence. T-09."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from pipeline.zone_mapper import ZoneTransition


@dataclass
class DwellEvent:
    track_id: int
    zone_id: str
    dwell_ms: int
    timestamp: datetime


class DwellAccumulator:
    """Tracks per-(track_id, zone_id) entry time.

    Emits a DwellEvent every 30 continuous seconds in the same zone.
    Zone exit resets the counter; re-entry in the same zone starts fresh.
    """

    DWELL_INTERVAL_MS: int = 30_000

    def __init__(self) -> None:
        # (track_id, zone_id) → timestamp when track entered this zone
        self._entries: dict[tuple[int, str], datetime] = {}
        # (track_id, zone_id) → timestamp of last emitted dwell event
        self._last_emit: dict[tuple[int, str], datetime] = {}

    def update(
        self,
        transitions: list[ZoneTransition],
        current_time: datetime,
    ) -> list[DwellEvent]:
        """Process zone transitions and return any new dwell events."""
        events: list[DwellEvent] = []

        for t in transitions:
            # track exited a zone
            if t.from_zone is not None:
                key = (t.track_id, t.from_zone)
                self._entries.pop(key, None)
                self._last_emit.pop(key, None)

            # track entered a zone
            if t.to_zone is not None:
                key = (t.track_id, t.to_zone)
                self._entries[key] = t.timestamp
                self._last_emit[key] = t.timestamp

        # check all active presences for 30s dwell ticks
        for (track_id, zone_id), enter_time in list(self._entries.items()):
            key = (track_id, zone_id)
            last = self._last_emit.get(key, enter_time)
            elapsed_ms = (current_time - last).total_seconds() * 1000

            while elapsed_ms >= self.DWELL_INTERVAL_MS:
                emit_time = last + timedelta(milliseconds=self.DWELL_INTERVAL_MS)
                events.append(
                    DwellEvent(
                        track_id=track_id,
                        zone_id=zone_id,
                        dwell_ms=self.DWELL_INTERVAL_MS,
                        timestamp=emit_time,
                    )
                )
                last = emit_time
                self._last_emit[key] = emit_time
                elapsed_ms = (current_time - last).total_seconds() * 1000

        return events

    def zone_entry_time(self, track_id: int) -> Optional[datetime]:
        """Return when this track last entered its current zone."""
        for (tid, _), enter_time in self._entries.items():
            if tid == track_id:
                return enter_time
        return None
