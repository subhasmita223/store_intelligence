"""ByteTrack multi-object tracker. T-05."""

from dataclasses import dataclass
from unittest.mock import MagicMock

import numpy as np

from pipeline.detect import Detection


@dataclass
class Track:
    track_id: int
    x1: float
    y1: float
    x2: float
    y2: float
    confidence: float
    age: int

    @property
    def centroid(self) -> tuple[float, float]:
        return ((self.x1 + self.x2) / 2, (self.y1 + self.y2) / 2)

    @property
    def bbox(self) -> list[float]:
        return [self.x1, self.y1, self.x2, self.y2]

    def to_dict(self) -> dict:
        return {
            "track_id": self.track_id,
            "bbox": self.bbox,
            "confidence": round(self.confidence, 6),
        }


def _iou(a: list[float], b: list[float]) -> float:
    """Intersection-over-Union for two [x1,y1,x2,y2] boxes."""
    ix1, iy1 = max(a[0], b[0]), max(a[1], b[1])
    ix2, iy2 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    if inter == 0:
        return 0.0
    area_a = (a[2] - a[0]) * (a[3] - a[1])
    area_b = (b[2] - b[0]) * (b[3] - b[1])
    return inter / (area_a + area_b - inter)


class ByteTracker:
    """Wraps boxmot ByteTrack for stable per-frame track ID assignment.

    Falls back to a simple IoU-based tracker when boxmot is unavailable.
    track_id is stable while the track is active.
    Lost tracks are held for track_buffer frames before deletion.
    State resets between clips via reset().
    """

    def __init__(
        self,
        track_thresh: float = 0.5,
        track_buffer: int = 30,
        match_thresh: float = 0.8,
    ) -> None:
        self._track_thresh = track_thresh
        self._track_buffer = track_buffer
        self._match_thresh = match_thresh
        self._ages: dict[int, int] = {}
        try:
            from boxmot import ByteTrack
            self._ByteTrack = ByteTrack
            self._tracker = self._make_tracker()
            self._backend = "bytetrack"
        except Exception:
            self._backend = "iou"
            # IoU fallback state
            self._next_id = 1
            self._active: dict[int, list[float]] = {}   # tid -> bbox
            self._lost_age: dict[int, int] = {}         # tid -> frames since last seen
            print("[ByteTracker] boxmot unavailable — using IoU fallback")

    def _make_tracker(self):
        return self._ByteTrack(
            track_thresh=self._track_thresh,
            track_buffer=self._track_buffer,
            match_thresh=self._match_thresh,
        )

    def update(self, detections: list[Detection], frame: np.ndarray) -> list[Track]:
        """Feed detections for one frame; return active tracks with stable IDs."""
        if self._backend == "bytetrack":
            return self._update_bytetrack(detections, frame)
        return self._update_iou(detections, frame)

    def _update_bytetrack(self, detections: list[Detection], frame: np.ndarray) -> list[Track]:
        if detections:
            dets = np.array(
                [[d.x1, d.y1, d.x2, d.y2, d.confidence, 0.0] for d in detections],
                dtype=np.float32,
            )
        else:
            dets = np.empty((0, 6), dtype=np.float32)
        raw = self._tracker.update(dets, frame)
        result: list[Track] = []
        for t in raw:
            tid = int(t[4])
            self._ages[tid] = self._ages.get(tid, 0) + 1
            result.append(Track(
                track_id=tid, x1=float(t[0]), y1=float(t[1]),
                x2=float(t[2]), y2=float(t[3]),
                confidence=float(t[5]), age=self._ages[tid],
            ))
        return result

    def _update_iou(self, detections: list[Detection], frame: np.ndarray) -> list[Track]:
        """Greedy IoU matching with lost-track buffering."""
        # Age out tracks lost for too long
        to_remove = [tid for tid, age in self._lost_age.items() if age > self._track_buffer]
        for tid in to_remove:
            self._active.pop(tid, None)
            self._lost_age.pop(tid, None)
            self._ages.pop(tid, None)

        # Increment lost counters for all active tracks (reset below for matched ones)
        for tid in list(self._active):
            self._lost_age[tid] = self._lost_age.get(tid, 0) + 1

        matched_tids: set[int] = set()
        result: list[Track] = []

        for det in detections:
            det_box = [det.x1, det.y1, det.x2, det.y2]
            best_tid, best_iou = -1, self._match_thresh
            for tid, bbox in self._active.items():
                if tid in matched_tids:
                    continue
                score = _iou(det_box, bbox)
                if score > best_iou:
                    best_iou, best_tid = score, tid

            if best_tid >= 0:
                tid = best_tid
                self._lost_age[tid] = 0
            else:
                tid = self._next_id
                self._next_id += 1

            self._active[tid] = det_box
            matched_tids.add(tid)
            self._ages[tid] = self._ages.get(tid, 0) + 1
            result.append(Track(
                track_id=tid, x1=det.x1, y1=det.y1,
                x2=det.x2, y2=det.y2,
                confidence=det.confidence, age=self._ages[tid],
            ))

        return result

    def reset(self) -> None:
        """Clear all track state — call between clips."""
        self._ages = {}
        if self._backend == "bytetrack":
            self._tracker = self._make_tracker()
        else:
            self._next_id = 1
            self._active.clear()
            self._lost_age.clear()


# ── Unit tests ─────────────────────────────────────────────────────────────────

def _make_tracker(raw_frames: list[list]) -> "ByteTracker":
    """Build a ByteTracker with a mocked inner tracker.

    raw_frames: list of per-frame raw outputs, each a list of rows
                [x1, y1, x2, y2, track_id, conf, cls, det_ind].
    Successive update() calls consume successive entries.
    """
    tracker = ByteTracker.__new__(ByteTracker)
    tracker._ages = {}
    tracker._track_thresh = 0.5
    tracker._track_buffer = 30
    tracker._match_thresh = 0.8

    inner = MagicMock()
    inner.update.side_effect = [
        np.array(rows, dtype=np.float64) if rows else np.empty((0, 8))
        for rows in raw_frames
    ]
    tracker._tracker = inner

    new_inner = MagicMock()
    new_inner.update.return_value = np.empty((0, 8))
    tracker._ByteTrack = MagicMock(return_value=new_inner)
    return tracker


def _det(x1=10.0, y1=20.0, x2=100.0, y2=200.0, conf=0.9) -> Detection:
    from pipeline.detect import Detection
    return Detection(x1=x1, y1=y1, x2=x2, y2=y2, confidence=conf)


def test_returns_track_with_correct_fields():
    raw = [[10, 20, 100, 200, 4, 0.94, 0, 0]]
    bt = _make_tracker([raw])
    tracks = bt.update([_det()], np.zeros((480, 640, 3), dtype=np.uint8))

    assert len(tracks) == 1
    t = tracks[0]
    assert t.track_id == 4
    assert t.bbox == [10.0, 20.0, 100.0, 200.0]
    assert abs(t.confidence - 0.94) < 1e-4


def test_to_dict_shape():
    raw = [[0, 0, 50, 50, 7, 0.8, 0, 0]]
    bt = _make_tracker([raw])
    tracks = bt.update([_det()], np.zeros((480, 640, 3), dtype=np.uint8))

    d = tracks[0].to_dict()
    assert set(d.keys()) == {"track_id", "bbox", "confidence"}
    assert isinstance(d["track_id"], int)
    assert len(d["bbox"]) == 4


def test_empty_detections_returns_empty_list():
    bt = _make_tracker([[]])
    tracks = bt.update([], np.zeros((480, 640, 3), dtype=np.uint8))
    assert tracks == []


def test_track_id_stable_across_frames():
    frame1 = [[10, 20, 100, 200, 3, 0.9, 0, 0]]
    frame2 = [[12, 22, 102, 202, 3, 0.88, 0, 0]]   # same track_id=3, shifted bbox
    bt = _make_tracker([frame1, frame2])

    blank = np.zeros((480, 640, 3), dtype=np.uint8)
    t1 = bt.update([_det()], blank)
    t2 = bt.update([_det()], blank)

    assert t1[0].track_id == t2[0].track_id == 3


def test_age_increments_each_frame():
    tid = 5
    raw = [[0, 0, 50, 50, tid, 0.8, 0, 0]]
    # feed same track over 3 frames
    bt = _make_tracker([raw, raw, raw])

    blank = np.zeros((480, 640, 3), dtype=np.uint8)
    for expected_age in [1, 2, 3]:
        tracks = bt.update([_det()], blank)
        assert tracks[0].age == expected_age


def test_reset_clears_age_and_creates_new_tracker():
    raw = [[0, 0, 50, 50, 1, 0.9, 0, 0]]
    bt = _make_tracker([raw])

    blank = np.zeros((480, 640, 3), dtype=np.uint8)
    bt.update([_det()], blank)
    assert bt._ages == {1: 1}

    bt.reset()
    assert bt._ages == {}
    # _ByteTrack should have been called once to create the new tracker
    bt._ByteTrack.assert_called_once()


def test_multiple_tracks_same_frame():
    raw = [
        [0,  0,  50, 50, 1, 0.9, 0, 0],
        [60, 0, 110, 50, 2, 0.8, 0, 0],
        [120, 0, 170, 50, 3, 0.7, 0, 0],
    ]
    bt = _make_tracker([raw])
    tracks = bt.update([_det(), _det(), _det()], np.zeros((480, 640, 3), dtype=np.uint8))

    assert len(tracks) == 3
    assert [t.track_id for t in tracks] == [1, 2, 3]
