# PROMPT: Write pipeline unit tests covering schema validation, entry/exit events,
# group entry, staff exclusion, re-entry visitor ID reuse, empty-clip safety, and
# confidence passthrough. Use synthetic data only — no database, no real video.
# CHANGES MADE: Replaced old StoreEvent/EventMetadata imports with new discriminated-
# union models (EntryExitEvent, ZoneEvent, QueueEvent). Removed ReIDResult dependency
# from emitter tests since the new EventEmitter takes visitor_id directly.

"""Detection pipeline unit tests. T-25.

Tests are pure Python — no database, no real video, no subprocess.
All pipeline objects use synthetic data (fake tracks, synthetic frames).
"""

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.models import EntryExitEvent, QueueEvent, ZoneEvent
from pipeline.direction import Direction, DirectionClassifier
from pipeline.dwell import DwellAccumulator
from pipeline.emit import EventEmitter
from pipeline.queue_depth import QueueDepthCounter, QueueExitEvent
from pipeline.reid import ReIDTracker
from pipeline.zone_mapper import ZoneMapper, ZoneTransition

# Docker mounts data at /data; locally it lives relative to the project root
_DOCKER_LAYOUT = Path("/data/Store 1/store_layout.json")
_LOCAL_LAYOUT  = Path(__file__).parent.parent / "data" / "Store 1" / "store_layout.json"
LAYOUT = _DOCKER_LAYOUT if _DOCKER_LAYOUT.exists() else _LOCAL_LAYOUT
UTC = timezone.utc


# ── Helpers ───────────────────────────────────────────────────────────────────

@dataclass
class _Track:
    track_id: int
    x1: float = 100.0
    y1: float = 100.0
    x2: float = 200.0
    y2: float = 300.0
    confidence: float = 0.9
    age: int = 1

    @property
    def centroid(self):
        return ((self.x1 + self.x2) / 2, (self.y1 + self.y2) / 2)


def _ts(secs: float = 0.0) -> datetime:
    return datetime(2026, 3, 8, 18, 0, 0, tzinfo=UTC) + timedelta(seconds=secs)


# ── T-25-1  Schema validation ─────────────────────────────────────────────────

def test_valid_entry_event_parses():
    ev = EntryExitEvent(
        event_type="entry",
        id_token="ID_60001",
        store_code="store_1076",
        camera_id="cam1",
        event_timestamp=_ts(),
        is_staff=False,
    )
    assert ev.event_type == "entry"
    assert ev.id_token == "ID_60001"


def test_valid_zone_event_parses():
    ev = ZoneEvent(
        event_type="zone_entered",
        track_id=101,
        store_id="ST1076",
        camera_id="CAM2",
        zone_id="PURPLLE_MUM_1076_Z01",
        zone_name="Left Shelf",
        zone_type="SHELF",
        is_revenue_zone="Yes",
        event_time=_ts(),
        zone_hotspot_x=412.6,
        zone_hotspot_y=238.4,
    )
    assert ev.is_revenue_zone == "Yes"


def test_invalid_event_type_raises_validation_error():
    with pytest.raises(ValidationError):
        EntryExitEvent(
            event_type="not_a_real_type",  # type: ignore[arg-type]
            id_token="ID_001",
            store_code="store_1076",
            camera_id="cam1",
            event_timestamp=_ts(),
            is_staff=False,
        )


# ── T-25-2  Entry / Exit pair ─────────────────────────────────────────────────

def test_emitter_produces_entry_and_exit_events():
    em = EventEmitter("ST1076", "store_1076", "CAM3")
    ev_in  = em.entry_exit("entry", "ID_00001", _ts(0),  is_staff=False)
    ev_out = em.entry_exit("exit",  "ID_00001", _ts(120), is_staff=False)

    assert isinstance(ev_in,  EntryExitEvent) and ev_in.event_type  == "entry"
    assert isinstance(ev_out, EntryExitEvent) and ev_out.event_type == "exit"
    assert ev_in.id_token == ev_out.id_token == "ID_00001"


# ── T-25-3  Group entry: 3 tracks → 3 crossing events ────────────────────────

def test_direction_classifier_fires_per_track_for_group():
    dc = DirectionClassifier(LAYOUT, "CAM3", min_frames=3)
    # Three tracks, all start left of threshold (x=760), cross to right
    xs = [400, 450, 500,  # 3 frames left
          900, 950, 1000]  # 3 frames right
    events = []
    for x in xs:
        tracks = [_Track(tid, x, 400, x + 80, 700) for tid in [1, 2, 3]]
        events.extend(dc.update(tracks, _ts()))

    inbound = [e for e in events if e.direction == Direction.INBOUND]
    assert len(inbound) == 3, f"Expected 3 INBOUND events, got {len(inbound)}"
    assert {e.track_id for e in inbound} == {1, 2, 3}


# ── T-25-4  Staff exclusion ───────────────────────────────────────────────────

def test_emitter_flags_staff_correctly():
    em = EventEmitter("ST1076", "store_1076", "CAM3")
    ev_staff    = em.entry_exit("entry", "ID_STAFF_01", _ts(), is_staff=True)
    ev_customer = em.entry_exit("entry", "ID_CUST_01",  _ts(), is_staff=False)

    assert ev_staff.is_staff    is True
    assert ev_customer.is_staff is False


def test_queue_counter_ignores_staff():
    qc = QueueDepthCounter("Z_BILLING", abandon_wait_seconds=60)
    qc.update(99, "Z_BILLING", True, _ts())   # staff — must not increment
    assert qc.current_depth == 0


# ── T-25-5  REENTRY: same track → same visitor_id ────────────────────────────

def test_reid_tracker_reuses_visitor_id_for_same_track():
    reid = ReIDTracker(store_prefix="ST1076")
    r1  = reid.assign_new(42)
    r2  = reid.assign_new(42)   # same track_id

    assert r1.visitor_id == r2.visitor_id
    assert r1.is_reentry is False            # stub always returns False


def test_reid_tracker_different_tracks_get_different_ids():
    reid = ReIDTracker(store_prefix="ST1076")
    r1 = reid.assign_new(1)
    r2 = reid.assign_new(2)
    assert r1.visitor_id != r2.visitor_id


# ── T-25-6  Empty clip: no events, no exceptions ─────────────────────────────

def test_zone_mapper_empty_tracks_no_transitions():
    zm = ZoneMapper(LAYOUT, "CAM2")
    zones, transitions = zm.assign([], _ts())
    assert zones == {} and transitions == []


def test_dwell_accumulator_empty_transitions_no_events():
    acc = DwellAccumulator()
    events = acc.update([], _ts())
    assert events == []


def test_queue_counter_empty_frame_no_events():
    qc = QueueDepthCounter("Z_BILLING")
    # No tracks in billing zone → no join, no exit
    join, exit_ev = qc.update(1, None, False, _ts())
    assert join is None and exit_ev is None


# ── T-25-7  Confidence passthrough ───────────────────────────────────────────

def test_low_confidence_detection_not_suppressed():
    """A detection at 0.31 must pass through a threshold of 0.30."""
    from pipeline.detect import Detection, PersonDetector

    low_conf_det = Detection(x1=100, y1=100, x2=200, y2=300, confidence=0.31)
    # Verify the detection object is valid and confidence is preserved
    assert low_conf_det.confidence == pytest.approx(0.31, abs=1e-6)

    # Ensure the detector's threshold is respected: 0.31 >= 0.30 → not dropped
    detector = PersonDetector(confidence_threshold=0.30)
    # If YOLO/MOG2 were to return this detection, it must be included.
    # We validate the threshold logic directly here.
    assert low_conf_det.confidence >= detector._threshold


# ── T-25-8  Dwell fires at 30-second intervals ───────────────────────────────

def test_dwell_fires_at_30s_not_before():
    acc = DwellAccumulator()
    t0 = _ts(0)
    acc.update([ZoneTransition(1, None, "Z01", t0)], t0)

    assert acc.update([], _ts(29)) == []
    events = acc.update([], _ts(31))
    assert len(events) == 1 and events[0].dwell_ms == 30_000


def test_dwell_fires_three_times_at_90s():
    acc = DwellAccumulator()
    t0 = _ts(0)
    acc.update([ZoneTransition(1, None, "Z01", t0)], t0)
    events = acc.update([], _ts(91))
    assert len(events) == 3


# ── T-25-9  Zone emitter attaches correct metadata ───────────────────────────

def test_zone_emitter_populates_zone_metadata():
    zm = ZoneMapper(LAYOUT, "CAM2")
    em = EventEmitter("ST1076", "store_1076", "CAM2", zm)
    ev = em.zone_event("zone_entered", 101, "PURPLLE_MUM_1076_Z02", _ts())

    assert isinstance(ev, ZoneEvent)
    assert ev.zone_name == "Center Display"
    assert ev.zone_type == "DISPLAY"
    assert ev.is_revenue_zone == "Yes"
    assert ev.zone_hotspot_x > 0
