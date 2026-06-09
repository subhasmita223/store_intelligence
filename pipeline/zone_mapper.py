"""Map track centroids to named zones using store_layout.json polygons. T-06."""

import json
import math
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from pipeline.tracker import Track


@dataclass
class ZoneTransition:
    track_id: int
    from_zone: Optional[str]
    to_zone: Optional[str]
    timestamp: datetime


def _point_in_polygon(px: float, py: float, polygon: list[list[float]]) -> bool:
    """Ray-casting point-in-polygon test. Boundary counts as inside."""
    inside = False
    n = len(polygon)
    j = n - 1
    for i in range(n):
        xi, yi = polygon[i]
        xj, yj = polygon[j]
        if ((yi > py) != (yj > py)) and (px < (xj - xi) * (py - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside


def _polygon_area(polygon: list[list[float]]) -> float:
    """Shoelace formula — used to prefer smaller zones on overlap."""
    n = len(polygon)
    area = 0.0
    j = n - 1
    for i in range(n):
        area += (polygon[j][0] + polygon[i][0]) * (polygon[j][1] - polygon[i][1])
        j = i
    return abs(area) / 2.0


class ZoneMapper:
    """Point-in-polygon zone assignment per camera.

    Smaller zones take priority when a centroid falls inside overlapping polygons.
    Returns zone_id=None for centroids outside all defined zones.
    """

    def __init__(self, layout_path: Path, camera_id: str) -> None:
        data = json.loads(layout_path.read_text())
        self.store_id: str = data["store_id"]
        self.store_code: str = data["store_code"]

        cam = data["cameras"][camera_id]
        self.camera_id = camera_id
        self.role: str = cam["role"]
        self.resolution: list[int] = cam["resolution"]
        self.entry_threshold: Optional[dict] = cam.get("entry_threshold")

        # Sort zones smallest-area-first so tighter zones win on overlap
        raw_zones = cam.get("zones", [])
        self._zones = sorted(raw_zones, key=lambda z: _polygon_area(z["polygon"]))

        # track_id -> zone_id of the zone it was in last frame
        self._prev: dict[int, Optional[str]] = {}

    # ── public helpers ──────────────────────────────────────────────────────

    def zone_meta(self, zone_id: str) -> Optional[dict]:
        for z in self._zones:
            if z["zone_id"] == zone_id:
                return z
        return None

    # ── main method ─────────────────────────────────────────────────────────

    def assign(
        self,
        tracks: list[Track],
        timestamp: datetime,
    ) -> tuple[dict[int, Optional[str]], list[ZoneTransition]]:
        """Return (track_id → current_zone_id, transitions detected this frame)."""
        current: dict[int, Optional[str]] = {}
        transitions: list[ZoneTransition] = []

        active_ids = {t.track_id for t in tracks}

        for track in tracks:
            cx, cy = track.centroid
            assigned: Optional[str] = None
            for zone in self._zones:          # sorted smallest first
                if _point_in_polygon(cx, cy, zone["polygon"]):
                    assigned = zone["zone_id"]
                    break
            current[track.track_id] = assigned

            prev = self._prev.get(track.track_id)
            if prev != assigned:
                transitions.append(
                    ZoneTransition(
                        track_id=track.track_id,
                        from_zone=prev,
                        to_zone=assigned,
                        timestamp=timestamp,
                    )
                )

        # tracks that vanished — emit exit transition
        for tid, zone in self._prev.items():
            if tid not in active_ids and zone is not None:
                transitions.append(
                    ZoneTransition(track_id=tid, from_zone=zone, to_zone=None, timestamp=timestamp)
                )

        self._prev = current
        return current, transitions
