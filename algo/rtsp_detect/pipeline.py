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

# Prometheus metrics
from algo.monitoring.metrics import (
    record_detection,
    detected_objects_total,
    record_kafka_send,
    active_cameras,
)

# Kafka integration (optional)
try:
    from algo.kafka.detection_producer import DetectionResultProducer
    KAFKA_AVAILABLE = True
except ImportError:
    KAFKA_AVAILABLE = False
    logger.warning("Kafka module not available, streaming mode disabled")


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
        kafka_producer: Optional['DetectionResultProducer'] = None,
        enable_kafka: bool = False,
    ) -> None:
        self.camera_id = camera_id
        self.stream = stream
        self.detector = detector
        self.frame_interval = frame_interval
        self.callback = callback
        self.group_analyzer = group_analyzer
        self.dangerous_analyzer = dangerous_analyzer
        self.risk_manager = RiskAlertManager()
        
        # Kafka integration (optional)
        self.kafka_producer = kafka_producer
        self.enable_kafka = enable_kafka and KAFKA_AVAILABLE
        if self.enable_kafka and not self.kafka_producer:
            logger.warning(
                "Kafka enabled but no producer provided for camera %s, streaming mode disabled",
                self.camera_id
            )
            self.enable_kafka = False
        elif self.enable_kafka:
            logger.info("Kafka streaming enabled for camera {}", self.camera_id)

        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self.stream.start()
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, name=f"DetectionPipeline-{self.camera_id}", daemon=True)
        self._thread.start()
        
        # Update active cameras metric
        active_cameras.inc()
        
        logger.info("Detection pipeline started for camera {}", self.camera_id)

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        self._thread = None
        self.stream.stop()
        
        # Update active cameras metric
        active_cameras.dec()
        
        # Close Kafka producer if enabled
        if self.enable_kafka and self.kafka_producer:
            try:
                self.kafka_producer.close()
                logger.info("Kafka producer closed for camera {}", self.camera_id)
            except Exception as exc:
                logger.warning("Failed to close Kafka producer for camera {}: {}", self.camera_id, exc)
        
        logger.info("Detection pipeline stopped for camera {}", self.camera_id)

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
            
            # Record Prometheus metrics for detection
            camera_id_str = str(self.camera_id)
            model_type = self.detector.model_type
            num_objects = len(detected_objects)
            
            # Record detection metrics before grouping
            try:
                record_detection(
                    camera_id=camera_id_str,
                    model_type=model_type,
                    latency=detection_time,
                    num_objects=num_objects,
                    num_groups=0  # Will be updated after grouping
                )
                
                # Record individual object detections
                for obj in detected_objects:
                    class_name = obj.get("class", "unknown")
                    detected_objects_total.labels(
                        camera_id=camera_id_str,
                        class_name=class_name
                    ).inc()
            except Exception as metrics_exc:
                logger.debug("Failed to record detection metrics: {}", metrics_exc)

            # Preserve original frame for LLM analysis and group cropping
            raw_frame = frame.copy()

            groups, group_images = self._analyze_groups(raw_frame, detected_objects)
            
            # Update group count in metrics
            num_groups = len(groups)
            if num_groups > 0:
                try:
                    from algo.monitoring.metrics import traffic_groups_total
                    traffic_groups_total.labels(camera_id=camera_id_str).inc(num_groups)
                except Exception as metrics_exc:
                    logger.debug("Failed to record group metrics: {}", metrics_exc)

            try:
                raw_data_uri, _ = encode_frame_to_base64(raw_frame)
            except ValueError as exc:
                logger.warning("Failed to encode raw frame for camera {}: {}", self.camera_id, exc)
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
                "Camera %s: prepared %d group crops for LLM analysis",
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
                logger.warning("Failed to encode rendered frame for camera {}: {}", self.camera_id, exc)
                time.sleep(self.frame_interval)
                continue

            dangerous_results = alerts

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
                    "alerts": dangerous_results,
                    "dangerousDrivingResults": dangerous_results,
                    "hasDangerousDriving": self.risk_manager.has_high_risk(),
                    "maxRiskLevel": self.risk_manager.highest_risk_level(),
                    "alertGeneratedAt": now_ts,
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
            
            # Send detection result to Kafka for async LLM processing
            if self.enable_kafka and self.kafka_producer:
                try:
                    kafka_payload = {
                        "cameraId": self.camera_id,
                        "timestamp": datetime.utcnow().isoformat() + "Z",
                        "frameTimestamp": datetime.utcnow().timestamp(),
                        "detectedObjects": detected_objects,
                        "trafficGroups": normalized_groups,
                        "groupImages": llm_group_images,  # Use LLM-ready format
                        "imageWidth": width,
                        "imageHeight": height,
                        "detectionLatency": detection_time,
                        "modelType": self.detector.model_type,
                    }
                    self.kafka_producer.send(kafka_payload, self.camera_id)
                    
                    # Record Kafka metrics
                    record_kafka_send(
                        topic='detection-results',
                        camera_id=camera_id_str,
                        success=True
                    )
                    
                    logger.debug(
                        "Sent detection result to Kafka for camera {} with {} groups",
                        self.camera_id,
                        len(normalized_groups)
                    )
                except Exception as kafka_exc:
                    # Record Kafka error
                    record_kafka_send(
                        topic='detection-results',
                        camera_id=camera_id_str,
                        success=False,
                        error_type=type(kafka_exc).__name__
                    )
                    logger.error(
                        "Failed to send detection to Kafka for camera %s: %s",
                        self.camera_id,
                        kafka_exc
                    )

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
            if idx is None:
                continue
            try:
                idx_int = int(idx)
            except (TypeError, ValueError):
                continue
            alert_index[idx_int] = alert

        for group in groups:
            raw_idx = group.get("groupIndex")
            if raw_idx is None:
                continue
            try:
                idx = int(raw_idx)
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
            logger.error("Group analysis failed for camera {}: {}", self.camera_id, exc)
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
            logger.error("Dangerous driving analysis failed for camera {}: {}", self.camera_id, exc)
            return {
                "hasDangerousDriving": False,
                "maxRiskLevel": "none",
                "results": [],
                "latency": 0.0,
                "model": self.dangerous_analyzer.config.model,
                "rawText": str(exc),
            }
