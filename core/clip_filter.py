from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np

from core.config import ClipFilterConfig

logger = logging.getLogger(__name__)


@dataclass
class ClipVerdict:
    accepted: bool
    scores: dict[str, float]
    reason: str


class ClipFalsePositiveFilter:
    def __init__(self, config: ClipFilterConfig) -> None:
        self.config = config
        self._model = None
        self._processor = None
        self._torch = None
        self._available = False

        if not config.enabled:
            return
        try:
            import torch
            from transformers import CLIPModel, CLIPProcessor

            self._processor = CLIPProcessor.from_pretrained(config.model_name)
            self._model = CLIPModel.from_pretrained(config.model_name)
            self._model.eval()
            self._torch = torch
            self._available = True
            logger.info("CLIP filter loaded: %s", config.model_name)
        except ImportError:
            logger.warning("CLIP disabled — pip install torch transformers")
        except Exception as exc:
            logger.warning("CLIP load failed: %s", exc)

    @property
    def enabled(self) -> bool:
        return self.config.enabled and self._available

    def evaluate(self, frame: np.ndarray) -> ClipVerdict:
        if not self.enabled:
            return ClipVerdict(True, {}, "clip_disabled")

        import cv2

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        prompts = self.config.prompts
        texts = [prompts["accident"], prompts["normal"], prompts["stopped"]]
        keys = ["accident", "normal", "stopped"]
        inputs = self._processor(text=texts, images=rgb, return_tensors="pt", padding=True)
        with self._torch.no_grad():
            logits = self._model(**inputs).logits_per_image[0]
            probs = logits.softmax(dim=0).tolist()
        scores = {keys[i]: float(probs[i]) for i in range(3)}
        normal_score = max(scores["normal"], scores["stopped"])
        if normal_score > scores["accident"] + self.config.reject_margin:
            return ClipVerdict(False, scores, "normal_traffic_dominates")
        return ClipVerdict(True, scores, "accident_or_ambiguous")
