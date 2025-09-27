"""Detection pipeline combining video stream, group analysis, and LLM."""

from __future__ import annotations

import threading
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence, Callable

import numpy as np
from loguru import logger

from algo.llm.dangerous_driving_detector import DangerousDrivingAnalyzer
from algo.rtsp_detect.group_analyzer import GroupAnalyzer
from algo.rtsp_detect.video_stream import VideoStream
from algo.rtsp_detect.yolo_detector import YoloDetector
from utils.image import encode_frame_to_base64


DetectionCallback = Callable[[Dict], None]


class DetectionPipeline:
    """Run YOLO inference on frames from a video stream and emit enriched results."""

    def __init__(
        self,
        camera_id: int,
        stream: VideoStream,
        detector: YoloDetector,
        frame_interval: float,
        callback: DetectionCallback,
        group_analyzer: Optional[GroupAnalyzer] = None,
        dangerous_analyzer: Optional[DangerousDrivingAnalyzer] = None,
    ) -> None:
        self.camera_id = camera_id
        self.stream = stream
        self.detector = detector
        self.frame_interval = frame_interval
        self.callback = callback
        self.group_analyzer = group_analyzer
        self.dangerous_analyzer = dangerous_analyzer

        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self.stream.start()
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, name=f"DetectionPipeline-{self.camera_id}", daemon=True)
        self._thread.start()
        logger.info("Detection pipeline started for camera %s", self.camera_id)

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        self._thread = None
        self.stream.stop()
        logger.info("Detection pipeline stopped for camera %s", self.camera_id)

    def _run(self) -> None:
        while not self._stop_event.is_set():
            frame = self.stream.get_latest_frame()
            if frame is None:
                time.sleep(0.1)
                continue

            detection_start = time.time()
            detection = self.detector.detect(frame)
            detection_time = detection.get("latency", time.time() - detection_start)
            detected_objects: Sequence[Dict] = detection.get("objects", [])

            try:
                data_uri, _ = encode_frame_to_base64(frame)
            except ValueError as exc:
                logger.warning("Failed to encode frame for camera %s: %s", self.camera_id, exc)
                time.sleep(self.frame_interval)
                continue

            groups, group_images = self._analyze_groups(frame, detected_objects)
            llm_result = self._analyze_dangerous_driving(data_uri, detected_objects, groups)

            height, width = frame.shape[:2]
            payload = {
                "type": "detection_result",
                "data": {
                    "cameraId": self.camera_id,
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                    "frame": data_uri,
                    "imageWidth": width,
                    "imageHeight": height,
                    "detectedObjects": detected_objects,
                    "trafficGroups": groups,
                    "groupImages": group_images,
                    "dangerousDrivingResults": llm_result.get("results", []),
                    "hasDangerousDriving": llm_result.get("hasDangerousDriving", False),
                    "maxRiskLevel": llm_result.get("maxRiskLevel", "none"),
                    "processTime": detection_time,
                    "llmLatency": llm_result.get("latency"),
                    "llmModel": llm_result.get("model"),
                    "llmRawText": llm_result.get("rawText"),
                    "modelType": self.detector.model_type,
                    "supportedClasses": self.detector.supported_classes,
                    "trackingEnabled": False,
                    "serverDrawEnabled": False,
                },
            }
            self.callback(payload)

            elapsed = time.time() - detection_start
            wait_time = max(self.frame_interval - elapsed, 0.05)
            time.sleep(wait_time)

    def _analyze_groups(
        self,
        frame: np.ndarray,
        detections: Sequence[Dict],
    ) -> tuple[list[Dict], list[str]]:
        if not self.group_analyzer:
            return [], []
        try:
            groups, images = self.group_analyzer.analyze(frame, detections)
            return groups, images
        except Exception as exc:  # pragma: no cover - robustness
            logger.error("Group analysis failed for camera %s: %s", self.camera_id, exc)
            return [], []

    def _analyze_dangerous_driving(
        self,
        image_data_url: str,
        detections: Sequence[Dict],
        groups: Sequence[Dict],
    ) -> Dict[str, Any]:
        if not self.dangerous_analyzer:
            return {
                "hasDangerousDriving": False,
                "maxRiskLevel": "none",
                "results": [],
                "latency": 0.0,
                "model": None,
            }
        try:
            if not self.dangerous_analyzer.should_analyze(detections, groups):
                return {
                    "hasDangerousDriving": False,
                    "maxRiskLevel": "none",
                    "results": [],
                    "latency": 0.0,
                    "model": self.dangerous_analyzer.config.model,
                }
            return self.dangerous_analyzer.analyze(image_data_url, detections, groups)
        except Exception as exc:  # pragma: no cover - robustness
            logger.error("Dangerous driving analysis failed for camera %s: %s", self.camera_id, exc)
            return {
                "hasDangerousDriving": False,
                "maxRiskLevel": "none",
                "results": [],
                "latency": 0.0,
                "model": self.dangerous_analyzer.config.model,
                "rawText": str(exc),
            }
