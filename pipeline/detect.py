"""YOLOv8 person detector. T-04."""

from dataclasses import dataclass, field
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np

PERSON_CLASS_ID = 0


@dataclass
class Detection:
    x1: float
    y1: float
    x2: float
    y2: float
    confidence: float
    class_name: str = field(default="person")

    @property
    def bbox(self) -> list[float]:
        return [self.x1, self.y1, self.x2, self.y2]

    def to_dict(self) -> dict:
        return {
            "bbox": self.bbox,
            "confidence": round(self.confidence, 6),
            "class_name": self.class_name,
        }


class PersonDetector:
    """Wraps YOLOv8 for single-class (person) detection.

    Falls back to OpenCV HOG when ultralytics / PyTorch is unavailable.
    Low-confidence detections are passed through, not suppressed.
    """

    # Person-sized blob bounds for a 1920x1080 store CCTV at typical 3-6 m distance.
    # ~80x100 px minimum (person far away), ~300x400 px maximum (person close).
    _MIN_AREA = 6_000
    _MAX_AREA = 100_000

    def __init__(
        self,
        model_path: str = "yolov8n.pt",
        confidence_threshold: float = 0.3,
        device: str = "cpu",
    ) -> None:
        self._threshold = confidence_threshold
        try:
            from ultralytics import YOLO
            self._model = YOLO(model_path)
            self._model.to(device)
            self._backend = "yolo"
        except Exception:
            try:
                import cv2
                self._mog = cv2.createBackgroundSubtractorMOG2(
                    history=120, varThreshold=50, detectShadows=False
                )
                self._kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
                self._backend = "mog2"
                print("[PersonDetector] ultralytics unavailable -- using MOG2 fallback")
            except ImportError:
                self._backend = "none"
                print("[PersonDetector] no detection backend available (install ultralytics or opencv-python)")

    def detect(self, frame: np.ndarray) -> list[Detection]:
        """Return all person detections above threshold for a single frame."""
        if self._backend == "yolo":
            return self._detect_yolo(frame)
        if self._backend == "mog2":
            return self._detect_mog2(frame)
        return []  # "none" backend

    def _detect_yolo(self, frame: np.ndarray) -> list[Detection]:
        results = self._model(frame, conf=self._threshold, classes=[PERSON_CLASS_ID], verbose=False)
        detections: list[Detection] = []
        for result in results:
            boxes = result.boxes
            if boxes is None:
                continue
            for box in boxes:
                if int(box.cls[0].item()) != PERSON_CLASS_ID:
                    continue
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                conf = float(box.conf[0].item())
                detections.append(Detection(x1=x1, y1=y1, x2=x2, y2=y2, confidence=conf))
        return detections

    def _detect_mog2(self, frame: np.ndarray) -> list[Detection]:
        import cv2
        mask = self._mog.apply(frame)
        # Remove noise and fill small holes
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, self._kernel)
        mask = cv2.dilate(mask, self._kernel, iterations=2)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        detections: list[Detection] = []
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < self._MIN_AREA or area > self._MAX_AREA:
                continue
            x, y, w, h = cv2.boundingRect(cnt)
            # Reject very wide flat blobs (background artefacts) and very thin tall blobs
            if w > h * 2.0 or h < 60:
                continue
            # Confidence proxy: larger blob = more confident it's a person
            conf = min(0.95, 0.4 + (area - self._MIN_AREA) / 30_000)
            if conf < self._threshold:
                continue
            detections.append(Detection(x1=float(x), y1=float(y), x2=float(x + w), y2=float(y + h), confidence=conf))
        return detections


# ── Unit tests ─────────────────────────────────────────────────────────────────

def _make_mock_box(x1, y1, x2, y2, conf, cls=0):
    box = MagicMock()
    xyxy = MagicMock()
    xyxy.tolist.return_value = [x1, y1, x2, y2]
    box.xyxy = [xyxy]
    conf_t = MagicMock()
    conf_t.item.return_value = float(conf)
    box.conf = [conf_t]
    cls_t = MagicMock()
    cls_t.item.return_value = float(cls)
    box.cls = [cls_t]
    return box


def _make_mock_model(boxes):
    result = MagicMock()
    result.boxes = boxes
    model = MagicMock()
    model.return_value = [result]
    return model


def test_returns_detection_dataclass():
    box = _make_mock_box(10, 20, 100, 200, 0.9)
    mock_model = _make_mock_model([box])

    detector = PersonDetector.__new__(PersonDetector)
    detector._threshold = 0.3
    detector._model = mock_model

    detections = detector.detect(np.zeros((480, 640, 3), dtype=np.uint8))
    assert len(detections) == 1
    d = detections[0]
    assert d.class_name == "person"
    assert d.bbox == [10, 20, 100, 200]
    assert abs(d.confidence - 0.9) < 1e-4


def test_to_dict_shape():
    box = _make_mock_box(0, 0, 50, 50, 0.75)
    mock_model = _make_mock_model([box])

    detector = PersonDetector.__new__(PersonDetector)
    detector._threshold = 0.3
    detector._model = mock_model

    result = detector.detect(np.zeros((480, 640, 3), dtype=np.uint8))
    d = result[0].to_dict()
    assert set(d.keys()) == {"bbox", "confidence", "class_name"}
    assert len(d["bbox"]) == 4
    assert d["class_name"] == "person"


def test_non_person_class_excluded():
    # cls=1 (bicycle) — should be filtered out
    box = _make_mock_box(10, 20, 100, 200, 0.95, cls=1)
    mock_model = _make_mock_model([box])

    detector = PersonDetector.__new__(PersonDetector)
    detector._threshold = 0.3
    detector._model = mock_model

    detections = detector.detect(np.zeros((480, 640, 3), dtype=np.uint8))
    assert detections == []


def test_empty_frame_returns_empty_list():
    mock_model = _make_mock_model([])

    detector = PersonDetector.__new__(PersonDetector)
    detector._threshold = 0.3
    detector._model = mock_model

    detections = detector.detect(np.zeros((1080, 1920, 3), dtype=np.uint8))
    assert detections == []


def test_low_confidence_detection_included():
    # conf=0.31 is above default threshold 0.3 — must be included
    box = _make_mock_box(5, 5, 50, 50, 0.31)
    mock_model = _make_mock_model([box])

    detector = PersonDetector.__new__(PersonDetector)
    detector._threshold = 0.3
    detector._model = mock_model

    detections = detector.detect(np.zeros((480, 640, 3), dtype=np.uint8))
    assert len(detections) == 1
    assert detections[0].confidence < 0.5


def test_multiple_persons_detected():
    boxes = [_make_mock_box(i * 10, 0, i * 10 + 50, 100, 0.8) for i in range(4)]
    mock_model = _make_mock_model(boxes)

    detector = PersonDetector.__new__(PersonDetector)
    detector._threshold = 0.3
    detector._model = mock_model

    detections = detector.detect(np.zeros((480, 640, 3), dtype=np.uint8))
    assert len(detections) == 4
    assert all(d.class_name == "person" for d in detections)
