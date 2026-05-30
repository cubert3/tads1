from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

import cv2
import numpy as np

if TYPE_CHECKING:
    from core.tracker import TrackedObject

logger = logging.getLogger(__name__)

# Indian-style plates + generic alphanumeric clusters
PLATE_PATTERNS = [
    re.compile(r"[A-Z]{2}\s?\d{1,2}\s?[A-Z]{1,3}\s?\d{4}", re.I),
    re.compile(r"[A-Z0-9]{6,10}", re.I),
]


def _preprocess_crop(crop: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    gray = cv2.bilateralFilter(gray, 9, 75, 75)
    _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return thresh


def _ocr_text(image: np.ndarray) -> str:
    try:
        import pytesseract
    except ImportError:
        return ""
    try:
        return pytesseract.image_to_string(image, config="--psm 7 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789")
    except Exception as exc:
        logger.debug("OCR failed: %s", exc)
        return ""


def _normalize_plate(text: str) -> str | None:
    cleaned = re.sub(r"[^A-Z0-9]", "", text.upper())
    if len(cleaned) < 6:
        return None
    for pattern in PLATE_PATTERNS:
        m = pattern.search(text.upper().replace(" ", ""))
        if m:
            return m.group(0).replace(" ", "")
    if 6 <= len(cleaned) <= 12:
        return cleaned
    return None


def extract_plates_from_tracks(
    frame: np.ndarray,
    tracked: list[TrackedObject],
    track_ids: tuple[int, int] | None,
    enabled: bool = True,
) -> list[str]:
    """Best-effort plate read on involved vehicles. Requires optional pytesseract + Tesseract OCR."""
    if not enabled or not track_ids:
        return []

    plates: list[str] = []
    wanted = set(track_ids)

    for obj in tracked:
        if obj.track_id not in wanted:
            continue
        x1, y1, x2, y2 = (int(v) for v in obj.bbox)
        h, w = frame.shape[:2]
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(w, x2), min(h, y2)
        if x2 <= x1 or y2 <= y1:
            continue
        crop = frame[y1:y2, x1:x2]
        if crop.size == 0:
            continue
        # Focus on lower third of vehicle bbox (typical plate region)
        ph = crop.shape[0]
        plate_region = crop[int(ph * 0.55) : ph, :]
        if plate_region.size == 0:
            plate_region = crop
        processed = _preprocess_crop(plate_region)
        text = _ocr_text(processed)
        plate = _normalize_plate(text)
        if plate and plate not in plates:
            plates.append(plate)

    return plates
