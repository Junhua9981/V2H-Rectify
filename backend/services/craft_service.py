"""
CRAFT batch inference service.

Retains the v2 Queue + Future design (which was good) but:
- **No global singleton** — lifecycle is managed by FastAPI's ``lifespan``.
- Detection results are returned as immutable ``DetectionResult`` dataclasses,
  so concurrent requests never overwrite each other's heatmaps.
- Device is injected from ``config.Settings``.
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from concurrent.futures import Future
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from config.settings import CRAFTSettings
from core.craft_detector import CRAFTDetector, DetectionResult, resize_heatmap

logger = logging.getLogger(__name__)


@dataclass
class _Request:
    image: np.ndarray
    params: Dict[str, Any]
    future: Future
    request_id: int


class CRAFTService:
    """Batched CRAFT inference service (thread-safe, no global state)."""

    def __init__(
        self,
        device: str = "cuda:7",
        craft_settings: Optional[CRAFTSettings] = None,
    ) -> None:
        cfg = craft_settings or CRAFTSettings()
        self._detector = CRAFTDetector(
            languages=cfg.languages,
            gpu=("cuda" in device),
            device=device,
        )
        self._max_batch = cfg.batch_size
        self._batch_timeout = cfg.batch_timeout
        self._default_params = {
            "canvas_size": cfg.canvas_size,
            "mag_ratio": cfg.mag_ratio,
            "text_threshold": cfg.text_threshold,
            "link_threshold": cfg.link_threshold,
            "low_text": cfg.low_text,
        }

        self._queue: queue.Queue[_Request] = queue.Queue(maxsize=200)
        self._worker: Optional[threading.Thread] = None
        self._running = False
        self._counter = 0
        self._batch_counter = 0
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._worker = threading.Thread(target=self._loop, daemon=True)
        self._worker.start()
        logger.info(
            "CRAFTService started (batch=%d, timeout=%.2fs)",
            self._max_batch,
            self._batch_timeout,
        )

    def stop(self, timeout: float = 5.0) -> None:
        if not self._running:
            return
        self._running = False
        if self._worker:
            self._worker.join(timeout=timeout)
        logger.info(
            "CRAFTService stopped (%d batches, %d requests)",
            self._batch_counter,
            self._counter,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def detect(self, image: np.ndarray, **kwargs: Any) -> DetectionResult:
        """Submit a detection request and block until the result is ready."""
        return self.detect_async(image, **kwargs).result()

    def detect_async(self, image: np.ndarray, **kwargs: Any) -> Future:
        """Submit a detection request and return a ``Future``."""
        if not self._running:
            raise RuntimeError("CRAFTService not started.  Call start() first.")

        params = {**self._default_params, **kwargs}
        req = _Request(
            image=image,
            params=params,
            future=Future(),
            request_id=self._next_id(),
        )
        self._queue.put_nowait(req)
        return req.future

    def detect_with_heatmap(
        self, image: np.ndarray, **kwargs: Any
    ) -> Tuple[DetectionResult, np.ndarray]:
        """Detect *and* return the heatmap resized to ``image.shape[:2]``.

        This is the primary entry point for the OCR pipeline — it avoids
        downstream modules having to redo the resize themselves.
        """
        result = self.detect(image, **kwargs)
        heatmap = resize_heatmap(
            result.score_text, result.ratio_w, result.ratio_h, image.shape[:2]
        )
        return result, heatmap

    @property
    def is_ready(self) -> bool:
        """True if the service is running and ready to accept requests."""
        return self._running

    def get_stats(self) -> dict:
        return {
            "total_requests": self._counter,
            "total_batches": self._batch_counter,
            "avg_batch_size": self._counter / max(self._batch_counter, 1),
            "queue_size": self._queue.qsize(),
            "running": self._running,
        }

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _next_id(self) -> int:
        with self._lock:
            self._counter += 1
            return self._counter

    def _loop(self) -> None:
        while self._running:
            batch = self._collect()
            if batch:
                self._process(batch)

    def _collect(self) -> List[_Request]:
        batch: list[_Request] = []
        deadline = time.time() + self._batch_timeout
        try:
            batch.append(self._queue.get(timeout=self._batch_timeout))
        except queue.Empty:
            return []

        while len(batch) < self._max_batch:
            remaining = deadline - time.time()
            if remaining <= 0:
                break
            try:
                batch.append(self._queue.get(timeout=remaining))
            except queue.Empty:
                break
        return batch

    def _process(self, batch: List[_Request]) -> None:
        self._batch_counter += 1
        try:
            for req in batch:
                try:
                    result = self._detector.detect(req.image, **req.params)
                    req.future.set_result(result)
                except Exception as exc:
                    req.future.set_exception(exc)
        except Exception as exc:
            for req in batch:
                if not req.future.done():
                    req.future.set_exception(exc)
