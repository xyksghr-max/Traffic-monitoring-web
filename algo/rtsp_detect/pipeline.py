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
from algo.rtsp_detect.frame_renderer import render_frame
from algo.rtsp_detect.risk_alert_manager import RiskAlertManager
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
        self.risk_manager = RiskAlertManager()

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

            # Preserve original frame for LLM analysis and group cropping
            raw_frame = frame.copy()

            groups, group_images = self._analyze_groups(raw_frame, detected_objects)

            try:
                raw_data_uri, _ = encode_frame_to_base64(raw_frame)
            except ValueError as exc:
                logger.warning("Failed to encode raw frame for camera %s: %s", self.camera_id, exc)
                time.sleep(self.frame_interval)
                continue

            llm_group_images: list[Dict[str, Any]] = []
            for image in group_images:
                base64_part = image.get("imageBase64")
                if not base64_part:
                    continue
                llm_group_images.append(
                    {
                        "groupIndex": image.get("groupIndex"),
                        "objectCount": image.get("objectCount"),
                        "classes": image.get("classes"),
                        "dataUri": f"data:image/jpeg;base64,{base64_part}",
                    }
                )

            logger.debug(
                "Camera {}: prepared {} group crops for LLM analysis",
                self.camera_id,
                len(llm_group_images),
            )
            llm_result = self._analyze_dangerous_driving(llm_group_images, detected_objects, groups)

            # Normalize traffic group fields to include requested aliases while preserving originals
            normalized_groups: list[Dict[str, Any]] = []
            for g in groups:
                g2 = dict(g)
                # Alias keys expected by frontend schema
                if "objectCount" in g2 and "memberCount" not in g2:
                    g2["memberCount"] = g2.get("objectCount")
                if "averageConfidence" in g2 and "avgConfidence" not in g2:
                    g2["avgConfidence"] = g2.get("averageConfidence")
                if "bbox" in g2 and "groupBbox" not in g2:
                    g2["groupBbox"] = g2.get("bbox")
                normalized_groups.append(g2)

            raw_results = llm_result.get("results", []) or []
            now_ts = time.time()
            alerts = self.risk_manager.update(now_ts, raw_results)
            self._apply_alerts_to_groups(normalized_groups, group_images, alerts)

            rendered_frame = render_frame(frame, detected_objects, normalized_groups)

            try:
                rendered_data_uri, _ = encode_frame_to_base64(rendered_frame)
            except ValueError as exc:
                logger.warning("Failed to encode rendered frame for camera %s: %s", self.camera_id, exc)
                time.sleep(self.frame_interval)
                continue

            dangerous_results = alerts

            # Normalize traffic group fields to include requested aliases while preserving originals
            normalized_groups: list[Dict[str, Any]] = []
            for g in groups:
                g2 = dict(g)
                # Alias keys expected by frontend schema
                if "objectCount" in g2 and "memberCount" not in g2:
                    g2["memberCount"] = g2.get("objectCount")
                if "averageConfidence" in g2 and "avgConfidence" not in g2:
                    g2["avgConfidence"] = g2.get("averageConfidence")
                if "bbox" in g2 and "groupBbox" not in g2:
                    g2["groupBbox"] = g2.get("bbox")
                normalized_groups.append(g2)

            # Add incremental groupIndex to each dangerous driving result item (1,2,3,...)
            raw_results = llm_result.get("results", []) or []
            dangerous_results: list[Dict[str, Any]] = []
            for idx, item in enumerate(raw_results, start=1):
                # Keep original fields and add required ones
                out = dict(item)
                out["groupIndex"] = idx
                dangerous_results.append(out)

            height, width = frame.shape[:2]
            payload = {
                "type": "detection_result",
                "data": {
                    "cameraId": self.camera_id,
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                    "frame": rendered_data_uri,
                    "rawFrame": raw_data_uri,
                    "imageWidth": width,
                    "imageHeight": height,
                    "detectedObjects": detected_objects,
                    "trafficGroups": normalized_groups,
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
                    "serverDrawEnabled": True,
                    "renderedBy": "server",
                },
            }
            self.callback(payload)

            elapsed = time.time() - detection_start
            wait_time = max(self.frame_interval - elapsed, 0.05)
            time.sleep(wait_time)

    def _apply_alerts_to_groups(
        self,
        groups: list[Dict[str, Any]],
        group_images: list[Dict[str, Any]],
        alerts: Sequence[Dict[str, Any]],
    ) -> None:
        level_map = {"high": "blue", "medium": "orange", "low": "yellow", "none": "gray"}
        alert_index: Dict[int, Dict[str, Any]] = {}
        for alert in alerts:
            idx = alert.get("groupIndex")
            try:
                idx_int = int(idx)
            except (TypeError, ValueError):
                continue
            alert_index[idx_int] = alert

        for group in groups:
            raw_idx = group.get("groupIndex")
            try:
                idx = int(raw_idx or 0)
            except (TypeError, ValueError):
                idx = 0
            alert = alert_index.get(idx)
            if alert:
                risk_level = str(alert.get("riskLevel", "none")).lower()
                group["riskLevelRaw"] = risk_level
                group["riskLevel"] = level_map.get(risk_level, "none")
                group["riskTypes"] = alert.get("riskTypes", [])
                group["dangerObjectCount"] = alert.get("dangerObjectCount")
                group["triggerObjectIds"] = alert.get("triggerObjectIds", [])
                group["alertDescription"] = alert.get("description")
                group["alertConfidence"] = alert.get("confidence")
            else:
                group.setdefault("riskLevel", "gray")
                group.setdefault("riskLevelRaw", "none")

        for image in group_images:
            raw_idx = image.get("groupIndex")
            try:
                idx = int(raw_idx or 0)
            except (TypeError, ValueError):
                idx = 0
            alert = alert_index.get(idx)
            if alert:
                risk_level = str(alert.get("riskLevel", "none")).lower()
                image["riskLevelRaw"] = risk_level
                image["riskLevel"] = level_map.get(risk_level, "none")
                image["riskTypes"] = alert.get("riskTypes", [])
            else:
                image.setdefault("riskLevel", "gray")
                image.setdefault("riskLevelRaw", "none")

    def _analyze_groups(
        self,
        frame: np.ndarray,
        detections: Sequence[Dict],
    ) -> tuple[list[Dict], list[Dict]]:
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
        group_image_data: Sequence[Dict[str, Any]],
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
            if not self.dangerous_analyzer.should_analyze(detections, groups, group_image_data):
                return {
                    "hasDangerousDriving": False,
                    "maxRiskLevel": "none",
                    "results": [],
                    "latency": 0.0,
                    "model": self.dangerous_analyzer.config.model,
                }
            return self.dangerous_analyzer.analyze(group_image_data, detections, groups)
        except Exception as exc:  # pragma: no cover - robustness
            logger.exception("Dangerous driving analysis failed for camera {}", self.camera_id)
            return {
                "hasDangerousDriving": False,
                "maxRiskLevel": "none",
                "results": [],
                "latency": 0.0,
                "model": self.dangerous_analyzer.config.model,
                "rawText": str(exc),
            }
