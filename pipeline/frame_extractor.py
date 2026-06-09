"""Decode video clips into timestamped frames. T-03."""

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import cv2
import numpy as np


@dataclass
class Frame:
    image: np.ndarray
    timestamp: datetime
    frame_index: int


class FrameExtractor:
    """Streams frames from a video file at a configurable sample rate.

    Timestamps are derived from clip_start_utc + frame_index / source_fps.
    Does not load the entire clip into memory.
    """

    def __init__(
        self,
        video_path: Path,
        clip_start_utc: datetime,
        sample_fps: float = 5.0,
    ) -> None:
        self._path = Path(video_path)
        self._clip_start_utc = clip_start_utc
        self._sample_fps = sample_fps
        self._cap = None  # cv2.VideoCapture, opened lazily or via context manager

    def _open(self) -> None:
        cap = cv2.VideoCapture(str(self._path))
        if not cap.isOpened():
            raise FileNotFoundError(f"Cannot open video: {self._path}")
        self._cap = cap

    def _close(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None

    def __iter__(self) -> Iterator[Frame]:
        managed = self._cap is not None
        if not managed:
            self._open()
        try:
            cap = self._cap
            source_fps: float = cap.get(cv2.CAP_PROP_FPS) or 25.0
            # frame_interval: how many source frames to advance per sampled frame
            frame_interval = max(1, round(source_fps / self._sample_fps))
            frame_index = 0

            while True:
                ok, image = cap.read()
                if not ok:
                    break
                if frame_index % frame_interval == 0:
                    ts = self._clip_start_utc + timedelta(seconds=frame_index / source_fps)
                    yield Frame(image=image, timestamp=ts, frame_index=frame_index)
                frame_index += 1
        finally:
            # Only release if we opened it here (not via context manager)
            if not managed:
                self._close()

    def __enter__(self) -> "FrameExtractor":
        self._open()
        return self

    def __exit__(self, *_) -> None:
        self._close()


# ── Unit tests ─────────────────────────────────────────────────────────────────

def _make_mock_cap(frames: list, fps: float = 15.0) -> MagicMock:
    cap = MagicMock()
    cap.isOpened.return_value = True
    cap.get.return_value = fps
    reads = [(True, f) for f in frames] + [(False, None)]
    cap.read.side_effect = reads
    return cap


def test_first_frame_timestamp_equals_clip_start():
    from datetime import timezone
    start = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    blank = np.zeros((4, 4, 3), dtype=np.uint8)
    mock_cap = _make_mock_cap([blank], fps=15.0)

    with patch("pipeline.frame_extractor.cv2.VideoCapture", return_value=mock_cap):
        frames = list(FrameExtractor(Path("fake.mp4"), start, sample_fps=5.0))

    assert len(frames) == 1
    assert frames[0].timestamp == start
    assert frames[0].frame_index == 0


def test_timestamp_accuracy_at_frame_n():
    from datetime import timezone
    start = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    blank = np.zeros((4, 4, 3), dtype=np.uint8)
    # sample_fps == source_fps → every frame yielded
    mock_cap = _make_mock_cap([blank] * 6, fps=15.0)

    with patch("pipeline.frame_extractor.cv2.VideoCapture", return_value=mock_cap):
        frames = list(FrameExtractor(Path("fake.mp4"), start, sample_fps=15.0))

    assert len(frames) == 6
    # frame index 5: timestamp should be start + 5/15 s
    expected_offset = timedelta(seconds=5 / 15.0)
    delta = abs((frames[5].timestamp - start) - expected_offset)
    assert delta.total_seconds() < 0.001


def test_sampling_yields_fewer_frames():
    from datetime import timezone
    start = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    blank = np.zeros((4, 4, 3), dtype=np.uint8)
    # 15 fps source, 5 fps sample → interval=3 → 15 frames → 5 yielded
    mock_cap = _make_mock_cap([blank] * 15, fps=15.0)

    with patch("pipeline.frame_extractor.cv2.VideoCapture", return_value=mock_cap):
        frames = list(FrameExtractor(Path("fake.mp4"), start, sample_fps=5.0))

    assert len(frames) == 5
    assert all(f.frame_index % 3 == 0 for f in frames)


def test_context_manager_releases_cap():
    from datetime import timezone
    start = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    mock_cap = _make_mock_cap([], fps=15.0)

    with patch("pipeline.frame_extractor.cv2.VideoCapture", return_value=mock_cap):
        with FrameExtractor(Path("fake.mp4"), start) as extractor:
            list(extractor)

    mock_cap.release.assert_called_once()


def test_empty_video_no_exception():
    from datetime import timezone
    start = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    mock_cap = _make_mock_cap([], fps=15.0)

    with patch("pipeline.frame_extractor.cv2.VideoCapture", return_value=mock_cap):
        frames = list(FrameExtractor(Path("fake.mp4"), start))

    assert frames == []


def test_sample_fps_above_source_yields_every_frame():
    from datetime import timezone
    start = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    blank = np.zeros((4, 4, 3), dtype=np.uint8)
    # sample_fps > source_fps → interval=1 → all 4 frames yielded
    mock_cap = _make_mock_cap([blank] * 4, fps=10.0)

    with patch("pipeline.frame_extractor.cv2.VideoCapture", return_value=mock_cap):
        frames = list(FrameExtractor(Path("fake.mp4"), start, sample_fps=30.0))

    assert len(frames) == 4
