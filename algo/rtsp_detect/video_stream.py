"""RTSP/Video stream management utilities."""

from __future__ import annotations

import threading
import time
from typing import Optional, Tuple

import cv2
import numpy as np
from loguru import logger


class VideoStream:
    """Continuously read frames from an RTSP stream with reconnection support."""

    def __init__(
        self,
        source: str,
        reconnect_interval: float = 3.0,
        max_retries: Optional[int] = None,
        name: Optional[str] = None,
    ) -> None:
        self.source = source
        self.reconnect_interval = reconnect_interval
        self.max_retries = max_retries
        self.name = name or source

        self._capture: Optional[cv2.VideoCapture] = None
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._frame_lock = threading.Lock()
        self._latest_frame: Optional[np.ndarray] = None
        self._resolution: Tuple[int, int] = (0, 0)

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, name=f"VideoStream-{self.name}", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        self._thread = None
        self._release_capture()
        with self._frame_lock:
            self._latest_frame = None

    def _open_capture(self) -> bool:
        self._release_capture()
        logger.info("Opening video stream {}", self.name)
        cap = cv2.VideoCapture(self.source)
        if not cap.isOpened():
            logger.warning("Failed to open video stream {}", self.name)
            cap.release()
            return False
        self._capture = cap
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        if width and height:
            self._resolution = (width, height)
        return True

    def _release_capture(self) -> None:
        if self._capture is not None:
            try:
                self._capture.release()
            except Exception:  # pragma: no cover - defensive
                pass
            self._capture = None

    def _run(self) -> None:
        retries = 0
        while not self._stop_event.is_set():
            if self._capture is None or not self._capture.isOpened():
                if self.max_retries is not None and retries >= self.max_retries:
                    logger.error("Max retries reached for stream {}", self.name)
                    time.sleep(self.reconnect_interval)
                    continue
                if not self._open_capture():
                    retries += 1
                    time.sleep(self.reconnect_interval)
                    continue
                retries = 0

            if not self._capture:
                time.sleep(self.reconnect_interval)
                continue

            ok, frame = self._capture.read()
            if not ok:
                logger.warning("Frame read failed for stream {}, reconnecting", self.name)
                self._release_capture()
                time.sleep(self.reconnect_interval)
                continue

            with self._frame_lock:
                self._latest_frame = frame
                if not self._resolution[0] or not self._resolution[1]:
                    height, width = frame.shape[:2]
                    self._resolution = (width, height)

        self._release_capture()

    def get_latest_frame(self) -> Optional[np.ndarray]:
        with self._frame_lock:
            if self._latest_frame is None:
                return None
            return self._latest_frame.copy()

    def get_resolution(self) -> Tuple[int, int]:
        return self._resolution

    @staticmethod
    def probe(source: str, timeout: float = 5.0) -> bool:
        cap = cv2.VideoCapture(source)
        start_time = time.time()
        success = False
        while time.time() - start_time < timeout:
            if not cap.isOpened():
                time.sleep(0.2)
                continue
            ok, _ = cap.read()
            if ok:
                success = True
                break
            time.sleep(0.2)
        cap.release()
        return success
