"""Cross-camera deduplicator — suppress double-counting in overlap zones. T-12."""

from datetime import datetime, timedelta
from typing import Optional

from pipeline.emit import PipelineEvent


class CrossCameraDeduplicator:
    """Suppresses floor-camera ZONE_ENTER events when the same visitor_id
    already appeared in the entry camera within the overlap zone and time window.

    Conservative: only deduplicates confirmed overlap zone events.
    Suppressed events are logged, not silently discarded.
    """

    def __init__(
        self,
        overlap_zone_ids: list[str],
        window_seconds: int = 5,
    ) -> None:
        raise NotImplementedError

    def filter(
        self,
        events: list["PipelineEvent"],
        source_camera_id: str,
        timestamp: datetime,
    ) -> tuple[list["PipelineEvent"], list["PipelineEvent"]]:
        """Return (kept_events, suppressed_events)."""
        raise NotImplementedError
