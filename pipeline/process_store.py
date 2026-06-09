"""Main pipeline orchestrator — processes all cameras for one store. T-14."""

import json
import os
import sys
from datetime import date, datetime, time, timezone
from pathlib import Path
from typing import Any

import httpx

# Allow running from project root or from inside Docker (WORKDIR=/workspace)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.models import EntryExitEvent, QueueEvent, ZoneEvent
from pipeline.detect import PersonDetector
from pipeline.direction import DirectionClassifier
from pipeline.dwell import DwellAccumulator
from pipeline.emit import EventEmitter
from pipeline.frame_extractor import FrameExtractor
from pipeline.queue_depth import QueueDepthCounter
from pipeline.reid import ReIDTracker
from pipeline.staff import StaffClassifier
from pipeline.tracker import ByteTracker
from pipeline.zone_mapper import ZoneMapper

_BATCH_SIZE = 400
_SAMPLE_FPS_ZONE = float(os.environ.get("DETECTION_SAMPLE_FPS", "5"))
_SAMPLE_FPS_BILLING = float(os.environ.get("BILLING_SAMPLE_FPS", "3"))
_STAFF_COLOR_HEX = os.environ.get("STAFF_COLOR_HEX", "1A6B3C")
_CONFIDENCE_THRESHOLD = float(os.environ.get("CONFIDENCE_THRESHOLD", "0.3"))


def _post_batch(events: list[Any], api_url: str) -> tuple[int, int]:
    """POST up to _BATCH_SIZE events to /events/ingest. Returns (accepted, rejected)."""
    accepted = rejected = 0
    for i in range(0, len(events), _BATCH_SIZE):
        chunk = events[i : i + _BATCH_SIZE]
        payload = {"events": [e.model_dump(mode="json") for e in chunk]}
        try:
            r = httpx.post(f"{api_url}/events/ingest", json=payload, timeout=30)
            r.raise_for_status()
            body = r.json()
            accepted += body.get("accepted", 0)
            rejected += body.get("rejected", 0)
        except Exception as exc:
            print(f"    [WARN] ingest failed: {exc}", file=sys.stderr)
            rejected += len(chunk)
    return accepted, rejected


def _process_entry_camera(
    video_path: Path,
    layout_path: Path,
    camera_id: str,
    store_id: str,
    store_code: str,
    clip_start: datetime,
) -> list[Any]:
    """Run detection + direction classification; emit entry/exit events."""
    emitter = EventEmitter(store_id, store_code, camera_id)
    reid = ReIDTracker(store_prefix=store_code[:6].upper())
    staff = StaffClassifier(_STAFF_COLOR_HEX)
    direction_clf = DirectionClassifier(layout_path, camera_id)
    detector = PersonDetector(confidence_threshold=_CONFIDENCE_THRESHOLD)
    tracker = ByteTracker()
    extractor = FrameExtractor(video_path, clip_start, sample_fps=_SAMPLE_FPS_ZONE)

    events: list[Any] = []
    frame_count = 0

    for frame in extractor:
        frame_count += 1
        detections = detector.detect(frame.image)
        tracks = tracker.update(detections, frame.image)

        for track in tracks:
            staff.classify(track, frame.image)

        crossings = direction_clf.update(tracks, frame.timestamp)
        for crossing in crossings:
            is_s = staff.is_staff(crossing.track_id)
            reid_result = reid.assign_new(crossing.track_id)
            etype = "entry" if crossing.direction.value == "INBOUND" else "exit"
            ev = emitter.entry_exit(etype, reid_result.visitor_id, crossing.timestamp, is_s)
            events.append(ev)

    tracker.reset()
    staff.reset()
    print(f"    {frame_count} frames -> {len(events)} entry/exit events")
    return events


def _process_zone_camera(
    video_path: Path,
    layout_path: Path,
    camera_id: str,
    store_id: str,
    store_code: str,
    clip_start: datetime,
) -> list[Any]:
    """Run detection + zone mapping + dwell; emit zone_entered/zone_exited events."""
    zone_mapper = ZoneMapper(layout_path, camera_id)
    emitter = EventEmitter(store_id, store_code, camera_id, zone_mapper)
    dwell_acc = DwellAccumulator()
    detector = PersonDetector(confidence_threshold=_CONFIDENCE_THRESHOLD)
    tracker = ByteTracker()
    extractor = FrameExtractor(video_path, clip_start, sample_fps=_SAMPLE_FPS_ZONE)

    events: list[Any] = []
    frame_count = 0

    for frame in extractor:
        frame_count += 1
        detections = detector.detect(frame.image)
        tracks = tracker.update(detections, frame.image)

        _, transitions = zone_mapper.assign(tracks, frame.timestamp)
        dwell_acc.update(transitions, frame.timestamp)

        for t in transitions:
            if t.to_zone is not None:
                ev = emitter.zone_event("zone_entered", t.track_id, t.to_zone, t.timestamp)
                if ev:
                    events.append(ev)
            if t.from_zone is not None:
                ev = emitter.zone_event("zone_exited", t.track_id, t.from_zone, t.timestamp)
                if ev:
                    events.append(ev)

    tracker.reset()
    print(f"    {frame_count} frames -> {len(events)} zone events")
    return events


def _process_billing_camera(
    video_path: Path,
    layout_path: Path,
    camera_id: str,
    cam_config: dict,
    store_id: str,
    store_code: str,
    clip_start: datetime,
) -> list[Any]:
    """Run detection + zone + queue depth; emit zone events + queue_completed/abandoned."""
    zone_mapper = ZoneMapper(layout_path, camera_id)
    emitter = EventEmitter(store_id, store_code, camera_id, zone_mapper)
    dwell_acc = DwellAccumulator()
    staff = StaffClassifier(_STAFF_COLOR_HEX)
    detector = PersonDetector(confidence_threshold=_CONFIDENCE_THRESHOLD)
    tracker = ByteTracker()
    extractor = FrameExtractor(video_path, clip_start, sample_fps=_SAMPLE_FPS_BILLING)

    billing_zone = cam_config["zones"][0]
    queue_ctr = QueueDepthCounter(
        billing_zone["zone_id"],
        abandon_wait_seconds=billing_zone.get("abandon_wait_seconds", 60),
    )

    events: list[Any] = []
    frame_count = 0

    for frame in extractor:
        frame_count += 1
        detections = detector.detect(frame.image)
        tracks = tracker.update(detections, frame.image)

        for track in tracks:
            staff.classify(track, frame.image)

        zone_assignments, transitions = zone_mapper.assign(tracks, frame.timestamp)
        dwell_acc.update(transitions, frame.timestamp)

        for t in transitions:
            if t.to_zone is not None:
                ev = emitter.zone_event("zone_entered", t.track_id, t.to_zone, t.timestamp)
                if ev:
                    events.append(ev)
            if t.from_zone is not None:
                ev = emitter.zone_event("zone_exited", t.track_id, t.from_zone, t.timestamp)
                if ev:
                    events.append(ev)

        for track in tracks:
            zone_id = zone_assignments.get(track.track_id)
            is_s = staff.is_staff(track.track_id)
            _, exit_ev = queue_ctr.update(track.track_id, zone_id, is_s, frame.timestamp)
            if exit_ev:
                ev = emitter.queue_event(exit_ev, billing_zone["zone_id"])
                if ev:
                    events.append(ev)

    # flush remaining in-queue tracks as abandoned at video end
    for track_id in list(queue_ctr._in_queue.keys()):
        _, exit_ev = queue_ctr.update(track_id, None, False, frame.timestamp if frame_count else clip_start)
        if exit_ev:
            ev = emitter.queue_event(exit_ev, billing_zone["zone_id"])
            if ev:
                events.append(ev)

    tracker.reset()
    staff.reset()
    print(f"    {frame_count} frames -> {len(events)} billing/queue events")
    return events


def process_store(store_dir: Path, api_url: str, clip_date: date) -> None:
    layout_path = store_dir / "store_layout.json"
    if not layout_path.exists():
        print(f"[ERROR] store_layout.json not found in {store_dir}", file=sys.stderr)
        sys.exit(1)

    layout = json.loads(layout_path.read_text())
    store_id: str = layout["store_id"]
    store_code: str = layout["store_code"]
    cameras: dict = layout["cameras"]

    # Use 09:00 UTC on the given date as clip start for all cameras
    clip_start = datetime.combine(clip_date, time(9, 0, 0), tzinfo=timezone.utc)

    total_accepted = total_rejected = 0
    overall_ok = True

    for cam_id, cam_cfg in cameras.items():
        video_file = cam_cfg.get("video_file", "")
        video_path = store_dir / video_file
        role: str = cam_cfg["role"]

        print(f"\n[{cam_id}] {role} — {video_file}")

        if not video_path.exists():
            print(f"  [SKIP] {video_path} not found", file=sys.stderr)
            continue

        try:
            if role == "entry":
                events = _process_entry_camera(
                    video_path, layout_path, cam_id, store_id, store_code, clip_start
                )
            elif role == "zone":
                events = _process_zone_camera(
                    video_path, layout_path, cam_id, store_id, store_code, clip_start
                )
            elif role == "billing":
                events = _process_billing_camera(
                    video_path, layout_path, cam_id, cam_cfg, store_id, store_code, clip_start
                )
            else:
                print(f"  [SKIP] unknown role: {role}")
                continue

            if events:
                accepted, rejected = _post_batch(events, api_url)
                total_accepted += accepted
                total_rejected += rejected
                print(f"    posted -> accepted={accepted} rejected={rejected}")
            else:
                print(f"    no events to post")

        except Exception as exc:
            print(f"  [ERROR] {cam_id}: {exc}", file=sys.stderr)
            overall_ok = False

    print(f"\n{'='*50}")
    print(f"Store {store_id}: accepted={total_accepted} rejected={total_rejected}")

    if not overall_ok:
        sys.exit(1)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Process one store's CCTV clips")
    parser.add_argument("store_dir", type=Path, help="Path to store data directory")
    parser.add_argument("api_url", help="API base URL, e.g. http://localhost:8000")
    parser.add_argument(
        "--date",
        default=str(date.today()),
        help="Clip date YYYY-MM-DD (default: today)",
    )
    args = parser.parse_args()

    process_store(args.store_dir, args.api_url, date.fromisoformat(args.date))
