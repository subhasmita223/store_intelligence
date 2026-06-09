"""Staff classifier — flag tracks wearing the staff uniform. T-08."""

import numpy as np

from pipeline.tracker import Track

try:
    import cv2
    _CV2_AVAILABLE = True
except ImportError:
    _CV2_AVAILABLE = False


def _hex_to_target_hue(hex_str: str) -> float:
    """Convert 'RRGGBB' or '#RRGGBB' to OpenCV hue [0, 180]."""
    hex_str = hex_str.lstrip("#")
    r = int(hex_str[0:2], 16) / 255.0
    g = int(hex_str[2:4], 16) / 255.0
    b = int(hex_str[4:6], 16) / 255.0
    max_c, min_c = max(r, g, b), min(r, g, b)
    delta = max_c - min_c
    if delta < 1e-6:
        return 0.0
    if max_c == r:
        h = (g - b) / delta % 6
    elif max_c == g:
        h = (b - r) / delta + 2
    else:
        h = (r - g) / delta + 4
    hue_360 = h * 60.0
    if hue_360 < 0:
        hue_360 += 360.0
    return hue_360 / 2.0  # OpenCV uses [0, 180]


class StaffClassifier:
    """Classifies each track as staff or customer using upper-body color analysis.

    Classification is sticky: once a track is classified as staff it remains staff.
    Configurable via staff_color_hex (hex RGB) and tolerance (hue degrees, 0-180 scale).
    Falls back to never-staff when OpenCV is unavailable.
    """

    def __init__(self, staff_color_hex: str = "1A6B3C", tolerance: int = 15) -> None:
        self._target_hue = _hex_to_target_hue(staff_color_hex)
        self._tol = tolerance
        self._staff_ids: set[int] = set()
        self._checked: set[int] = set()  # tracks already evaluated

    def classify(self, track: Track, frame: np.ndarray) -> bool:
        """Return True if this track is staff. Sticky once True."""
        if track.track_id in self._staff_ids:
            return True
        if track.track_id in self._checked:
            return False
        self._checked.add(track.track_id)

        if not _CV2_AVAILABLE or frame is None or frame.size == 0:
            return False

        h_img, w_img = frame.shape[:2]
        x1 = max(0, int(track.x1))
        y1 = max(0, int(track.y1))
        x2 = min(w_img, int(track.x2))
        # Use top 50% of bounding box as upper-body crop
        mid_y = min(h_img, int(track.y1 + (track.y2 - track.y1) * 0.5))

        if x2 <= x1 or mid_y <= y1:
            return False

        crop = frame[y1:mid_y, x1:x2]
        if crop.size == 0:
            return False

        hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
        # Only use well-saturated, non-dark pixels to ignore shadows/skin
        sat_mask = (hsv[:, :, 1] > 50) & (hsv[:, :, 2] > 50)
        if sat_mask.sum() < 20:
            return False

        hues = hsv[:, :, 0][sat_mask].astype(float)
        median_hue = float(np.median(hues))

        # Circular hue distance on [0,180] scale
        diff = abs(median_hue - self._target_hue)
        hue_dist = min(diff, 180.0 - diff)

        is_staff = hue_dist <= self._tol
        if is_staff:
            self._staff_ids.add(track.track_id)
        return is_staff

    def is_staff(self, track_id: int) -> bool:
        return track_id in self._staff_ids

    def reset(self) -> None:
        self._staff_ids.clear()
        self._checked.clear()
