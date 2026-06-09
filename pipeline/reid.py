"""Re-ID: detect re-entering visitors and assign existing visitor_id. T-11."""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

import numpy as np

from pipeline.tracker import Track


@dataclass
class ReIDResult:
    track_id: int
    visitor_id: str
    is_reentry: bool


class ReIDTracker:
    """Assigns visitor_ids to entry-threshold tracks.

    Stub implementation: always assigns a new unique visitor_id (no appearance matching).
    Full re-ID matching (T-11) can replace this without changing the interface.
    """

    def __init__(
        self,
        similarity_threshold: float = 0.75,
        buffer_minutes: int = 10,
        store_prefix: str = "ID",
    ) -> None:
        self._prefix = store_prefix
        self._counter = 0
        self._track_map: dict[int, str] = {}  # track_id → visitor_id

    def assign_new(self, track_id: int) -> ReIDResult:
        """Assign a fresh visitor_id to a new entry-threshold track."""
        if track_id in self._track_map:
            return ReIDResult(track_id=track_id, visitor_id=self._track_map[track_id], is_reentry=False)
        self._counter += 1
        vid = f"{self._prefix}_{self._counter:05d}"
        self._track_map[track_id] = vid
        return ReIDResult(track_id=track_id, visitor_id=vid, is_reentry=False)

    def register_exit(
        self,
        track_id: int,
        visitor_id: str,
        frame_crop: np.ndarray,
        timestamp: datetime,
    ) -> None:
        pass  # no-op in stub

    def match_entry(
        self,
        track_id: int,
        frame_crop: np.ndarray,
        timestamp: datetime,
    ) -> ReIDResult:
        return self.assign_new(track_id)

    def _purge_expired(self, now: datetime) -> None:
        pass

    def reset(self) -> None:
        self._counter = 0
        self._track_map.clear()
