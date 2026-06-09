"""Entry/exit direction classifier — inbound vs outbound crossing. T-07."""

import json
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional

from pipeline.tracker import Track


class Direction(str, Enum):
    INBOUND = "INBOUND"
    OUTBOUND = "OUTBOUND"


@dataclass
class CrossingEvent:
    track_id: int
    direction: Direction
    timestamp: datetime


def _cross_product_side(point: tuple[float, float], line: list) -> int:
    """Return +1 or -1: which side of the line the point is on.

    Uses the 2-D cross-product sign of (line_vec × point_vec).
    """
    (x1, y1), (x2, y2) = line
    px, py = point
    cross = (x2 - x1) * (py - y1) - (y2 - y1) * (px - x1)
    return 1 if cross >= 0 else -1


# Which (prev_side, curr_side) pair means INBOUND for each direction keyword.
# Derived from _cross_product_side for common camera orientations:
#   "right" → vertical line, moving left→right: prev=+1, curr=-1
#   "left"  → vertical line, moving right→left: prev=-1, curr=+1
#   "down"  → horizontal line, moving top→bottom: prev=-1, curr=+1
#   "up"    → horizontal line, moving bottom→top: prev=+1, curr=-1
_INBOUND_PAIRS: dict[str, tuple[int, int]] = {
    "right": (+1, -1),
    "left":  (-1, +1),
    "down":  (-1, +1),
    "up":    (+1, -1),
}


class DirectionClassifier:
    """Detects when a track crosses the entry threshold line.

    Requires at least min_frames consistent positions on one side before firing.
    Updates committed side on each stable crossing — fires INBOUND and OUTBOUND.
    """

    def __init__(self, layout_path: Path, camera_id: str, min_frames: int = 3) -> None:
        data = json.loads(Path(layout_path).read_text())
        cam = data["cameras"][camera_id]
        thr = cam["entry_threshold"]
        self._line: list = thr["line"]
        self._inbound_direction: str = thr["inbound_direction"]
        self._min_frames = min_frames

        # track_id → deque of recent cross-product sides
        self._side_history: dict[int, deque] = {}
        # track_id → last committed side (after firing)
        self._committed_side: dict[int, int] = {}

    def update(
        self,
        tracks: list[Track],
        timestamp: datetime,
    ) -> list[CrossingEvent]:
        """Return crossing events detected in this frame update."""
        events: list[CrossingEvent] = []
        active_ids = {t.track_id for t in tracks}

        # clean up vanished tracks
        for tid in list(self._side_history):
            if tid not in active_ids:
                del self._side_history[tid]
                self._committed_side.pop(tid, None)

        for track in tracks:
            tid = track.track_id
            side = _cross_product_side(track.centroid, self._line)

            if tid not in self._side_history:
                self._side_history[tid] = deque(maxlen=self._min_frames)
            self._side_history[tid].append(side)

            history = self._side_history[tid]
            if len(history) < self._min_frames:
                continue

            # all recent frames on the same side → stable position
            sides = list(history)
            if len(set(sides)) != 1:
                continue

            current_side = sides[0]
            prev_committed = self._committed_side.get(tid)

            if prev_committed is None:
                self._committed_side[tid] = current_side
                continue

            if current_side == prev_committed:
                continue  # hasn't crossed

            # crossing detected
            inbound_pair = _INBOUND_PAIRS.get(self._inbound_direction, (+1, -1))
            direction = (
                Direction.INBOUND
                if (prev_committed, current_side) == inbound_pair
                else Direction.OUTBOUND
            )
            events.append(CrossingEvent(track_id=tid, direction=direction, timestamp=timestamp))
            self._committed_side[tid] = current_side

        return events
